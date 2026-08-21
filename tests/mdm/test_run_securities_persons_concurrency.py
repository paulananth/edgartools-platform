"""Tests for MDMPipeline.run_securities()/run_persons()'s grouped-concurrency
resolution path (mdm-run-throughput map).

Both loops previously resolved one row at a time against a single shared
SQLAlchemy session (self.session), paying the same ~68ms/call round-trip
tax as run_companies() did before PR #376 -- estimated ~9h (security,
~15,000 rows) and ~4.7h (person, ~7,911 rows) sequential. Unlike company,
neither domain is safely per-row-independent:

  - SecurityResolver._existing_candidates always scopes its exact match to
    canonical_title (issuer-scoped when known, NULL-issuer-scoped
    otherwise), but resolve_one's "upgrade a NULL-issuer security" path
    lets two DIFFERENT issuers sharing the same title interact. So rows
    are grouped by canonical_title alone (not (issuer, title)) and each
    group's rows run sequentially on one worker; different titles run
    concurrently across a bounded thread pool.
  - PersonResolver._existing_candidates scopes strictly to owner_cik when
    present (grouped the same way, safe to parallelize across CIKs), but
    falls back to an UNSCOPED fuzzy match across the entire mdm_person
    table when owner_cik IS NULL -- those rows stay single-threaded,
    strictly after the CIK-scoped batch commits.

These tests cover:
  1. Correctness under the SQLite StaticPool dialect guard (forces 1
     worker -- proves the new grouped code path is behaviorally identical
     to the old single-session loop).
  2. The specific race the title/CIK grouping exists to prevent: a
     NULL-issuer security "upgrade" contested by multiple known issuers,
     and a NULL-owner_cik fuzzy-name merge -- both must resolve to a
     stable, non-corrupted final state even under real multi-connection
     concurrency.
  3. Structural proof that same-key rows always land on the same worker
     (thread-identity recording), and that independent keys (or rows with
     no possible match state) really do spread across multiple workers.
  4. The default worker count is 16 for company, security, and person.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import Base, MdmPerson, MdmSecurity, get_session
from edgar_warehouse.mdm.migrations.runtime import seed_defaults
from edgar_warehouse.mdm.pipeline import (
    MDMPipeline,
    _COMPANY_RESOLVE_MAX_WORKERS,
    _PERSON_RESOLVE_MAX_WORKERS,
    _SECURITY_RESOLVE_MAX_WORKERS,
)
from edgar_warehouse.mdm.resolvers import PersonResolver, SecurityResolver
from edgar_warehouse.mdm.resolvers.base import ResolverContext
from edgar_warehouse.mdm.rules import MDMRuleEngine

from tests.mdm.test_run_companies_concurrency import StubSilver, _seeded_sqlite_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _security_rows(titles_by_issuer_cik: dict[Optional[int], list[str]]) -> dict[str, list[dict]]:
    """StubSilver fixture for run_securities()'s UNION ALL query.

    ``titles_by_issuer_cik`` maps issuer_cik (or None for "issuer unknown")
    to a list of security titles that issuer's ownership filings mention.
    """
    rows = []
    i = 0
    for issuer_cik, titles in titles_by_issuer_cik.items():
        for title in titles:
            i += 1
            rows.append({
                "accession_number": f"acc-{i}", "owner_index": i, "txn_index": 0,
                "security_title": title, "issuer_cik": issuer_cik, "is_derivative": False,
            })
    return {"sec_ownership_non_derivative_txn": rows, "sec_ownership_derivative_txn": []}


def _person_rows(owner_ciks: list[Optional[int]], name_by_index=None) -> dict[str, list[dict]]:
    rows = []
    for i, owner_cik in enumerate(owner_ciks):
        name = (name_by_index or {}).get(i, f"Person {owner_cik if owner_cik is not None else i}")
        rows.append({
            "owner_cik": owner_cik, "owner_name": name, "officer_title": None,
            "is_director": True, "is_officer": False, "is_ten_percent_owner": False,
            "is_other": False, "accession_number": f"acc-{i}", "owner_index": i,
            "issuer_cik": None,
        })
    return {"sec_ownership_reporting_owner": rows}


def _run_grouped_via_real_threadpool(
    session: Session,
    keyed_rows: list[tuple[Any, Any]],
    process_fn,
    *,
    max_workers: int,
) -> None:
    """Test-only mirror of MDMPipeline._run_grouped_concurrent's grouping
    strategy, WITHOUT its SQLite dialect guard (which forces max_workers=1
    for any sqlite engine, same as run_companies() -- deliberately, see
    pipeline.py). Genuinely testing "does the grouping key prevent a race"
    requires actual multi-threaded execution, so these tests drive the
    resolver directly against a real multi-connection engine, the same way
    TestConcurrentCompanyResolutionSafety in test_run_companies_concurrency
    bypasses run_companies() for the same reason.
    """
    from collections import defaultdict

    groups: dict[Any, list] = defaultdict(list)
    for key, row in keyed_rows:
        groups[key].append(row)

    engine_bind = session.get_bind()

    def _process_group(group_rows: list) -> None:
        worker_session = get_session(engine_bind)
        try:
            for row in group_rows:
                process_fn(worker_session, row)
            worker_session.commit()
        finally:
            worker_session.close()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(_process_group, groups.values()))


def _multi_connection_sqlite_session() -> Session:
    db_path = Path(__import__("tempfile").mkstemp(suffix=".db")[1])
    engine = create_engine(f"sqlite:///{db_path}")

    from datetime import datetime, timezone

    @event.listens_for(engine, "connect")
    def _register_now(dbapi_conn, _record):
        dbapi_conn.create_function("NOW", 0, lambda: datetime.now(timezone.utc).isoformat())

    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_defaults(session)
    session.commit()
    return session


# ---------------------------------------------------------------------------
# 1. run_securities() under SQLite StaticPool (sequential fallback)
# ---------------------------------------------------------------------------

class TestRunSecuritiesSequentialFallback:
    def test_distinct_titles_create_distinct_entities(self):
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _security_rows({111: ["Common Stock"], 222: ["Preferred Stock"], 333: ["Warrant"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        n = pipeline.run_securities()

        assert n == 3
        rows = session.execute(select(MdmSecurity)).scalars().all()
        assert len(rows) == 3
        assert {r.canonical_title for r in rows} == {"Common Stock", "Preferred Stock", "Warrant"}

    def test_same_title_same_known_issuer_dedupes_to_one_entity(self):
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _security_rows({111: ["Common Stock", "Common Stock", "Common Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        n = pipeline.run_securities()

        assert n == 3
        rows = session.execute(select(MdmSecurity)).scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# 2. The race the title/CIK grouping exists to prevent
# ---------------------------------------------------------------------------

class TestNullIssuerUpgradeRaceIsAvoidedByGrouping:
    def test_mixed_known_and_unknown_issuer_same_title_resolves_without_corruption(self):
        """Rows: one unknown-issuer 'Common Stock', then several DIFFERENT
        known issuers also reporting 'Common Stock'. Sequentially, this is
        well-defined: the first known issuer to process upgrades the
        null-issuer entity in place; every other known issuer creates its
        own new entity (the null-match query no longer finds an upgradeable
        NULL-issuer row once one issuer has claimed it). If title-grouping
        were broken (e.g. grouped by (issuer, title) instead), these rows
        could land on different workers and race on that same upgrade,
        risking two issuers colliding onto one entity (real data loss).

        Drives SecurityResolver.resolve_one directly via
        _run_grouped_via_real_threadpool (bypassing run_securities()'s own
        SQLite dialect guard, which forces max_workers=1 for ANY sqlite
        engine regardless of pool type -- deliberately, matching
        run_companies()'s precedent, but that means going through
        run_securities() itself can never exercise genuine concurrency in
        a sqlite-backed test). Run under a REAL multi-connection engine so
        if the grouping were wrong, concurrent workers would have an
        actual chance to race -- with the correct canonical_title-only
        grouping, everything here shares one worker/session and there is
        no race window at all.
        """
        session = _multi_connection_sqlite_session()
        engine_bind = session.get_bind()

        # Seed 3 known companies directly (bypass run_companies() -- only
        # the entity_id lookup matters here).
        from edgar_warehouse.mdm.database import MdmCompany, MdmEntity

        known_cik_entity_ids = {}
        for cik in (111, 222, 333):
            entity = MdmEntity(entity_type="company")
            session.add(entity)
            session.flush()
            session.add(MdmCompany(entity_id=entity.entity_id, cik=cik, canonical_name=f"Co {cik}"))
            known_cik_entity_ids[cik] = entity.entity_id
        session.commit()

        rule_engine = MDMRuleEngine.load(session)
        resolver = SecurityResolver()
        rows = [
            {"security_title": "Common Stock", "issuer_entity_id": None},
            {"security_title": "Common Stock", "issuer_entity_id": known_cik_entity_ids[111]},
            {"security_title": "Common Stock", "issuer_entity_id": known_cik_entity_ids[222]},
            {"security_title": "Common Stock", "issuer_entity_id": known_cik_entity_ids[333]},
        ]
        keyed_rows = [("Common Stock", row) for row in rows]

        def _process(worker_session, row):
            ctx = ResolverContext(session=worker_session, engine=rule_engine, silver=None, run_id="test")
            time.sleep(0.02)  # widen the race window if grouping were broken
            resolver.resolve_one(ctx, "ownership_filing", row, row["issuer_entity_id"])

        _run_grouped_via_real_threadpool(session, keyed_rows, _process, max_workers=4)

        verify_session = Session(engine_bind)
        rows = verify_session.execute(select(MdmSecurity)).scalars().all()
        # Exactly 3 final entities: one per distinct known issuer. The
        # unknown-issuer row's entity got upgraded into one of the three,
        # never survives as a fourth, separate NULL-issuer entity.
        assert len(rows) == 3, f"expected 3 issuer-scoped entities, got {len(rows)}: {[(r.issuer_entity_id, r.canonical_title) for r in rows]}"
        assert None not in {r.issuer_entity_id for r in rows}, "no entity should remain unclaimed (NULL issuer)"
        assert {r.issuer_entity_id for r in rows} == set(known_cik_entity_ids.values())
        verify_session.close()


# ---------------------------------------------------------------------------
# 2b. run_securities()'s grouping-key construction (2026-08-21 fix): a title
#     with NO null-issuer row present splits into per-issuer keys instead of
#     one shared title-only key -- the fix for the throughput collapse a
#     live production investigation found (title-only grouping concentrated
#     53%/27% of one shard's rows into two sequential groups). A title WITH
#     a null-issuer row present must still fall back to the original
#     title-only key, since that's the only case the NULL-issuer "upgrade"
#     race (tested above) can actually happen.
# ---------------------------------------------------------------------------

class TestSecurityGroupingKeyReflectsIssuerWhenSafe:
    def test_different_known_issuers_same_title_get_different_keys(self):
        session = _seeded_sqlite_session(static_pool=True)
        from edgar_warehouse.mdm.database import MdmCompany, MdmEntity

        entity_ids = {}
        for cik in (111, 222):
            entity = MdmEntity(entity_type="company")
            session.add(entity)
            session.flush()
            session.add(MdmCompany(entity_id=entity.entity_id, cik=cik, canonical_name=f"Co {cik}"))
            entity_ids[cik] = entity.entity_id
        session.commit()

        fixtures = _security_rows({111: ["Common Stock"], 222: ["Common Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        captured_keys: list[Any] = []
        real_run_grouped = MDMPipeline._run_grouped_concurrent

        def _capture(self_, keyed_rows, *args, **kwargs):
            captured_keys.extend(key for key, _ in keyed_rows)
            return real_run_grouped(self_, keyed_rows, *args, **kwargs)

        with patch.object(MDMPipeline, "_run_grouped_concurrent", _capture):
            pipeline.run_securities()

        assert len(captured_keys) == 2
        assert len(set(captured_keys)) == 2, f"expected 2 distinct keys, got {captured_keys}"
        assert set(captured_keys) == {
            (entity_ids[111], "Common Stock"),
            (entity_ids[222], "Common Stock"),
        }

    def test_same_known_issuer_same_title_still_shares_one_key(self):
        """The optimization must not stop deduping rows that genuinely
        belong together -- same issuer, same title, still one group."""
        session = _seeded_sqlite_session(static_pool=True)
        from edgar_warehouse.mdm.database import MdmCompany, MdmEntity

        entity = MdmEntity(entity_type="company")
        session.add(entity)
        session.flush()
        session.add(MdmCompany(entity_id=entity.entity_id, cik=111, canonical_name="Co 111"))
        session.commit()
        known_entity_id = entity.entity_id

        fixtures = _security_rows({111: ["Common Stock", "Common Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        captured_keys: list[Any] = []
        real_run_grouped = MDMPipeline._run_grouped_concurrent

        def _capture(self_, keyed_rows, *args, **kwargs):
            captured_keys.extend(key for key, _ in keyed_rows)
            return real_run_grouped(self_, keyed_rows, *args, **kwargs)

        with patch.object(MDMPipeline, "_run_grouped_concurrent", _capture):
            pipeline.run_securities()

        assert captured_keys == [(known_entity_id, "Common Stock"), (known_entity_id, "Common Stock")]

    def test_a_null_issuer_row_forces_title_only_grouping_for_that_title(self):
        """Safety-critical fallback: if ANY row for a title has no resolved
        issuer_entity_id -- whether because issuer_cik itself is NULL, or
        because issuer_cik is a real value that was never bootstrapped as a
        tracked MdmCompany -- every row sharing that title must share ONE
        key, since a shared NULL-issuer entity could exist for them to race
        on upgrading (see TestNullIssuerUpgradeRaceIsAvoidedByGrouping)."""
        session = _seeded_sqlite_session(static_pool=True)
        from edgar_warehouse.mdm.database import MdmCompany, MdmEntity

        entity = MdmEntity(entity_type="company")
        session.add(entity)
        session.flush()
        session.add(MdmCompany(entity_id=entity.entity_id, cik=111, canonical_name="Co 111"))
        session.commit()

        # issuer_cik=999 has no MdmCompany row -> issuer_entity_id resolves
        # to None despite issuer_cik itself being non-null (the untracked-
        # issuer case commit 86baa4b6 fixed the join gap for).
        fixtures = _security_rows({111: ["Common Stock"], 999: ["Common Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        captured_keys: list[Any] = []
        real_run_grouped = MDMPipeline._run_grouped_concurrent

        def _capture(self_, keyed_rows, *args, **kwargs):
            captured_keys.extend(key for key, _ in keyed_rows)
            return real_run_grouped(self_, keyed_rows, *args, **kwargs)

        with patch.object(MDMPipeline, "_run_grouped_concurrent", _capture):
            pipeline.run_securities()

        assert len(captured_keys) == 2
        assert captured_keys[0] == captured_keys[1] == "Common Stock", (
            f"expected both rows to share the title-only fallback key, got {captured_keys}"
        )


class TestDifferentIssuersSameTitleResolveConcurrentlyWithoutCorruption:
    def test_distinct_known_issuers_sharing_a_title_each_get_their_own_entity_under_real_concurrency(self):
        """Proves the new (issuer_entity_id, title) sub-grouping is safe
        under genuine concurrent execution, not just sequentially: several
        known issuers reporting the same generic title (e.g. "Common
        Stock") resolve on DIFFERENT worker threads simultaneously and each
        still gets its own correct, uncorrupted entity. This is the actual
        throughput fix: live production data showed titles like this
        concentrating 53%/27% of a shard's rows into ONE sequential group
        under the old canonical_title-only grouping.

        Drives the resolver directly via _run_grouped_via_real_threadpool
        (same reason as TestNullIssuerUpgradeRaceIsAvoidedByGrouping --
        run_securities()'s own SQLite dialect guard forces max_workers=1
        for any sqlite engine regardless of pool type, so genuine
        concurrency can't be exercised by calling run_securities() itself
        in this test suite)."""
        session = _multi_connection_sqlite_session()
        rule_engine = MDMRuleEngine.load(session)
        resolver = SecurityResolver()

        from edgar_warehouse.mdm.database import MdmCompany, MdmEntity

        entity_ids = {}
        for cik in range(10):
            entity = MdmEntity(entity_type="company")
            session.add(entity)
            session.flush()
            session.add(MdmCompany(entity_id=entity.entity_id, cik=cik, canonical_name=f"Co {cik}"))
            entity_ids[cik] = entity.entity_id
        session.commit()

        rows = [
            {"security_title": "Common Stock", "issuer_entity_id": entity_ids[cik]}
            for cik in range(10)
        ]
        # Mirrors run_securities()'s new key construction: no null-issuer
        # row present for this title, so each row gets its own key.
        keyed_rows = [((row["issuer_entity_id"], "Common Stock"), row) for row in rows]

        seen: dict[Any, set[int]] = {}
        lock = threading.Lock()

        def _process(worker_session, row):
            with lock:
                seen.setdefault(row["issuer_entity_id"], set()).add(threading.get_ident())
            time.sleep(0.02)  # widen the window for genuine overlap to show up
            ctx = ResolverContext(session=worker_session, engine=rule_engine, silver=None, run_id="test")
            resolver.resolve_one(ctx, "ownership_filing", row, row["issuer_entity_id"])

        _run_grouped_via_real_threadpool(session, keyed_rows, _process, max_workers=10)

        all_idents = {ident for idents in seen.values() for ident in idents}
        assert len(all_idents) > 1, "expected genuine parallelism across distinct issuers"

        verify_session = Session(session.get_bind())
        securities = verify_session.execute(select(MdmSecurity)).scalars().all()
        assert len(securities) == 10, (
            f"expected 10 distinct entities (one per issuer), got {len(securities)}"
        )
        assert {s.issuer_entity_id for s in securities} == set(entity_ids.values())
        verify_session.close()


class TestPersonUnscopedFuzzyMergeStaysCorrect:
    def test_null_owner_cik_near_duplicate_names_merge_to_one_entity(self):
        """Two owner_cik=IS NULL rows with the identical normalized name
        must fuzzy-merge into one person entity. This only holds reliably
        if the unscoped subset runs strictly sequentially (concurrent
        workers could each miss the other's still-uncommitted create and
        both insert a new entity)."""
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _person_rows(
            [None, None, None],
            name_by_index={0: "Jane Q Doe", 1: "Jane Q Doe", 2: "Jane Q Doe"},
        )
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        n = pipeline.run_persons()

        assert n == 3
        rows = session.execute(select(MdmPerson)).scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# 3. Structural proof: same-key rows share a worker; independent rows spread
# ---------------------------------------------------------------------------

class TestSecurityTitleGroupingSharesOneWorkerPerTitle:
    def test_all_rows_for_one_title_run_on_the_same_thread(self):
        """Drives the resolver via _run_grouped_via_real_threadpool
        (bypassing run_securities()'s SQLite dialect guard -- see the
        docstring on TestNullIssuerUpgradeRaceIsAvoidedByGrouping) so real
        multi-threaded execution actually happens against this sqlite
        engine, and records which thread handled each title."""
        session = _multi_connection_sqlite_session()
        rule_engine = MDMRuleEngine.load(session)
        resolver = SecurityResolver()

        rows = []
        for t in range(6):
            for _ in range(4):
                rows.append({"security_title": f"Title {t}", "issuer_entity_id": None})
        keyed_rows = [(row["security_title"], row) for row in rows]

        seen: dict[str, set[int]] = {}
        lock = threading.Lock()

        def _process(worker_session, row):
            with lock:
                seen.setdefault(row["security_title"], set()).add(threading.get_ident())
            # Real workload here is trivial in-memory SQLite work -- fast
            # enough that ThreadPoolExecutor could service every group off
            # one already-idle worker without ever spinning up a second,
            # which would make the "genuine parallelism happened" check
            # below flaky. A tiny synthetic delay gives concurrent groups
            # an actual window to overlap.
            time.sleep(0.02)
            ctx = ResolverContext(session=worker_session, engine=rule_engine, silver=None, run_id="test")
            resolver.resolve_one(ctx, "ownership_filing", row, row["issuer_entity_id"])

        _run_grouped_via_real_threadpool(session, keyed_rows, _process, max_workers=6)

        assert len(seen) == 6
        for title, idents in seen.items():
            assert len(idents) == 1, f"title {title!r} was processed by {len(idents)} different threads"
        # And real parallelism actually happened across titles.
        all_idents = {ident for idents in seen.values() for ident in idents}
        assert len(all_idents) > 1, "expected more than one worker thread across distinct titles"


class TestPersonCikGroupingSharesOneWorkerPerCik:
    def test_all_rows_for_one_owner_cik_run_on_the_same_thread(self):
        """Drives PersonResolver directly via _run_grouped_via_real_threadpool
        for the same reason as the security-title equivalent above."""
        session = _multi_connection_sqlite_session()
        rule_engine = MDMRuleEngine.load(session)
        resolver = PersonResolver()

        rows = []
        i = 0
        for cik in range(2000, 2006):
            for _ in range(4):
                i += 1
                rows.append({
                    "owner_cik": cik, "owner_name": f"Person {cik}", "officer_title": None,
                    "is_director": True, "is_officer": False, "is_ten_percent_owner": False,
                    "is_other": False, "accession_number": f"acc-{i}", "owner_index": i,
                })
        keyed_rows = [(row["owner_cik"], row) for row in rows]

        seen: dict[int, set[int]] = {}
        lock = threading.Lock()

        def _process(worker_session, row):
            with lock:
                seen.setdefault(row["owner_cik"], set()).add(threading.get_ident())
            time.sleep(0.02)  # see comment in the security-title equivalent above
            ctx = ResolverContext(session=worker_session, engine=rule_engine, silver=None, run_id="test")
            resolver.resolve_one(ctx, "ownership_filing", row, issuer_cik=None)

        _run_grouped_via_real_threadpool(session, keyed_rows, _process, max_workers=6)

        assert len(seen) == 6
        for cik, idents in seen.items():
            assert len(idents) == 1, f"owner_cik {cik} was processed by {len(idents)} different threads"
        all_idents = {ident for idents in seen.values() for ident in idents}
        assert len(all_idents) > 1, "expected more than one worker thread across distinct owner_ciks"


class TestEmptyTitleSecurityRowsDoNotSpuriouslyDedupe:
    def test_rows_with_no_title_each_get_their_own_entity(self):
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _security_rows({111: ["", "", ""]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        n = pipeline.run_securities()

        assert n == 3
        rows = session.execute(select(MdmSecurity)).scalars().all()
        assert len(rows) == 3, "empty-title rows never dedup -- each row must create its own entity"


# ---------------------------------------------------------------------------
# 4. Default worker count
# ---------------------------------------------------------------------------

class TestDefaultConcurrencyIsSixteen:
    def test_company_security_person_all_default_to_sixteen(self):
        assert _COMPANY_RESOLVE_MAX_WORKERS == 16
        assert _SECURITY_RESOLVE_MAX_WORKERS == 16
        assert _PERSON_RESOLVE_MAX_WORKERS == 16


# ---------------------------------------------------------------------------
# 5. Partial-failure propagation (mirrors run_companies' equivalent test)
# ---------------------------------------------------------------------------

class TestRunSecuritiesPartialFailure:
    def test_a_raising_row_propagates_not_swallowed(self):
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _security_rows({111: ["Common Stock"]})
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        with patch(
            "edgar_warehouse.mdm.pipeline.SecurityResolver.resolve_one",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                pipeline.run_securities()


class TestRunPersonsPartialFailure:
    def test_a_raising_row_propagates_not_swallowed(self):
        session = _seeded_sqlite_session(static_pool=True)
        fixtures = _person_rows([555])
        pipeline = MDMPipeline(session=session, silver=StubSilver(fixtures))

        with patch(
            "edgar_warehouse.mdm.pipeline.PersonResolver.resolve_one",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                pipeline.run_persons()
