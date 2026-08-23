"""Tests for PersonResolver's skip-if-unchanged fast path (added
2026-08-21, mdm-resolver-skip-unchanged map Ticket 02 -- mirrors
CompanyResolver's original fix and SecurityResolver's port of it, see
tests/mdm/test_run_companies_skip_unchanged.py and
tests/mdm/test_run_securities_skip_unchanged.py).

Root cause this closes: run_persons() has no resumable ledger (unlike
run_companies()), so a restarted `mdm run` re-processes every ownership
reporting-owner row from scratch. Before this fix, PersonResolver.resolve_one
never called _skip_if_unchanged, so every re-run of an unchanged row called
_stage_attrs() again -- and stage_candidate() always INSERTs a fresh row
with no dedup, since mdm_entity_attribute_stage has no pruning anywhere in
this codebase (confirmed by repo-wide search, same finding as the
SecurityResolver investigation). A heavily-refiled insider accumulates one
duplicate stage row per re-run forever.

These tests cover:
  1. A second run over unchanged data skips every row -- no new
     MdmEntityAttributeStage rows (the actual bug), no new MdmChangeLog
     rows (proof survivorship never ran).
  2. The skip path reuses the existing entity_id (doesn't create a
     duplicate MdmPerson row).
  3. A row whose issuer_cik context changes between runs is NOT skipped --
     the content hash must cover issuer_cik even though it's never staged
     as a golden field, since FuzzyNameMatcher uses it as a match context
     field for owner_cik-less rows.
  4. _skip_if_unchanged's own no-prior-match and hash-mismatch behavior,
     mirroring test_run_securities_skip_unchanged.py's direct-call coverage
     of the same shared base method.
"""
from __future__ import annotations

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmChangeLog, MdmEntityAttributeStage, MdmPerson, MdmSourceRef
from edgar_warehouse.mdm.pipeline import MDMPipeline
from edgar_warehouse.mdm.resolvers.base import ResolverContext, content_hash
from edgar_warehouse.mdm.resolvers.person import PersonResolver
from edgar_warehouse.mdm.rules import MDMRuleEngine

from tests.mdm.test_run_companies_concurrency import StubSilver, _seeded_sqlite_session
from tests.mdm.test_run_securities_persons_concurrency import _person_rows


class TestPersonSkipIfUnchanged:
    def test_second_run_over_unchanged_data_skips_every_row(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _person_rows([111, 222])
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        first_processed = pipeline.run_persons()
        assert first_processed == 2
        stage_count_after_first = len(
            session.execute(select(MdmEntityAttributeStage)).scalars().all()
        )
        change_log_count_after_first = len(session.execute(select(MdmChangeLog)).scalars().all())
        assert stage_count_after_first == 6, "2 rows x 3 staged fields (canonical_name, owner_cik, primary_role)"
        assert change_log_count_after_first == 2

        second_processed = pipeline.run_persons()

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
        fixtures = _person_rows([111, 222])
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        pipeline.run_persons()
        first_ids = {
            r.owner_cik: r.entity_id
            for r in session.execute(select(MdmPerson)).scalars().all()
        }

        pipeline.run_persons()
        second_ids = {
            r.owner_cik: r.entity_id
            for r in session.execute(select(MdmPerson)).scalars().all()
        }

        assert first_ids == second_ids
        assert len(session.execute(select(MdmPerson)).scalars().all()) == 2, (
            "skip path must not create duplicate golden records"
        )

    def test_issuer_cik_change_is_not_skipped(self) -> None:
        """issuer_cik is never staged as a PERSON_FIELDS value, but it is a
        FuzzyNameMatcher context field -- the content hash must still cover
        it, or a row whose issuer context changes between runs would wrongly
        skip reprocessing.

        Asserts on MdmSourceRef.source_content_hash rather than stage-row
        count: stage_candidate() upserts on its natural key
        (investigate-and-fix-stage-bloat, 2026-08-21), so a genuine
        reprocess updates the same 3 PERSON_FIELDS rows in place rather
        than adding 3 new ones -- row count alone no longer distinguishes
        "reprocessed" from "skipped". The hash changing is the correct
        signal: it only advances when resolve_one actually re-ran past the
        skip check.
        """
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _person_rows([111])
        fixtures["sec_ownership_reporting_owner"][0]["issuer_cik"] = 900
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        pipeline.run_persons()
        source_id = "acc-0:0"
        hash_after_first = session.execute(
            select(MdmSourceRef.source_content_hash).where(MdmSourceRef.source_id == source_id)
        ).scalar_one()
        assert hash_after_first is not None

        fixtures["sec_ownership_reporting_owner"][0]["issuer_cik"] = 901
        second_processed = pipeline.run_persons()

        assert second_processed == 1
        hash_after_second = session.execute(
            select(MdmSourceRef.source_content_hash).where(MdmSourceRef.source_id == source_id)
        ).scalar_one()
        assert hash_after_second != hash_after_first, (
            "a changed issuer_cik must be reprocessed (its stored content "
            "hash must advance), not skipped"
        )

    def test_skip_if_unchanged_returns_none_when_no_prior_match_exists(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        ctx = ResolverContext(session=session, engine=MDMRuleEngine(session), silver=None)
        resolver = PersonResolver()

        result = resolver._skip_if_unchanged(
            ctx, "ownership_filing", "acc-999:1", content_hash({"x": 1})
        )

        assert result is None

    def test_skip_if_unchanged_returns_none_on_hash_mismatch(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _person_rows([111])
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))
        pipeline.run_persons()

        source_id = "acc-0:0"
        ref = session.execute(
            select(MdmSourceRef).where(MdmSourceRef.source_id == source_id)
        ).scalars().first()
        assert ref is not None
        assert ref.source_content_hash is not None

        resolver = PersonResolver()
        ctx = ResolverContext(session=session, engine=MDMRuleEngine(session), silver=None)
        result = resolver._skip_if_unchanged(
            ctx, "ownership_filing", source_id, "deliberately-wrong-hash"
        )

        assert result is None
