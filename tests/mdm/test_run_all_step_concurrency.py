"""Tests for MDMPipeline.run_all()'s cross-step concurrency
(mdm-run-step-parallelism wayfinder map, ticket 02).

run_all() previously called its five entity-resolution steps
(run_companies, run_advisers, run_securities, run_persons, run_funds)
strictly sequentially. It now launches all five as concurrent top-level
futures, each on its own fresh MDMPipeline instance/session -- never
sharing self.session across steps. This matters because run_advisers/
run_funds (edgar_warehouse/mdm/adv_bulk.py) write through whatever session
they're given directly, and run_persons' unscoped-name-match fallback also
writes through self.session directly -- none of the five is safe to launch
concurrently against one shared session.

These tests cover:
  1. Session isolation: every step gets its own session, never self.session
     (the property that actually matters for correctness -- holds
     regardless of whether the steps run sequentially or truly
     concurrently, so it's provable even under the SQLite dialect guard).
  2. The SQLite dialect guard: max_workers=1 for a sqlite-bound session
     (matches run_companies()/derive_relationships()'s identical guard --
     StaticPool shares one physical connection and cannot run concurrent
     transactions), _RUN_STEP_MAX_WORKERS otherwise.
  3. Correctness: run_all() against a real SilverDatabase still resolves
     companies and returns accurate PipelineStats.
  4. Fail-fast: an exception in any one step propagates out of run_all()
     rather than being silently swallowed.
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest
from sqlalchemy import select

from edgar_warehouse.mdm import pipeline as pipeline_module
from edgar_warehouse.mdm.database import MdmCompany, MdmEntityTypeDefinition, MdmRelationshipType
from edgar_warehouse.mdm.pipeline import MDMPipeline
from edgar_warehouse.silver_store import SilverDatabase

from tests.mdm.test_run_companies_concurrency import _seeded_sqlite_session


def _seed_fundamentals_relationship_types(session) -> None:
    """_seeded_sqlite_session()'s seed_defaults() only registers the 8
    original relationship types -- EMPLOYED_BY/AUDITED_BY/INSTITUTIONAL_HOLDS
    only exist in prod via the separate, Postgres-specific
    005_fundamentals_relationships.sql migration (DO $$ blocks,
    gen_random_uuid() -- not portable to the SQLite path these unit tests
    use). Pre-existing gap, unrelated to this ticket: derive_relationships()
    unscoped (all 11 types, exactly what run_all() calls) raises KeyError
    for these 3 under the plain seed_defaults() fixture. Scoped narrowly to
    this test file rather than touching the shared seed_defaults()/
    _seed_relationship_types() helpers -- out of scope for
    mdm-run-step-parallelism ticket 02, which never touched
    derive_relationships() itself."""
    if not session.query(MdmEntityTypeDefinition).filter_by(entity_type="audit_firm").first():
        session.add(MdmEntityTypeDefinition(
            entity_type="audit_firm", neo4j_label="AuditFirm",
            domain_table="mdm_audit_firm", api_path_prefix="/audit-firms",
            primary_id_field="entity_id", display_name="Audit Firm",
        ))
        session.flush()
    for rel_type_name, source, target, dedup_fields in (
        ("EMPLOYED_BY", "person", "company", ["source_entity_id", "target_entity_id", "fiscal_year"]),
        ("AUDITED_BY", "company", "audit_firm", ["source_entity_id", "target_entity_id", "fiscal_year"]),
        ("INSTITUTIONAL_HOLDS", "adviser", "security", ["source_entity_id", "target_entity_id", "quarter_end"]),
    ):
        if not session.query(MdmRelationshipType).filter_by(rel_type_name=rel_type_name).first():
            session.add(MdmRelationshipType(
                rel_type_name=rel_type_name, source_node_type=source,
                target_node_type=target, direction="outbound",
                dedup_key_fields=dedup_fields, merge_strategy="extend_temporal",
            ))
    session.commit()


def _real_silver_with_companies(n: int) -> SilverDatabase:
    tmpdir = tempfile.mkdtemp()
    silver_path = os.path.join(tmpdir, "silver.duckdb")
    db = SilverDatabase(silver_path)
    for i in range(n):
        db._conn.execute(
            "INSERT INTO sec_company (cik, entity_name) VALUES (?, ?)",
            [900000 + i, f"Company {i}"],
        )
    db.close()
    return SilverDatabase(silver_path)


class TestRunAllUsesIsolatedSessionsPerStep:
    def test_no_step_ever_uses_the_outer_pipeline_session(self) -> None:
        """The load-bearing correctness property: run_advisers/run_funds
        write through whatever session they're given directly, and
        run_persons' unscoped fallback writes through self.session
        directly -- if any step's worker were handed the outer pipeline's
        own session instead of a fresh one, this would be a genuine
        thread-safety bug (concurrent use of one non-thread-safe
        SQLAlchemy Session), not just a style issue."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_companies(2)
        _seed_fundamentals_relationship_types(session)
        outer_pipeline = MDMPipeline(session=session, silver=silver)

        created_sessions: list[object] = []
        real_get_session = pipeline_module.get_session

        def _tracking_get_session(engine):
            worker_session = real_get_session(engine)
            created_sessions.append(worker_session)
            return worker_session

        with patch.object(pipeline_module, "get_session", side_effect=_tracking_get_session):
            outer_pipeline.run_all(limit=1)

        # get_session() is called for the 5 entity-resolution steps AND
        # (separately, unaffected by this ticket) once per relationship
        # type inside derive_relationships() -- at least the 5 entity
        # steps' worth must be present, and every single one, whichever
        # phase it came from, must be its own distinct session, never the
        # outer pipeline's self.session.
        assert len(created_sessions) >= 5
        assert len(set(id(s) for s in created_sessions)) == len(created_sessions), (
            "expected every tracked session to be a genuinely distinct object, got duplicates"
        )
        for worker_session in created_sessions:
            assert worker_session is not session, (
                "a step's worker session must never be the outer pipeline's "
                "own self.session -- that's exactly the shared-session race "
                "this fix exists to prevent"
            )


class TestRunAllSqliteDialectGuard:
    def test_sqlite_engine_forces_single_worker(self) -> None:
        """Mirrors run_companies()/derive_relationships()'s identical
        guard: SQLite's StaticPool test fixture shares one physical
        connection and cannot run simultaneous transactions, so
        max_workers must be forced to 1 regardless of
        MDM_RUN_STEP_CONCURRENCY's configured value."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_companies(1)
        _seed_fundamentals_relationship_types(session)
        outer_pipeline = MDMPipeline(session=session, silver=silver)

        captured_kwargs: list[dict] = []
        real_executor_cls = pipeline_module.ThreadPoolExecutor

        class _CapturingExecutor(real_executor_cls):
            def __init__(self, *args, **kwargs):
                captured_kwargs.append(kwargs)
                super().__init__(*args, **kwargs)

        with patch.object(pipeline_module, "ThreadPoolExecutor", _CapturingExecutor):
            outer_pipeline.run_all(limit=1)

        # run_all()'s own 5-step executor is the first ThreadPoolExecutor
        # constructed; company/security/person's internal per-row pools
        # construct further ones inside it, all also forced to 1 under
        # sqlite -- every captured call must show max_workers=1.
        assert captured_kwargs, "expected at least one ThreadPoolExecutor construction"
        assert all(kwargs.get("max_workers") == 1 for kwargs in captured_kwargs)


class TestRunAllCorrectness:
    def test_resolves_companies_and_returns_accurate_stats(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_companies(3)
        _seed_fundamentals_relationship_types(session)
        outer_pipeline = MDMPipeline(session=session, silver=silver)

        stats = outer_pipeline.run_all()

        assert stats.companies_processed == 3
        assert stats.advisers_processed == 0
        assert stats.securities_processed == 0
        assert stats.persons_processed == 0
        assert stats.funds_processed == 0

        # The outer session (not any worker session) is what the test
        # queries against afterward -- proves each worker's commit()
        # really did land in the shared underlying database, not just its
        # own disconnected in-memory state.
        resolved = {row.cik for row in session.execute(select(MdmCompany)).scalars().all()}
        assert resolved == {900000, 900001, 900002}


class TestRunAllFailsFast:
    def test_a_failing_step_propagates_out_of_run_all(self, monkeypatch) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_companies(1)
        outer_pipeline = MDMPipeline(session=session, silver=silver)

        # Raise from inside one step's worker without patching MDMPipeline
        # itself (a class-level method patch here has shown flaky
        # interaction with unrelated test ordering elsewhere in this
        # package -- patching the lower-level get_session() call every
        # _run_step worker makes is an equally valid way to inject a
        # failure into exactly one step and proves the same propagation
        # property).
        call_count = {"n": 0}
        real_get_session = pipeline_module.get_session

        def _raise_on_second_call(engine):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("boom")
            return real_get_session(engine)

        monkeypatch.setattr(pipeline_module, "get_session", _raise_on_second_call)

        with pytest.raises(RuntimeError, match="boom"):
            outer_pipeline.run_all()
        assert call_count["n"] >= 2

    def test_shutdown_does_not_wait_for_still_running_steps(self, monkeypatch) -> None:
        """Regression for a bug the mdm-run-step-parallelism Spec review
        caught: `with ThreadPoolExecutor(...) as executor:` always calls
        shutdown(wait=True) on exit, even on an exception. With exactly 5
        futures and max_workers defaulting to 5, all 5 start immediately,
        so f.cancel() on each is a no-op and that implicit wait=True would
        block the re-raise until every already-running sibling step
        finished -- turning "propagates immediately" (ticket 02's Answer)
        into "propagates after the slowest still-running step" (up to the
        ~2h14m company / ~1h50m security durations measured in ticket 01).
        This doesn't need real multi-worker timing to catch: the exception
        path must call shutdown(wait=False, cancel_futures=True) instead,
        and that's true regardless of max_workers -- including under the
        sqlite dialect guard's forced max_workers=1 used by every other
        test in this file."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_companies(1)
        outer_pipeline = MDMPipeline(session=session, silver=silver)

        shutdown_calls: list[dict] = []
        real_executor_cls = pipeline_module.ThreadPoolExecutor

        class _RecordingExecutor(real_executor_cls):
            def shutdown(self, wait=True, *, cancel_futures=False):
                shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})
                return super().shutdown(wait=wait, cancel_futures=cancel_futures)

        call_count = {"n": 0}
        real_get_session = pipeline_module.get_session

        def _raise_on_second_call(engine):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("boom")
            return real_get_session(engine)

        monkeypatch.setattr(pipeline_module, "get_session", _raise_on_second_call)
        monkeypatch.setattr(pipeline_module, "ThreadPoolExecutor", _RecordingExecutor)

        with pytest.raises(RuntimeError, match="boom"):
            outer_pipeline.run_all()

        assert shutdown_calls, "expected shutdown() to be called on the exception path"
        assert shutdown_calls[-1] == {"wait": False, "cancel_futures": True}
