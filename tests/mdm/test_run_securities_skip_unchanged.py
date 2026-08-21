"""Tests for SecurityResolver's skip-if-unchanged fast path (added
2026-08-21, mirroring CompanyResolver's existing one from single-path-per-
layer map Ticket 03 -- see tests/mdm/test_run_companies_skip_unchanged.py).

Root cause this closes: run_securities() has no resumable ledger (unlike
run_companies()), so a restarted `mdm run` re-processes every ownership-
transaction row from scratch. Before this fix, SecurityResolver.resolve_one
never called _skip_if_unchanged, so every re-run of an unchanged row called
_stage_attrs() again -- and stage_candidate() always INSERTs a fresh row
with no dedup, since mdm_entity_attribute_stage has no pruning anywhere in
this codebase. A heavily-refiled security (e.g. a large issuer's "Common
Stock") accumulates one duplicate stage row per re-run forever, and every
future run_survivorship_for_entity() call for that entity re-reads the
full, ever-growing history. Live production evidence: SELECT rowcounts of
8560-12547 for a single entity's stage history during a Stage 14 re-run,
directly measured while diagnosing a multi-hour slowdown.

These tests cover:
  1. A second run over unchanged data skips every row -- no new
     MdmEntityAttributeStage rows (the actual bug), no new MdmChangeLog
     rows (proof survivorship never ran, mirroring the company test).
  2. The skip path reuses the existing entity_id (doesn't create a
     duplicate MdmSecurity row).
  3. A row whose *resolved issuer* changes between runs (the NULL-issuer
     "upgrade" scenario SecurityResolver.resolve_one has its own docstring
     about) is NOT skipped -- the content hash must cover issuer_entity_id,
     not just the title.
  4. _skip_if_unchanged's own no-prior-match and hash-mismatch behavior,
     mirroring the company test's direct-call coverage.
"""
from __future__ import annotations

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmChangeLog, MdmEntityAttributeStage, MdmSecurity, MdmSourceRef
from edgar_warehouse.mdm.pipeline import MDMPipeline
from edgar_warehouse.mdm.resolvers.base import ResolverContext, content_hash
from edgar_warehouse.mdm.resolvers.security import SecurityResolver
from edgar_warehouse.mdm.rules import MDMRuleEngine

from tests.mdm.test_run_companies_concurrency import StubSilver, _seeded_sqlite_session
from tests.mdm.test_run_securities_persons_concurrency import _security_rows


class TestSecuritySkipIfUnchanged:
    def test_second_run_over_unchanged_data_skips_every_row(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _security_rows({111: ["Common Stock"], 222: ["Preferred Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        pipeline.run_securities()
        stage_count_after_first = len(
            session.execute(select(MdmEntityAttributeStage)).scalars().all()
        )
        change_log_count_after_first = len(session.execute(select(MdmChangeLog)).scalars().all())
        assert stage_count_after_first == 4, "2 rows x 2 staged fields (canonical_title, security_type)"
        assert change_log_count_after_first == 2, "one change-log entry per resolved row"

        second_processed = pipeline.run_securities()

        assert second_processed == 2
        stage_count_after_second = len(
            session.execute(select(MdmEntityAttributeStage)).scalars().all()
        )
        change_log_count_after_second = len(session.execute(select(MdmChangeLog)).scalars().all())
        assert stage_count_after_second == stage_count_after_first, (
            "second run over unchanged data must not re-stage -- this is the actual "
            "production bug: unbounded duplicate mdm_entity_attribute_stage growth "
            "across repeated mdm run restarts"
        )
        assert change_log_count_after_second == change_log_count_after_first, (
            "second run over unchanged data must not run survivorship again"
        )

    def test_second_run_reuses_entity_id_on_skip(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _security_rows({111: ["Common Stock", "Preferred Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        pipeline.run_securities()
        first_ids = {
            r.canonical_title: r.entity_id
            for r in session.execute(select(MdmSecurity)).scalars().all()
        }

        pipeline.run_securities()
        second_ids = {
            r.canonical_title: r.entity_id
            for r in session.execute(select(MdmSecurity)).scalars().all()
        }

        assert first_ids == second_ids
        assert len(session.execute(select(MdmSecurity)).scalars().all()) == 2, (
            "skip path must not create duplicate golden records"
        )

    def test_issuer_newly_resolving_between_runs_is_not_skipped(self) -> None:
        """The NULL-issuer "upgrade" scenario (SecurityResolver.resolve_one's
        own docstring): a row's issuer_cik was unresolved on the first run
        (no MdmCompany yet), then the company gets resolved before the
        second run. The content hash must include issuer_entity_id, not
        just the title, or this row would wrongly skip and never upgrade
        its NULL-issuer entity."""
        session = _seeded_sqlite_session(static_pool=True)
        # issuer_cik=111 has NO MdmCompany row yet on the first run.
        fixtures = _security_rows({111: ["Common Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        pipeline.run_securities()
        first_entity = session.execute(select(MdmSecurity)).scalars().one()
        assert first_entity.issuer_entity_id is None

        # Now resolve the company for CIK 111 (mirrors run_companies() having
        # run between two mdm run attempts).
        from edgar_warehouse.mdm.database import MdmCompany, MdmEntity

        company_entity = MdmEntity(entity_type="company")
        session.add(company_entity)
        session.flush()
        session.add(MdmCompany(entity_id=company_entity.entity_id, cik=111, canonical_name="Co 111"))
        session.commit()

        second_processed = pipeline.run_securities()

        assert second_processed == 1
        securities = session.execute(select(MdmSecurity)).scalars().all()
        assert len(securities) == 1, "must upgrade the existing entity, not skip or duplicate"
        assert securities[0].issuer_entity_id == company_entity.entity_id, (
            "row must be reprocessed (not skipped) once its issuer newly resolves"
        )

    def test_skip_if_unchanged_returns_none_when_no_prior_match_exists(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        ctx = ResolverContext(session=session, engine=MDMRuleEngine(session), silver=None)
        resolver = SecurityResolver()

        result = resolver._skip_if_unchanged(
            ctx, "ownership_filing", "acc-999:1:0", content_hash({"x": 1})
        )

        assert result is None

    def test_skip_if_unchanged_returns_none_on_hash_mismatch(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _security_rows({111: ["Common Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))
        pipeline.run_securities()

        source_id = "acc-1:1:0"
        ref = session.execute(
            select(MdmSourceRef).where(MdmSourceRef.source_id == source_id)
        ).scalars().first()
        assert ref is not None
        assert ref.source_content_hash is not None

        resolver = SecurityResolver()
        ctx = ResolverContext(session=session, engine=MDMRuleEngine(session), silver=None)
        result = resolver._skip_if_unchanged(
            ctx, "ownership_filing", source_id, "deliberately-wrong-hash"
        )

        assert result is None
