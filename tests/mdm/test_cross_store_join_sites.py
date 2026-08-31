"""DuckDB Retirement Cutover Ticket 13: rewritten cross-store join sites.

sec_company_sync_state moved off DuckDB silver onto the bookkeeping store's
Postgres database, so the 4 sites that used to JOIN it against a DuckDB
silver table in one SQL statement can no longer do so -- each now fetches
its own side separately and joins/intersects in Python. These tests cover
the two sites that don't already have dedicated coverage elsewhere:

  1. edgar_warehouse.mdm.coverage.compute_coverage's company-domain count
     (get_company_identity_ciks's own rewrite is covered directly in
     tests/unit/test_identity_refresh_window.py).
  2. edgar_warehouse.mdm.cli._seed_mdm_from_silver_ticker_fallback.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.bookkeeping.database import Base as BookkeepingBase
from edgar_warehouse.bookkeeping.store import BookkeepingStore
from edgar_warehouse.mdm.database import Base, MdmCompany
from edgar_warehouse.mdm.migrations.runtime import seed_defaults


@pytest.fixture()
def bookkeeping() -> BookkeepingStore:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BookkeepingBase.metadata.create_all(engine)
    with Session(engine) as session:
        yield BookkeepingStore(session)


@pytest.fixture()
def mdm_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_defaults(session)
        session.commit()
        yield session


class _StubSilverReader:
    """Returns canned rows keyed by a substring of the SQL, like the other
    StubSilver fixtures in this test package."""

    def __init__(self, fixtures: dict[str, list[dict]]):
        self._fixtures = fixtures

    def fetch(self, sql: str, params: Optional[list[Any]] = None) -> list[dict]:
        matched: list[dict] = []
        for needle, rows in self._fixtures.items():
            if needle in sql:
                matched.extend(rows)
        return matched


class TestComputeCoverageCompanyDomain:
    def test_company_silver_count_is_intersection_of_silver_and_active_tracked(
        self, mdm_session, bookkeeping
    ) -> None:
        from edgar_warehouse.mdm.coverage import compute_coverage

        reader = _StubSilverReader({
            "FROM sec_company": [{"cik": 1}, {"cik": 2}, {"cik": 3}],
        })
        bookkeeping.upsert_company_sync_state({"cik": 1, "tracking_status": "active"})
        bookkeeping.upsert_company_sync_state({"cik": 2, "tracking_status": "paused"})
        bookkeeping.upsert_company_sync_state({"cik": 4, "tracking_status": "active"})

        rows = compute_coverage(reader, mdm_session, bookkeeping)

        company_row = next(r for r in rows if r["domain"] == "companies")
        # Only cik=1 is both present in silver's sec_company AND active in
        # bookkeeping -- cik=2 is silver-present but paused, cik=3 is
        # silver-present but untracked, cik=4 is active but not in silver.
        assert company_row["silver_count"] == 1

    def test_company_mdm_count_matches_real_mdm_company_rows(
        self, mdm_session, bookkeeping
    ) -> None:
        from edgar_warehouse.mdm.coverage import compute_coverage

        reader = _StubSilverReader({"FROM sec_company": []})
        mdm_session.add(MdmCompany(
            entity_id="e-1", cik=1, canonical_name="Test Co",
        ))
        mdm_session.commit()

        rows = compute_coverage(reader, mdm_session, bookkeeping)

        company_row = next(r for r in rows if r["domain"] == "companies")
        assert company_row["mdm_count"] == 1


class TestSeedMdmFromSilverTickerFallback:
    """DuckDB Retirement Cutover Ticket 05: _seed_mdm_from_silver_ticker_fallback
    reads via reader.fetch() now, not reader._conn.execute() -- SnowflakeSilverReader
    deliberately doesn't expose ._conn at all (see its own module docstring)."""

    class _FakeTickerReader:
        def __init__(self, rows: list[tuple]) -> None:
            self._rows = rows

        def fetch(self, sql, params=None):
            assert "sec_company_ticker" in sql
            return [{"cik": cik, "ticker": ticker, "exchange": exchange} for cik, ticker, exchange in self._rows]

    def test_defaults_missing_tracking_status_to_active(self, bookkeeping) -> None:
        import edgar_warehouse.mdm.cli as mdm_cli

        reader = self._FakeTickerReader([(100, "ABC", "NASDAQ")])

        rows = mdm_cli._seed_mdm_from_silver_ticker_fallback(reader, None, bookkeeping)

        assert rows == [(100, "ABC", "NASDAQ", "active")]

    def test_falsy_stored_status_is_not_overridden_to_active(self, bookkeeping) -> None:
        """DuckDB Retirement Cutover Ticket 13 spec: only *missing* CIKs default
        to "active" (`.get(cik, "active")`) -- a present-but-falsy stored value
        (e.g. empty string) must be returned as-is, not silently coerced."""
        import edgar_warehouse.mdm.cli as mdm_cli

        bookkeeping.upsert_company_sync_state({"cik": 100, "tracking_status": ""})

        reader = self._FakeTickerReader([(100, "ABC", "NASDAQ")])

        rows = mdm_cli._seed_mdm_from_silver_ticker_fallback(reader, None, bookkeeping)

        assert rows == [(100, "ABC", "NASDAQ", "")]

    def test_uses_real_tracking_status_from_bookkeeping(self, bookkeeping) -> None:
        import edgar_warehouse.mdm.cli as mdm_cli

        bookkeeping.upsert_company_sync_state({"cik": 100, "tracking_status": "paused"})

        reader = self._FakeTickerReader([(100, "ABC", "NASDAQ")])

        rows = mdm_cli._seed_mdm_from_silver_ticker_fallback(reader, None, bookkeeping)

        assert rows == [(100, "ABC", "NASDAQ", "paused")]

    def test_tracking_status_filter_excludes_non_matching_rows(self, bookkeeping) -> None:
        import edgar_warehouse.mdm.cli as mdm_cli

        bookkeeping.upsert_company_sync_state({"cik": 100, "tracking_status": "active"})
        bookkeeping.upsert_company_sync_state({"cik": 200, "tracking_status": "paused"})

        reader = self._FakeTickerReader([(100, "ABC", "NASDAQ"), (200, "XYZ", "NYSE")])

        rows = mdm_cli._seed_mdm_from_silver_ticker_fallback(reader, "active", bookkeeping)

        assert rows == [(100, "ABC", "NASDAQ", "active")]
