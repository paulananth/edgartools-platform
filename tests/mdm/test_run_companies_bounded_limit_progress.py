"""release-readiness ticket 94: run_companies(limit=N, no resume) previously
plateaued on the same first N rows on every repeated call instead of making
cumulative progress -- exactly the plateau shape _bounded_relationship_sql's
docstring already documents and fixes for relationship-derivation's own
source query, but never ported to company resolution itself.

Uses a real SilverDatabase-backed DuckDB file (not the substring-matched
StubSilver used elsewhere in this test package) deliberately: StubSilver's
`fetch()` ignores both the SQL string's LIMIT/ORDER BY and any params,
always returning every row matching a fixture-dict substring key -- it
cannot distinguish a plateaued call from a progressing one, so a StubSilver-
based test would pass whether or not the underlying bug existed (the same
"stub silently mirrors a bug instead of the real schema" trap CLAUDE.md's
INSTITUTIONAL_HOLDS incident already documents for this codebase). A real
DuckDB LIMIT/ORDER BY genuinely executes here, so this test can actually go
red on the bug it exists to catch.
"""
from __future__ import annotations

import os
import tempfile

from sqlalchemy import select

from edgar_warehouse.mdm.database import MdmCompany
from edgar_warehouse.mdm.pipeline import MDMPipeline
from edgar_warehouse.silver_store import SilverDatabase

from tests.mdm.test_run_companies_concurrency import _seeded_sqlite_session, _StubBookkeeping


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


class TestBoundedLimitMakesCumulativeProgress:
    def test_repeated_calls_with_same_limit_eventually_resolve_the_whole_universe(self) -> None:
        """3 calls with limit=2 against a 5-company universe must resolve all
        5 -- not plateau at the same first 2 forever. This is the exact
        shape load_history/daily_incremental/bootstrap/mdm_gold hit in prod:
        `mdm run --entity-type all --limit 100` (or --limit 200 for
        sync-graph's sibling case), invoked repeatedly with no
        --resume-ledger-run-id."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_companies(5)
        pipeline = MDMPipeline(session=session, silver=silver)

        processed_1 = pipeline.run_companies(limit=2, bookkeeping=_StubBookkeeping())
        processed_2 = pipeline.run_companies(limit=2, bookkeeping=_StubBookkeeping())
        processed_3 = pipeline.run_companies(limit=2, bookkeeping=_StubBookkeeping())

        assert processed_1 == 2
        assert processed_2 == 2
        assert processed_3 == 1  # only 1 CIK remained after 2 + 2

        resolved_ciks = {
            row.cik for row in session.execute(select(MdmCompany)).scalars().all()
        }
        assert resolved_ciks == {900000, 900001, 900002, 900003, 900004}

    def test_a_single_bounded_call_resolves_at_most_limit_new_companies(self) -> None:
        """The bounded-cost contract must still hold: a single call to a
        10-company universe with limit=3 resolves exactly 3, not the whole
        universe -- the over-fetch window that fixes the plateau must not
        silently uncap the real per-call resolution work."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_companies(10)
        pipeline = MDMPipeline(session=session, silver=silver)

        processed = pipeline.run_companies(limit=3, bookkeeping=_StubBookkeeping())

        assert processed == 3
        resolved_ciks = {
            row.cik for row in session.execute(select(MdmCompany)).scalars().all()
        }
        assert len(resolved_ciks) == 3

    def test_already_fully_resolved_universe_processes_nothing_further(self) -> None:
        """Once every company is resolved, a further bounded call must find
        zero new candidates (not error, not re-process) -- the over-fetch
        window growing past `existing` must terminate cleanly rather than
        looping or over-fetching unboundedly."""
        session = _seeded_sqlite_session(static_pool=True)
        silver = _real_silver_with_companies(3)
        pipeline = MDMPipeline(session=session, silver=silver)

        pipeline.run_companies(limit=10, bookkeeping=_StubBookkeeping())  # resolves all 3 in one call
        processed_after = pipeline.run_companies(limit=10, bookkeeping=_StubBookkeeping())

        assert processed_after == 0
