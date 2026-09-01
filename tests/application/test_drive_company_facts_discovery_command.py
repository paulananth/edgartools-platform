from __future__ import annotations

import json
from argparse import Namespace
from datetime import date
from unittest.mock import patch

import pytest

from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.registry_ledger import CoverageSpec, SourceRegistryLedger


@pytest.fixture()
def _acquisition_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from sqlalchemy import create_engine

    db_path = tmp_path / "mdm.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    AcquisitionBase.metadata.create_all(engine)
    monkeypatch.setenv("MDM_DATABASE_URL", url)
    _activate_company_facts_registry(engine)
    return url


def _activate_company_facts_registry(engine) -> None:
    """Mirrors test_drive_submissions_discovery_command.py's own
    _activate_submissions_registry helper, for the company_facts family.
    """

    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [
            CoverageSpec(
                source_family="company_facts",
                coverage_action="add",
                acquisition_mode="on_demand_fetch",
                completeness_policy="valid_json_object",
                discovery_policy="cik_universe_driven",
                required_producers=("sec_financial_fact", "sec_accounting_flag"),
                coverage_start_date=date(2026, 1, 1),
                catchup_required_through_date=date(2026, 1, 1),
            )
        ],
        operator_authorization_reference="test-bootstrap",
    )
    ledger.record_catchup_progress("company_facts", date(2026, 1, 1))
    activated = ledger.activate(version.version_id)
    assert activated.status == "active"


def _set_warehouse_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_ENVIRONMENT", "test")
    monkeypatch.setenv("WAREHOUSE_RUNTIME_MODE", "infrastructure_validation")
    monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(tmp_path / "warehouse"))
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    for variable in ("SERVING_EXPORT_ROOT", "SNOWFLAKE_EXPORT_ROOT", "SILVER_LANDING_EXPORT_ROOT"):
        monkeypatch.delenv(variable, raising=False)
    # DuckDB Retirement Cutover: sec_company_sync_state (read by
    # _resolve_ciks when cik_list is omitted) now lives in the Postgres-
    # backed BookkeepingStore, not this test's DuckDB fixture. Pin ONE
    # in-memory SQLite-backed store for the whole test, mirroring
    # test_drive_filing_discovery_command.py's identical pattern.
    from edgar_warehouse.application.workflows import drive_company_facts_discovery
    from tests.support.bookkeeping_fixtures import bookkeeping_fixture

    bookkeeping = bookkeeping_fixture()
    monkeypatch.setattr(drive_company_facts_discovery, "_bookkeeping_store", lambda: bookkeeping)
    return bookkeeping


def _facts_payload(*, accession: str = "0000320193-23-000106") -> dict[str, object]:
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "end": "2023-09-30", "val": 1000,
                                "accn": accession, "fy": 2023, "fp": "FY", "form": "10-K",
                            }
                        ]
                    }
                }
            }
        },
    }


def test_drive_company_facts_discovery_captures_and_publishes_end_to_end(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command

    _set_warehouse_env(monkeypatch, tmp_path)

    facts_bytes = json.dumps(_facts_payload()).encode("utf-8")
    facts_url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"

    def _fake_download(url: str, identity: str) -> bytes:
        if url == facts_url:
            return facts_bytes
        raise AssertionError(f"unexpected URL: {url}")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        side_effect=_fake_download,
    ) as mocked_fetch:
        exit_code = run_command(
            "drive-company-facts-discovery",
            Namespace(
                cik_list=[320193],
                tracking_status_filter="active",
                limit=None,
                worker_id="company-facts-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-company-facts-1",
            ),
        )

    assert exit_code == 0
    assert mocked_fetch.call_count == 1

    result = json.loads(capsys.readouterr().out)
    assert result["cik_count"] == 1
    assert result["interval_complete"] is True
    assert result["silver_interval_complete"] is True

    outcome = result["outcomes"][0]
    assert outcome["cik"] == 320193
    assert outcome["fetch_state"] == "CAPTURED"
    assert outcome["network_fetched"] is True
    assert outcome["silver_outcome"] == "PUBLISHED"
    assert outcome["silver_error"] is None

    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_support.session import open_silver_database

    silver_root = StorageLocation(str(tmp_path / "silver"))
    verify_db = open_silver_database(silver_root)
    try:
        rows = verify_db.fetch(
            "SELECT concept, value FROM sec_financial_fact WHERE cik = ?", [320193]
        )
        assert rows == [{"concept": "Assets", "value": 1000.0}]
    finally:
        verify_db.close()

    run_manifest_path = (
        tmp_path / "bronze" / "runs" / "drive-company-facts-discovery"
        / "run-company-facts-1" / "run_manifest.json"
    )
    assert run_manifest_path.exists()


def test_drive_company_facts_discovery_replay_performs_no_second_network_fetch(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command

    _set_warehouse_env(monkeypatch, tmp_path)

    facts_bytes = json.dumps(_facts_payload()).encode("utf-8")
    facts_url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"

    def _fake_download(url: str, identity: str) -> bytes:
        if url == facts_url:
            return facts_bytes
        raise AssertionError(f"unexpected URL: {url}")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        side_effect=_fake_download,
    ) as mocked_fetch:
        for run_id in ("run-company-facts-1", "run-company-facts-2"):
            exit_code = run_command(
                "drive-company-facts-discovery",
                Namespace(
                    cik_list=[320193],
                    tracking_status_filter="active",
                    limit=None,
                    worker_id=f"company-facts-worker-{run_id}",
                    lease_seconds=None,
                    registry_version=None,
                    run_id=run_id,
                ),
            )
            assert exit_code == 0

    assert mocked_fetch.call_count == 1


def test_drive_company_facts_discovery_resolves_tracked_ciks_from_bookkeeping_store(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    """DuckDB Retirement Cutover: sec_company_sync_state lives in the
    Postgres-backed BookkeepingStore, not SilverDatabase/DuckDB. When
    cik_list is omitted, the tracked-CIK universe must resolve from there --
    every other test in this file passes an explicit cik_list, which skips
    this code path entirely and would not catch a regression here.
    """
    from edgar_warehouse.application.command_router import run_command

    bookkeeping = _set_warehouse_env(monkeypatch, tmp_path)
    bookkeeping.upsert_company_sync_state({"cik": 320193, "tracking_status": "active"})

    facts_bytes = json.dumps(_facts_payload()).encode("utf-8")
    facts_url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"

    def _fake_download(url: str, identity: str) -> bytes:
        if url == facts_url:
            return facts_bytes
        raise AssertionError(f"unexpected URL: {url}")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        side_effect=_fake_download,
    ) as mocked_fetch:
        exit_code = run_command(
            "drive-company-facts-discovery",
            Namespace(
                cik_list=None,
                tracking_status_filter="active",
                limit=None,
                worker_id="company-facts-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-company-facts-1",
            ),
        )

    assert exit_code == 0
    assert mocked_fetch.call_count == 1

    result = json.loads(capsys.readouterr().out)
    assert result["cik_count"] == 1


def test_drive_company_facts_discovery_fails_closed_on_an_unsupported_required_producers_set(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import create_engine

    from edgar_warehouse.acquisition.company_facts_silver_acceptance import (
        UnsupportedRequiredProducers,
    )
    from edgar_warehouse.acquisition.models import AcquisitionBase
    from edgar_warehouse.acquisition.registry_ledger import CoverageSpec, SourceRegistryLedger
    from edgar_warehouse.application.command_router import run_command

    db_path = tmp_path / "mdm.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    AcquisitionBase.metadata.create_all(engine)
    monkeypatch.setenv("MDM_DATABASE_URL", url)

    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [
            CoverageSpec(
                source_family="company_facts",
                coverage_action="add",
                acquisition_mode="on_demand_fetch",
                completeness_policy="valid_json_object",
                discovery_policy="cik_universe_driven",
                required_producers=("some_other_table",),
                coverage_start_date=date(2026, 1, 1),
                catchup_required_through_date=date(2026, 1, 1),
            )
        ],
        operator_authorization_reference="test-bootstrap",
    )
    ledger.record_catchup_progress("company_facts", date(2026, 1, 1))
    ledger.activate(version.version_id)

    _set_warehouse_env(monkeypatch, tmp_path)

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        return_value=json.dumps({"cik": 320193, "entityName": "Apple Inc.", "facts": {}}).encode(
            "utf-8"
        ),
    ), pytest.raises(UnsupportedRequiredProducers):
        run_command(
            "drive-company-facts-discovery",
            Namespace(
                cik_list=[320193],
                tracking_status_filter="active",
                limit=None,
                worker_id="company-facts-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-company-facts-1",
            ),
        )
