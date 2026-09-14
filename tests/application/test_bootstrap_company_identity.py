"""bootstrap-fundamentals --mode company-identity: end-to-end local test.

Proves the new mode stages company master identity into silver (sec_company,
sec_company_ticker) via the existing form-agnostic submissions staging path,
while touching zero ownership/ADV artifacts or tables -- the whole point of
decoupling company identity from ownership at the Bronze/Silver layer.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pyarrow.parquet as pq
import pytest

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.commands import bootstrap_fundamentals
from tests.support.bookkeeping_fixtures import bookkeeping_fixture

CIK = 320193

_SUBMISSIONS_PAYLOAD = {
    "cik": "0000320193",
    "name": "APPLE INC",
    "entityType": "operating",
    "sic": "3571",
    "sicDescription": "Electronic Computers",
    "stateOfIncorporation": "CA",
    "fiscalYearEnd": "0930",
    "ein": "942404110",
    "addresses": {"business": {}, "mailing": {}},
    "formerNames": [],
    "filings": {"recent": {}, "files": []},
}

_COMPANY_TICKERS_EXCHANGE_PAYLOAD = {
    "fields": ["cik", "name", "ticker", "exchange"],
    "data": [[CIK, "Apple Inc.", "AAPL", "Nasdaq"]],
}


def _fake_download_sec_bytes(*, url: str, identity: str) -> bytes:
    if "submissions/CIK" in url:
        return json.dumps(_SUBMISSIONS_PAYLOAD).encode("utf-8")
    if "company_tickers_exchange" in url:
        return json.dumps(_COMPANY_TICKERS_EXCHANGE_PAYLOAD).encode("utf-8")
    if "company_tickers.json" in url:
        return json.dumps({}).encode("utf-8")
    raise AssertionError(f"unexpected SEC download in company-identity mode: {url}")


@pytest.fixture(autouse=True)
def _stub_sec_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        warehouse_orchestrator, "_download_sec_bytes", _fake_download_sec_bytes
    )
    monkeypatch.setattr(
        bootstrap_fundamentals, "_bookkeeping_store", lambda: bookkeeping_fixture()
    )


def test_company_identity_mode_stages_company_and_ticker_only(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage_root = tmp_path / "warehouse"
    landing_root = tmp_path / "landing"
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Test test@example.com")
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("SILVER_LANDING_EXPORT_ROOT", str(landing_root))
    monkeypatch.delenv("WAREHOUSE_BRONZE_ROOT", raising=False)
    monkeypatch.delenv("WAREHOUSE_SILVER_ROOT", raising=False)

    args = SimpleNamespace(
        cik_list=[CIK],
        mode="company-identity",
        run_id="test-company-identity-run",
        silver_root=None,
        release_mode=False,
        candidate_manifest=None,
        cik_offset=0,
        cik_limit=None,
        force=False,
    )

    exit_code = bootstrap_fundamentals.execute(args)
    assert exit_code == 0

    from edgar_warehouse.silver_support.session import open_silver_database
    from edgar_warehouse.infrastructure.object_storage import StorageLocation

    db = open_silver_database(StorageLocation(str(storage_root)))
    try:
        ticker_rows = db.fetch(
            "SELECT * FROM sec_company_ticker WHERE cik = ?", [CIK]
        )
        assert any(row["ticker"] == "AAPL" for row in ticker_rows)

        # Zero ownership/ADV artifacts touched is the whole point of this mode,
        # but the ownership trio, sec_adv_filing and sec_thirteenf_holding are
        # landing-only (silver-merge-engine-migration Tickets 05/06a/06c): an
        # empty local DuckDB table no longer proves they were untouched, so
        # the landing export is checked below instead.
    finally:
        db.close()

    # sec_company is landing-only (silver-merge-engine-migration Ticket 06b):
    # the company row reaches silver through the landing export this command
    # flushes, so read it back from the Parquet it wrote.
    company_files = [
        path for path in landing_root.rglob("*.parquet") if "/sec_company/" in path.as_posix()
    ]
    assert len(company_files) == 1, "expected exactly one sec_company landing Parquet"
    company_rows = pq.read_table(company_files[0]).to_pylist()
    assert [(row["cik"], row["entity_name"], row["sic"]) for row in company_rows] == [
        (CIK, "APPLE INC", "3571")
    ]
    untouched_tables = ("/sec_ownership_", "/sec_adv_", "/sec_thirteenf_")
    assert not [
        path
        for path in landing_root.rglob("*.parquet")
        if any(table in path.as_posix() for table in untouched_tables)
    ], "company-identity mode must not land any ownership, ADV or 13F rows"


def test_company_identity_mode_rejects_release_mode() -> None:
    args = SimpleNamespace(
        cik_list=[CIK],
        mode="company-identity",
        run_id="test-run",
        silver_root=None,
        release_mode=True,
        candidate_manifest="s3://bucket/manifest.json",
        cik_offset=0,
        cik_limit=None,
        force=False,
    )
    assert bootstrap_fundamentals.execute(args) == 2


def test_company_identity_with_explicit_cik_list_skips_full_hydrate(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit --cik-list never reads db.get_tracked_ciks(), and (DuckDB
    Retirement Cutover Ticket 10) canonical silver.duckdb is no longer a
    write/hydrate target for any command at all -- see
    _publish_silver_database_if_remote's docstring.
    """
    storage_root = tmp_path / "warehouse"
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Test test@example.com")
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(storage_root))
    monkeypatch.delenv("WAREHOUSE_BRONZE_ROOT", raising=False)
    monkeypatch.delenv("WAREHOUSE_SILVER_ROOT", raising=False)

    hydrate_calls: list[object] = []
    monkeypatch.setattr(
        warehouse_orchestrator,
        "_hydrate_silver_database_from_storage",
        lambda context: hydrate_calls.append(context),
    )

    args = SimpleNamespace(
        cik_list=[CIK],
        mode="company-identity",
        run_id="test-skip-hydrate-run",
        silver_root=None,
        release_mode=False,
        candidate_manifest=None,
        cik_offset=0,
        cik_limit=None,
        force=False,
    )

    exit_code = bootstrap_fundamentals.execute(args)
    assert exit_code == 0
    assert hydrate_calls == []


def test_company_identity_without_cik_list_also_skips_hydrate(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without an explicit --cik-list (the windowed Step Functions Map case),
    _resolve_fundamentals_ciks falls back to bookkeeping.get_tracked_ciks()
    -- Postgres, not this local DuckDB `db` connection (DuckDB Retirement
    Cutover Ticket 14 repointed it there). DuckDB Retirement Cutover Ticket
    10 then removed hydration for this call site entirely: there is no
    local-DB dependency left to justify it, and canonical silver.duckdb is
    no longer a write target for any command (see
    _publish_silver_database_if_remote's docstring).
    """
    storage_root = tmp_path / "warehouse"
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Test test@example.com")
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(storage_root))
    monkeypatch.delenv("WAREHOUSE_BRONZE_ROOT", raising=False)
    monkeypatch.delenv("WAREHOUSE_SILVER_ROOT", raising=False)

    hydrate_calls: list[object] = []
    monkeypatch.setattr(
        warehouse_orchestrator,
        "_hydrate_silver_database_from_storage",
        lambda context: hydrate_calls.append(context),
    )

    args = SimpleNamespace(
        cik_list=None,
        mode="company-identity",
        run_id="test-windowed-hydrate-run",
        silver_root=None,
        release_mode=False,
        candidate_manifest=None,
        cik_offset=0,
        cik_limit=None,
        force=False,
    )

    bootstrap_fundamentals.execute(args)
    assert hydrate_calls == []
