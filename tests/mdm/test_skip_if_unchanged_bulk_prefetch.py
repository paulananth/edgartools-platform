"""Tests for mdm-run-throughput Ticket 03: batching
BaseResolver._skip_if_unchanged's per-row mdm_source_ref SELECT into one
bulk prefetch per resolver batch.

Live evidence this closes: a CloudWatch Logs Insights breakdown of a real
prod mdm-mastering run showed 49,425 of ~57,000 SQL calls in the first ~14
minutes of pure entity-resolution work were individual SELECTs against
mdm_source_ref -- essentially one per row processed across
run_companies/run_persons/run_securities, since _skip_if_unchanged had no
batching at all.

These tests cover:
  1. MDMPipeline._prefetch_source_refs -- correctness (right rows, right
     source_system filter) and chunking (a batch larger than the chunk
     size still returns every row, via more than one SELECT).
  2. ResolverContext.prefetched_source_refs -- when populated,
     _skip_if_unchanged never touches the database at all, and treats an
     absent key as "no prior match" rather than falling back to a live
     query (the prefetch is authoritative for the whole batch it covers).
  3. run_companies/run_persons/run_securities actually build and thread the
     prefetch through -- a round-trip-count regression guard proving the
     mdm_source_ref SELECT count stays flat as row count grows, mirroring
     TestRelationshipDeriveBoundedRoundTrips's existing precedent for the
     relationship-derivation side of this same class of fix.
  4. Each resolver's extracted _source_id static method is the single
     source of truth resolve_one and the pipeline's prefetch loop both
     use -- protects against the two computations silently drifting apart.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest
from sqlalchemy import event, select

from edgar_warehouse.mdm.database import MdmCompany, MdmEntity, MdmSourceRef
from edgar_warehouse.mdm.pipeline import MDMPipeline
from edgar_warehouse.mdm.resolvers.base import ResolverContext
from edgar_warehouse.mdm.resolvers.company import CompanyResolver
from edgar_warehouse.mdm.resolvers.person import PersonResolver
from edgar_warehouse.mdm.resolvers.security import SecurityResolver
from edgar_warehouse.mdm.rules import MDMRuleEngine

from tests.mdm.test_run_companies_concurrency import (
    StubSilver,
    _companies_fixture,
    _seeded_sqlite_session,
    _StubBookkeeping,
)
from tests.mdm.test_run_securities_persons_concurrency import _person_rows, _security_rows


def _count_source_ref_selects(session, fn):
    """Run fn() while counting SELECTs against mdm_source_ref issued on
    session's bind, mirroring TestRelationshipDeriveBoundedRoundTrips's
    existing before_cursor_execute pattern."""
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        normalized = " ".join(statement.lower().split())
        if "mdm_source_ref" in normalized and normalized.startswith("select"):
            statements.append(normalized)

    bind = session.get_bind()
    event.listen(bind, "before_cursor_execute", capture)
    try:
        result = fn()
    finally:
        event.remove(bind, "before_cursor_execute", capture)
    return result, statements


class TestPrefetchSourceRefs:
    def test_empty_source_ids_short_circuits_without_a_query(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        pipeline = MDMPipeline(session=session, silver=StubSilver({}))

        result, statements = _count_source_ref_selects(
            session, lambda: pipeline._prefetch_source_refs("edgar_cik", [])
        )

        assert result == {}
        assert statements == []

    def test_returns_hash_and_entity_id_keyed_by_source_id(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        pipeline = MDMPipeline(session=session, silver=StubSilver({}))

        entity_id = MdmEntity(entity_type="company")
        session.add(entity_id)
        session.flush()
        session.add(MdmSourceRef(
            entity_id=entity_id.entity_id, source_system="edgar_cik", source_id="123",
            source_priority=1, source_content_hash="abc123",
        ))
        session.commit()

        result = pipeline._prefetch_source_refs("edgar_cik", ["123", "999"])

        assert result == {("edgar_cik", "123"): ("abc123", entity_id.entity_id)}
        assert ("edgar_cik", "999") not in result

    def test_filters_by_source_system(self) -> None:
        """A source_id shared across two source_systems must not leak the
        wrong system's ref into the prefetch."""
        session = _seeded_sqlite_session(static_pool=True)
        pipeline = MDMPipeline(session=session, silver=StubSilver({}))

        wrong_system_entity = MdmEntity(entity_type="security")
        session.add(wrong_system_entity)
        session.flush()
        session.add(MdmSourceRef(
            entity_id=wrong_system_entity.entity_id, source_system="ownership_filing",
            source_id="shared-id", source_priority=1, source_content_hash="wrong-hash",
        ))
        session.commit()

        result = pipeline._prefetch_source_refs("edgar_cik", ["shared-id"])

        assert result == {}

    def test_chunks_when_batch_exceeds_chunk_size(self, monkeypatch) -> None:
        """A batch larger than the chunk size must still return every row,
        via more than one SELECT -- proves the IN() splitting is correct,
        not just present."""
        import edgar_warehouse.mdm.pipeline as pipeline_module
        monkeypatch.setattr(pipeline_module, "_SOURCE_REF_PREFETCH_BATCH_SIZE", 2)

        session = _seeded_sqlite_session(static_pool=True)
        pipeline = MDMPipeline(session=session, silver=StubSilver({}))

        source_ids = [str(i) for i in range(5)]
        for sid in source_ids:
            entity = MdmEntity(entity_type="company")
            session.add(entity)
            session.flush()
            session.add(MdmSourceRef(
                entity_id=entity.entity_id, source_system="edgar_cik", source_id=sid,
                source_priority=1, source_content_hash=f"hash-{sid}",
            ))
        session.commit()

        result, statements = _count_source_ref_selects(
            session, lambda: pipeline._prefetch_source_refs("edgar_cik", source_ids)
        )

        assert set(result.keys()) == {("edgar_cik", sid) for sid in source_ids}
        for sid in source_ids:
            assert result[("edgar_cik", sid)][0] == f"hash-{sid}"
        # 5 ids at chunk size 2 -> 3 chunks (2, 2, 1), not 1 and not 5.
        assert len(statements) == 3, statements


class TestSkipIfUnchangedUsesPrefetch:
    def test_uses_prefetched_dict_without_touching_the_database(self, monkeypatch) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        ctx = ResolverContext(
            session=session,
            engine=MDMRuleEngine(session),
            silver=None,
            prefetched_source_refs={("edgar_cik", "123"): ("matching-hash", "entity-abc")},
        )
        resolver = CompanyResolver()

        def _forbidden(*_args, **_kwargs):
            raise AssertionError("_skip_if_unchanged must not query the database when a prefetch is provided")

        monkeypatch.setattr(session, "execute", _forbidden)

        result = resolver._skip_if_unchanged(ctx, "edgar_cik", "123", "matching-hash")

        assert result == "entity-abc"

    def test_hash_mismatch_in_prefetch_returns_none(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        ctx = ResolverContext(
            session=session,
            engine=MDMRuleEngine(session),
            silver=None,
            prefetched_source_refs={("edgar_cik", "123"): ("stored-hash", "entity-abc")},
        )
        resolver = CompanyResolver()

        result = resolver._skip_if_unchanged(ctx, "edgar_cik", "123", "different-hash")

        assert result is None

    def test_source_id_absent_from_prefetch_is_treated_as_no_prior_match(self) -> None:
        """Once a prefetch dict is provided, it's authoritative for the
        whole batch it covers -- a missing key means genuinely no prior
        match, not 'fall back and check the database anyway'."""
        session = _seeded_sqlite_session(static_pool=True)
        ctx = ResolverContext(
            session=session,
            engine=MDMRuleEngine(session),
            silver=None,
            prefetched_source_refs={},
        )
        resolver = CompanyResolver()

        result = resolver._skip_if_unchanged(ctx, "edgar_cik", "not-in-the-dict", "any-hash")

        assert result is None

    def test_same_source_id_under_a_different_source_system_does_not_cross_match(self) -> None:
        """The prefetch key is (source_system, source_id), not source_id
        alone -- a dict entry for one source_system must never satisfy a
        lookup for the same source_id under a different source_system."""
        session = _seeded_sqlite_session(static_pool=True)
        ctx = ResolverContext(
            session=session,
            engine=MDMRuleEngine(session),
            silver=None,
            prefetched_source_refs={("ownership_filing", "123"): ("matching-hash", "entity-abc")},
        )
        resolver = CompanyResolver()

        result = resolver._skip_if_unchanged(ctx, "edgar_cik", "123", "matching-hash")

        assert result is None

    def test_none_prefetch_falls_back_to_the_original_per_row_query(self) -> None:
        """Default behavior (no opt-in) is byte-for-byte unchanged."""
        session = _seeded_sqlite_session(static_pool=True)
        entity = MdmEntity(entity_type="company")
        session.add(entity)
        session.flush()
        session.add(MdmSourceRef(
            entity_id=entity.entity_id, source_system="edgar_cik", source_id="123",
            source_priority=1, source_content_hash="abc",
        ))
        session.commit()

        ctx = ResolverContext(session=session, engine=MDMRuleEngine(session), silver=None)
        resolver = CompanyResolver()

        result = resolver._skip_if_unchanged(ctx, "edgar_cik", "123", "abc")

        assert result == entity.entity_id


class TestSourceIdStaticMethods:
    def test_company_source_id_matches_cik(self) -> None:
        assert CompanyResolver._source_id({"cik": 12345}) == "12345"

    def test_person_source_id_matches_accession_and_owner_index(self) -> None:
        row = {"accession_number": "0000123-24-000001", "owner_index": 2}
        assert PersonResolver._source_id(row) == "0000123-24-000001:2"

    def test_security_source_id_prefers_explicit_source_id(self) -> None:
        assert SecurityResolver._source_id({"source_id": "explicit-id"}) == "explicit-id"

    def test_security_source_id_derives_from_transaction_fields_when_absent(self) -> None:
        row = {
            "accession_number": "acc-1", "owner_index": 1, "txn_index": 0,
            "is_derivative": False,
        }
        assert SecurityResolver._source_id(row) == "acc-1:1:0"

    def test_security_source_id_derivative_flag_changes_the_key(self) -> None:
        row = {
            "accession_number": "acc-1", "owner_index": 1, "txn_index": 0,
            "is_derivative": True,
        }
        assert SecurityResolver._source_id(row) == "acc-1:derivative:1:0"


class TestRunCompaniesUsesBulkPrefetch:
    def test_source_ref_select_count_stays_flat_as_rows_grow(self) -> None:
        """Regression guard: before this fix, N companies paid N
        mdm_source_ref SELECTs (one per _skip_if_unchanged call). After
        this fix, the whole batch pays a small, row-count-independent
        number of SELECTs (the bulk prefetch, plus whatever _existing_
        candidates/company_entity_ids-style lookups already existed)."""
        session_small = _seeded_sqlite_session(static_pool=True)
        pipeline_small = MDMPipeline(session=session_small, silver=StubSilver(_companies_fixture(3)))
        pipeline_small.run_companies(bookkeeping=_StubBookkeeping())
        _, first_run_statements = _count_source_ref_selects(
            session_small, lambda: pipeline_small.run_companies(bookkeeping=_StubBookkeeping())
        )

        session_large = _seeded_sqlite_session(static_pool=True)
        pipeline_large = MDMPipeline(session=session_large, silver=StubSilver(_companies_fixture(25)))
        pipeline_large.run_companies(bookkeeping=_StubBookkeeping())
        _, second_run_statements = _count_source_ref_selects(
            session_large, lambda: pipeline_large.run_companies(bookkeeping=_StubBookkeeping())
        )

        assert len(first_run_statements) <= 2, first_run_statements
        assert len(second_run_statements) <= 2, second_run_statements
        assert len(second_run_statements) == len(first_run_statements), (
            "SELECT count must not grow with row count -- 3 vs 25 companies "
            "must cost the same number of mdm_source_ref round trips"
        )


class TestRunPersonsUsesBulkPrefetch:
    def test_source_ref_select_count_stays_flat_as_rows_grow(self) -> None:
        session_small = _seeded_sqlite_session(static_pool=True)
        pipeline_small = MDMPipeline(session=session_small, silver=StubSilver(_person_rows([501, 502])))
        pipeline_small.run_persons()
        _, small_statements = _count_source_ref_selects(session_small, lambda: pipeline_small.run_persons())

        session_large = _seeded_sqlite_session(static_pool=True)
        owner_ciks = list(range(601, 621))
        pipeline_large = MDMPipeline(session=session_large, silver=StubSilver(_person_rows(owner_ciks)))
        pipeline_large.run_persons()
        _, large_statements = _count_source_ref_selects(session_large, lambda: pipeline_large.run_persons())

        assert len(small_statements) <= 2, small_statements
        assert len(large_statements) <= 2, large_statements
        assert len(large_statements) == len(small_statements), (
            "SELECT count must not grow with row count -- 2 vs 20 owners "
            "must cost the same number of mdm_source_ref round trips"
        )


class TestRunSecuritiesUsesBulkPrefetch:
    def test_source_ref_select_count_stays_flat_as_rows_grow(self) -> None:
        session_small = _seeded_sqlite_session(static_pool=True)
        fixtures_small = _security_rows({111: ["Common Stock", "Preferred Stock"]})
        pipeline_small = MDMPipeline(session=session_small, silver=StubSilver(fixtures_small))
        pipeline_small.run_securities()
        _, small_statements = _count_source_ref_selects(session_small, lambda: pipeline_small.run_securities())

        session_large = _seeded_sqlite_session(static_pool=True)
        fixtures_large = _security_rows({
            111: [f"Security Class {i}" for i in range(10)],
            222: [f"Other Class {i}" for i in range(10)],
        })
        pipeline_large = MDMPipeline(session=session_large, silver=StubSilver(fixtures_large))
        pipeline_large.run_securities()
        _, large_statements = _count_source_ref_selects(session_large, lambda: pipeline_large.run_securities())

        assert len(small_statements) <= 2, small_statements
        assert len(large_statements) <= 2, large_statements
        assert len(large_statements) == len(small_statements), (
            "SELECT count must not grow with row count -- 2 vs 20 securities "
            "must cost the same number of mdm_source_ref round trips"
        )
