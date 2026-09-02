"""Tests for the skip-if-unchanged fast path (single-path-per-layer map,
Ticket 03): a fresh full ``mdm mastering`` previously re-resolved every company
from scratch, including rows already correctly resolved and unchanged
since the last run -- idempotent (CIK-exact rematch reuses the entity_id)
but wasted work. ``CompanyResolver.resolve_one`` now compares a content
hash of the exact fields it stages against the hash stored on
``MdmSourceRef`` at the last successful match; a match skips candidate
lookup, the match pipeline, survivorship, and the golden-record upsert
entirely, reusing the existing entity_id.

These tests cover:
  1. content_hash() itself -- deterministic, key-order-independent,
     sensitive to any value change (BaseResolver.content_hash's own
     contract).
  2. A second run over unchanged data skips every row (no new
     MdmChangeLog entries -- proof survivorship never ran, not just that
     the returned entity_id happened to match).
  3. A second run where one field changed does NOT skip that row, and the
     golden record reflects the new value.
  4. The skip path reuses the existing entity_id (doesn't create a
     duplicate MdmCompany row).
"""
from __future__ import annotations

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmChangeLog, MdmCompany, MdmSourceRef
from edgar_warehouse.mdm.pipeline import MDMPipeline
from edgar_warehouse.mdm.resolvers.base import ResolverContext, content_hash
from edgar_warehouse.mdm.resolvers.company import CompanyResolver
from edgar_warehouse.mdm.rules import MDMRuleEngine

from tests.mdm.test_run_companies_concurrency import (
    StubSilver,
    _companies_fixture,
    _seeded_sqlite_session,
    _StubBookkeeping,
)


class TestContentHash:
    def test_deterministic_for_same_fields(self) -> None:
        fields = {"a": 1, "b": "x", "c": None}
        assert content_hash(fields) == content_hash(dict(fields))

    def test_independent_of_key_order(self) -> None:
        assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})

    def test_sensitive_to_any_value_change(self) -> None:
        base = {"a": 1, "b": "x"}
        changed = {"a": 1, "b": "y"}
        assert content_hash(base) != content_hash(changed)

    def test_sensitive_to_key_set_change(self) -> None:
        assert content_hash({"a": 1}) != content_hash({"a": 1, "b": None})


class TestSkipIfUnchanged:
    def test_second_run_over_unchanged_data_skips_every_row(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(5))
        pipeline = MDMPipeline(session=session, silver=silver)

        pipeline.run_companies(bookkeeping=_StubBookkeeping())
        change_log_count_after_first_run = len(
            session.execute(select(MdmChangeLog)).scalars().all()
        )
        assert change_log_count_after_first_run == 5, "first run should stage a change per row"

        second_processed = pipeline.run_companies(bookkeeping=_StubBookkeeping())

        assert second_processed == 5
        change_log_count_after_second_run = len(
            session.execute(select(MdmChangeLog)).scalars().all()
        )
        assert change_log_count_after_second_run == change_log_count_after_first_run, (
            "second run over unchanged data must not run survivorship again -- "
            "no new MdmChangeLog rows"
        )

    def test_second_run_reuses_entity_id_on_skip(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(3))
        pipeline = MDMPipeline(session=session, silver=silver)

        pipeline.run_companies(bookkeeping=_StubBookkeeping())
        first_ids = {
            r.cik: r.entity_id for r in session.execute(select(MdmCompany)).scalars().all()
        }

        pipeline.run_companies(bookkeeping=_StubBookkeeping())
        second_ids = {
            r.cik: r.entity_id for r in session.execute(select(MdmCompany)).scalars().all()
        }

        assert first_ids == second_ids
        assert len(session.execute(select(MdmCompany)).scalars().all()) == 3, (
            "skip path must not create duplicate golden records"
        )

    def test_changed_field_is_not_skipped_and_updates_golden_record(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _companies_fixture(3)
        silver = StubSilver(fixtures)
        pipeline = MDMPipeline(session=session, silver=silver)

        pipeline.run_companies(bookkeeping=_StubBookkeeping())
        change_log_count_after_first_run = len(
            session.execute(select(MdmChangeLog)).scalars().all()
        )

        # Mutate exactly one row's staged field (entity_name) between runs.
        target_cik = fixtures["FROM sec_company"][0]["cik"]
        fixtures["FROM sec_company"][0] = {
            **fixtures["FROM sec_company"][0],
            "entity_name": "Renamed Company",
        }

        second_processed = pipeline.run_companies(bookkeeping=_StubBookkeeping())

        assert second_processed == 3
        change_log_count_after_second_run = len(
            session.execute(select(MdmChangeLog)).scalars().all()
        )
        assert change_log_count_after_second_run == change_log_count_after_first_run + 1, (
            "exactly one row changed -- exactly one new MdmChangeLog entry, "
            "the other two must still skip"
        )
        golden = session.execute(
            select(MdmCompany).where(MdmCompany.cik == target_cik)
        ).scalar_one()
        assert golden.canonical_name == "Renamed Company"

    def test_skip_if_unchanged_returns_none_when_no_prior_match_exists(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        ctx = ResolverContext(session=session, engine=MDMRuleEngine(session), silver=None)
        resolver = CompanyResolver()

        result = resolver._skip_if_unchanged(ctx, "edgar_cik", "999999", content_hash({"x": 1}))

        assert result is None

    def test_skip_if_unchanged_returns_none_on_hash_mismatch(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        silver = StubSilver(_companies_fixture(1))
        pipeline = MDMPipeline(session=session, silver=silver)
        pipeline.run_companies(bookkeeping=_StubBookkeeping())

        cik = _companies_fixture(1)["FROM sec_company"][0]["cik"]
        ref = session.execute(
            select(MdmSourceRef).where(MdmSourceRef.source_id == str(cik))
        ).scalars().first()
        assert ref is not None
        assert ref.source_content_hash is not None

        resolver = CompanyResolver()
        ctx = ResolverContext(session=session, engine=MDMRuleEngine(session), silver=None)
        result = resolver._skip_if_unchanged(
            ctx, "edgar_cik", str(cik), "deliberately-wrong-hash"
        )

        assert result is None
