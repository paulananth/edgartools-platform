from __future__ import annotations

import json
from argparse import Namespace
from datetime import date
from unittest.mock import patch

import pytest

from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.registry_ledger import CoverageSpec, SourceRegistryLedger
from edgar_warehouse.infrastructure.sec_client import (
    build_company_tickers_exchange_url,
    build_company_tickers_url,
)


@pytest.fixture()
def _acquisition_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from sqlalchemy import create_engine

    db_path = tmp_path / "mdm.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    AcquisitionBase.metadata.create_all(engine)
    monkeypatch.setenv("MDM_DATABASE_URL", url)
    _activate_reference_catalog_registry(engine)
    return url


def _activate_reference_catalog_registry(engine) -> None:
    """Mirrors test_drive_company_facts_discovery_command.py's own
    _activate_company_facts_registry helper, for the reference_catalog family.
    """

    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [
            CoverageSpec(
                source_family="reference_catalog",
                coverage_action="add",
                acquisition_mode="on_demand_fetch",
                completeness_policy="valid_ticker_catalog_json",
                discovery_policy="fixed_source_name_set",
                required_producers=("sec_company_ticker",),
                coverage_start_date=date(2026, 1, 1),
                catchup_required_through_date=date(2026, 1, 1),
            )
        ],
        operator_authorization_reference="test-bootstrap",
    )
    ledger.record_catchup_progress("reference_catalog", date(2026, 1, 1))
    activated = ledger.activate(version.version_id)
    assert activated.status == "active"


def _set_warehouse_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_ENVIRONMENT", "test")
    monkeypatch.setenv("WAREHOUSE_RUNTIME_MODE", "infrastructure_validation")
    monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(tmp_path / "warehouse"))
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    for variable in ("SERVING_EXPORT_ROOT", "SNOWFLAKE_EXPORT_ROOT", "SILVER_LANDING_EXPORT_ROOT"):
        monkeypatch.delenv(variable, raising=False)


def _catalog_payloads() -> dict[str, bytes]:
    return {
        build_company_tickers_url(): json.dumps(
            {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
        ).encode("utf-8"),
        build_company_tickers_exchange_url(): json.dumps(
            {"fields": ["cik", "name", "ticker", "exchange"], "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]]}
        ).encode("utf-8"),
    }


def test_drive_reference_catalog_discovery_captures_and_publishes_end_to_end(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command

    _set_warehouse_env(monkeypatch, tmp_path)
    payloads = _catalog_payloads()

    def _fake_download(url: str, identity: str) -> bytes:
        if url in payloads:
            return payloads[url]
        raise AssertionError(f"unexpected URL: {url}")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        side_effect=_fake_download,
    ) as mocked_fetch:
        exit_code = run_command(
            "drive-reference-catalog-discovery",
            Namespace(
                source_names=None,
                worker_id="reference-catalog-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-reference-catalog-1",
            ),
        )

    assert exit_code == 0
    assert mocked_fetch.call_count == 2

    result = json.loads(capsys.readouterr().out)
    assert result["source_name_count"] == 2
    assert result["interval_complete"] is True
    assert result["silver_interval_complete"] is True

    for outcome in result["outcomes"]:
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
            "SELECT cik, ticker, source_name FROM sec_company_ticker WHERE cik = ? "
            "ORDER BY source_name",
            [320193],
        )
        assert rows == [
            {"cik": 320193, "ticker": "AAPL", "source_name": "company_tickers"},
            {"cik": 320193, "ticker": "AAPL", "source_name": "company_tickers_exchange"},
        ]
    finally:
        verify_db.close()

    run_manifest_path = (
        tmp_path / "bronze" / "runs" / "drive-reference-catalog-discovery"
        / "run-reference-catalog-1" / "run_manifest.json"
    )
    assert run_manifest_path.exists()


def test_drive_reference_catalog_discovery_replay_performs_no_second_network_fetch(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command

    _set_warehouse_env(monkeypatch, tmp_path)
    payloads = _catalog_payloads()

    def _fake_download(url: str, identity: str) -> bytes:
        if url in payloads:
            return payloads[url]
        raise AssertionError(f"unexpected URL: {url}")

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        side_effect=_fake_download,
    ) as mocked_fetch:
        for run_id in ("run-reference-catalog-1", "run-reference-catalog-2"):
            exit_code = run_command(
                "drive-reference-catalog-discovery",
                Namespace(
                    source_names=None,
                    worker_id=f"reference-catalog-worker-{run_id}",
                    lease_seconds=None,
                    registry_version=None,
                    run_id=run_id,
                ),
            )
            assert exit_code == 0

    assert mocked_fetch.call_count == 2


def test_drive_reference_catalog_discovery_fails_closed_on_an_unsupported_required_producers_set(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import create_engine

    from edgar_warehouse.acquisition.models import AcquisitionBase
    from edgar_warehouse.acquisition.reference_catalog_silver_acceptance import (
        UnsupportedRequiredProducers,
    )
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
                source_family="reference_catalog",
                coverage_action="add",
                acquisition_mode="on_demand_fetch",
                completeness_policy="valid_ticker_catalog_json",
                discovery_policy="fixed_source_name_set",
                required_producers=("some_other_table",),
                coverage_start_date=date(2026, 1, 1),
                catchup_required_through_date=date(2026, 1, 1),
            )
        ],
        operator_authorization_reference="test-bootstrap",
    )
    ledger.record_catchup_progress("reference_catalog", date(2026, 1, 1))
    ledger.activate(version.version_id)

    _set_warehouse_env(monkeypatch, tmp_path)
    payloads = _catalog_payloads()

    with patch(
        "edgar_warehouse.acquisition.source_family_registry.download_sec_catalog_bytes",
        side_effect=lambda url, identity: payloads[url],
    ), pytest.raises(UnsupportedRequiredProducers):
        run_command(
            "drive-reference-catalog-discovery",
            Namespace(
                source_names=None,
                worker_id="reference-catalog-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-reference-catalog-1",
            ),
        )
