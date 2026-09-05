"""release-readiness Ticket 100 / fundamentals-daily-integration map Ticket
06: resolve_advisers_bulk/resolve_funds_bulk (adv_bulk.py) previously
plateaued on the same first `limit` rows on every repeated call -- the
identical shape release-readiness Ticket 94 already found and fixed for
MDMPipeline.run_companies. Confirmed live: daily_incremental's daily
`mdm mastering --entity-type all --limit 100` call forwards that exact
limit into run_advisers(limit=100)/run_funds(limit=100), so this fires
every day, not just theoretically.

Uses a real SilverDatabase-backed DuckDB file (not the substring-matched
_AdviserSilver/_FundSilver stubs used in test_adv_bulk_resolution.py)
deliberately: those stubs ignore the SQL string's LIMIT/ORDER BY entirely
and always return every fixture row regardless -- they cannot distinguish
a plateaued call from a progressing one, so a stub-based test would pass
whether or not the underlying bug existed (the same "stub silently mirrors
a bug instead of the real schema" trap CLAUDE.md's INSTITUTIONAL_HOLDS
incident already documents for this codebase). A real DuckDB LIMIT/ORDER
BY genuinely executes here, so these tests can actually go red on the bug
they exist to catch.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

from sqlalchemy import func, select

from edgar_warehouse.mdm.database import MdmAdviser, MdmFund
from edgar_warehouse.mdm.pipeline import MDMPipeline
from edgar_warehouse.silver_store import SilverDatabase

from tests.mdm.test_run_companies_concurrency import _seeded_sqlite_session


def _real_silver_with_advisers(n: int) -> SilverDatabase:
    tmpdir = tempfile.mkdtemp()
    silver_path = os.path.join(tmpdir, "silver.duckdb")
    db = SilverDatabase(silver_path)
    for i in range(n):
        db._conn.execute(
            "INSERT INTO sec_adv_filing "
            "(accession_number, cik, form, adviser_name, sec_file_number, "
            "crd_number, effective_date, filing_status) "
            "VALUES (?, ?, 'ADV', ?, ?, ?, ?, 'registered')",
            [
                f"adv-{i:05d}",
                900000 + i,
                f"Adviser {i}",
                f"801-{i}",
                str(50000 + i),
                date(2026, 6, 30),
            ],
        )
    db.close()
    return SilverDatabase(silver_path)


def _real_silver_with_funds(n: int) -> SilverDatabase:
    tmpdir = tempfile.mkdtemp()
    silver_path = os.path.join(tmpdir, "silver.duckdb")
    db = SilverDatabase(silver_path)
    for i in range(n):
        db._conn.execute(
            "INSERT INTO sec_adv_private_fund "
            "(accession_number, fund_index, private_fund_id, adviser_crd_number, "
            "fund_name, fund_type, jurisdiction, aum_amount, effective_date) "
            "VALUES (?, 0, ?, ?, ?, 'hedge', 'DE', ?, ?)",
            [
                f"adv-fund-{i:05d}",
                f"PF-{i:05d}",
                str(60000 + i),
                f"Fund {i}",
                1_000_000 + i,
                date(2026, 6, 30),
            ],
        )
    db.close()
    return SilverDatabase(silver_path)


def _pipeline(session, silver) -> MDMPipeline:
    pipeline = MDMPipeline(session=session, silver=silver)
    pipeline.engine._source_priority[("adviser", "adv_filing")] = 30
    pipeline.engine._source_priority[("fund", "adv_filing")] = 30
    return pipeline


class TestAdviserBoundedLimitMakesCumulativeProgress:
    def test_repeated_calls_with_same_limit_eventually_resolve_the_whole_universe(self) -> None:
        """3 calls with limit=2 against a 5-adviser universe must resolve
        all 5 -- not plateau at the same first 2 forever. This is the exact
        shape daily_incremental hits in prod: `mdm mastering --entity-type
        all --limit 100`, invoked every day with no exclusion of
        already-resolved CRDs."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_advisers(5)
        pipeline = _pipeline(session, silver)

        processed_1 = pipeline.run_advisers(limit=2)
        processed_2 = pipeline.run_advisers(limit=2)
        processed_3 = pipeline.run_advisers(limit=2)

        assert processed_1 == 2
        assert processed_2 == 2
        assert processed_3 == 1  # only 1 CRD remained after 2 + 2

        resolved_crds = {
            row.crd_number for row in session.execute(select(MdmAdviser)).scalars().all()
        }
        assert resolved_crds == {str(50000 + i) for i in range(5)}

    def test_a_single_bounded_call_resolves_at_most_limit_new_advisers(self) -> None:
        """The bounded-cost contract must still hold: a single call to a
        10-adviser universe with limit=3 resolves exactly 3, not the whole
        universe -- the over-fetch window that fixes the plateau must not
        silently uncap the real per-call resolution work."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_advisers(10)
        pipeline = _pipeline(session, silver)

        processed = pipeline.run_advisers(limit=3)

        assert processed == 3
        assert session.scalar(select(func.count()).select_from(MdmAdviser)) == 3

    def test_already_fully_resolved_adviser_universe_processes_nothing_further(self) -> None:
        """Once every adviser is resolved, a further bounded call must find
        zero new candidates (not error, not re-process) -- the over-fetch
        window growing past `existing` must terminate cleanly rather than
        looping or over-fetching unboundedly."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_advisers(3)
        pipeline = _pipeline(session, silver)

        pipeline.run_advisers(limit=10)  # resolves all 3 in one call
        processed_after = pipeline.run_advisers(limit=10)

        assert processed_after == 0

    def test_latest_filing_still_wins_under_a_bounded_window(self) -> None:
        """The new ORDER BY crd_number must not break _latest_by_identity's
        "latest filing wins" semantics -- a CRD with two filing rows in the
        fetched window still resolves to the more recent one's data."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_advisers(1)
        silver._conn.execute(
            "INSERT INTO sec_adv_filing "
            "(accession_number, cik, form, adviser_name, sec_file_number, "
            "crd_number, effective_date, filing_status) "
            "VALUES ('adv-00000-amended', 900000, 'ADV', 'Adviser 0 Renamed', "
            "'801-0', ?, ?, 'registered')",
            [str(50000), date(2026, 9, 30)],
        )

        pipeline = _pipeline(session, silver)
        assert pipeline.run_advisers(limit=10) == 1
        adviser = session.scalar(select(MdmAdviser))
        assert adviser.canonical_name == "Adviser 0 Renamed"


class TestFundBoundedLimitMakesCumulativeProgress:
    def test_repeated_calls_with_same_limit_eventually_resolve_the_whole_universe(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_funds(5)
        pipeline = _pipeline(session, silver)

        processed_1 = pipeline.run_funds(limit=2)
        processed_2 = pipeline.run_funds(limit=2)
        processed_3 = pipeline.run_funds(limit=2)

        assert processed_1 == 2
        assert processed_2 == 2
        assert processed_3 == 1

        resolved_pfids = {
            row.private_fund_id for row in session.execute(select(MdmFund)).scalars().all()
        }
        assert resolved_pfids == {f"PF-{i:05d}" for i in range(5)}

    def test_a_single_bounded_call_resolves_at_most_limit_new_funds(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_funds(10)
        pipeline = _pipeline(session, silver)

        processed = pipeline.run_funds(limit=3)

        assert processed == 3
        assert session.scalar(select(func.count()).select_from(MdmFund)) == 3

    def test_already_fully_resolved_fund_universe_processes_nothing_further(self) -> None:
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_funds(3)
        pipeline = _pipeline(session, silver)

        pipeline.run_funds(limit=10)
        processed_after = pipeline.run_funds(limit=10)

        assert processed_after == 0

    def test_latest_filing_still_wins_under_a_bounded_window(self) -> None:
        """The new ORDER BY private_fund_id must not break
        _latest_by_identity's "latest filing wins" semantics -- a pfid with
        two filing rows in the fetched window still resolves to the more
        recent one's data. Fund-side companion to
        TestAdviserBoundedLimitMakesCumulativeProgress's equivalent test.

        Asserts on fund_type/aum_amount rather than canonical_name: unlike
        adviser_name, fund_name runs through MDMRuleEngine.normalize_name's
        legal-suffix stripping, which drops the literal word "Fund" -- a
        name-based assertion here would be testing normalization, not
        latest-wins ordering.
        """
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_funds(1)
        silver._conn.execute(
            "INSERT INTO sec_adv_private_fund "
            "(accession_number, fund_index, private_fund_id, adviser_crd_number, "
            "fund_name, fund_type, jurisdiction, aum_amount, effective_date) "
            "VALUES ('adv-fund-00000-amended', 0, ?, ?, ?, "
            "'private_equity', 'DE', 2000000, ?)",
            [f"PF-{0:05d}", str(60000), f"Renamed {0}", date(2026, 9, 30)],
        )

        pipeline = _pipeline(session, silver)
        assert pipeline.run_funds(limit=10) == 1
        fund = session.scalar(select(MdmFund))
        assert fund.fund_type == "private_equity"
        assert fund.aum_amount == 2000000
