"""bootstrap-fundamentals --mode company-identity: end-to-end local test.

Proves the new mode stages company master identity into silver (sec_company,
sec_company_ticker) via the existing form-agnostic submissions staging path,
while touching zero ownership/ADV artifacts or tables -- the whole point of
decoupling company identity from ownership at the Bronze/Silver layer.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.commands import bootstrap_fundamentals

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


def test_company_identity_mode_stages_company_and_ticker_only(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage_root = tmp_path / "warehouse"
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Test test@example.com")
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(storage_root))
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
        company = db.get_company(CIK)
        assert company is not None
        assert company["entity_name"] == "APPLE INC"
        assert company["sic"] == "3571"

        ticker_rows = db.fetch(
            "SELECT * FROM sec_company_ticker WHERE cik = ?", [CIK]
        )
        assert any(row["ticker"] == "AAPL" for row in ticker_rows)

        # Zero ownership/ADV artifacts touched -- the whole point of this mode.
        ownership_rows = db.fetch(
            "SELECT * FROM sec_ownership_reporting_owner WHERE 1=1"
        )
        assert ownership_rows == []
        adv_rows = db.fetch("SELECT * FROM sec_adv_filing WHERE 1=1")
        assert adv_rows == []
        thirteenf_rows = db.fetch("SELECT * FROM sec_thirteenf_holding WHERE 1=1")
        assert thirteenf_rows == []
    finally:
        db.close()


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
