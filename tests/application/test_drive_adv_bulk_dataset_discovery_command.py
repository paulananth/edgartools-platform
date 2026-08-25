from __future__ import annotations

import calendar
import io
import json
import zipfile
from argparse import Namespace
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.registry_ledger import CoverageSpec, SourceRegistryLedger


def _activate_adv_bulk_dataset_registry(engine) -> None:
    """Mirrors test_drive_reference_catalog_discovery_command.py's own
    _activate_reference_catalog_registry helper, for the adv_bulk_dataset family.
    """

    ledger = SourceRegistryLedger(engine)
    version = ledger.open_draft(
        [
            CoverageSpec(
                source_family="adv_bulk_dataset",
                coverage_action="add",
                acquisition_mode="on_demand_fetch",
                completeness_policy="non_empty_payload",
                discovery_policy="rolling_window_bulk_dataset",
                required_producers=("sec_adv_filing", "sec_adv_private_fund", "sec_adv_firm_roster"),
                coverage_start_date=date(2026, 1, 1),
                catchup_required_through_date=date(2026, 1, 1),
            )
        ],
        operator_authorization_reference="test-bootstrap",
    )
    ledger.record_catchup_progress("adv_bulk_dataset", date(2026, 1, 1))
    activated = ledger.activate(version.version_id)
    assert activated.status == "active"


@pytest.fixture()
def _acquisition_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    from sqlalchemy import create_engine

    db_path = tmp_path / "mdm.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    AcquisitionBase.metadata.create_all(engine)
    monkeypatch.setenv("MDM_DATABASE_URL", url)
    _activate_adv_bulk_dataset_registry(engine)
    return url


def _set_warehouse_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("EDGAR_IDENTITY", "EdgarTools Platform test@example.com")
    monkeypatch.setenv("WAREHOUSE_ENVIRONMENT", "test")
    monkeypatch.setenv("WAREHOUSE_RUNTIME_MODE", "infrastructure_validation")
    monkeypatch.setenv("WAREHOUSE_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", str(tmp_path / "warehouse"))
    monkeypatch.setenv("WAREHOUSE_SILVER_ROOT", str(tmp_path / "silver"))
    for variable in ("SERVING_EXPORT_ROOT", "SNOWFLAKE_EXPORT_ROOT", "SILVER_LANDING_EXPORT_ROOT"):
        monkeypatch.delenv(variable, raising=False)


def _zip(files: dict[str, str]) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return payload.getvalue()


def test_drive_adv_bulk_dataset_discovery_captures_and_publishes_end_to_end(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _acquisition_db: str
) -> None:
    from edgar_warehouse.application.command_router import run_command

    _set_warehouse_env(monkeypatch, tmp_path)

    today = date.today()
    period = f"{today.year:04d}-{today.month:02d}"
    file_name = f"ADV_Filing_Data_{today.year:04d}{today.month:02d}01_{today.year:04d}{today.month:02d}28.zip"
    metadata_payload = json.dumps(
        {"advFilingData": {period: {"files": [{"fileName": file_name, "year": str(today.year)}]}}}
    ).encode("utf-8")
    archive_url = (
        f"https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/{today.year}/{file_name}"
    )
    bulk_archive = _zip(
        {
            "IA_ADV_Base_A_x.csv": (
                '"FilingID","DateSubmitted","1A","1D","1E1","7B"\n'
                '2115188,"06/24/2026 10:37:17 AM","PNC WEALTH","801-66195",129052,"N"\n'
            ),
        }
    )
    # No Firm Roster listing published this run -- a valid, complete-empty
    # outcome for that source kind (bullet 3), so the roster half of the
    # manifest is empty and only the bulk archive is exercised end-to-end.

    def _fake_metadata_fetch(identity: str) -> bytes:
        return metadata_payload

    def _fake_listing_fetch(identity: str) -> bytes:
        return b""

    def _fake_download(url: str, identity: str) -> bytes:
        if url == archive_url:
            return bulk_archive
        raise AssertionError(f"unexpected URL: {url}")

    with (
        patch(
            "edgar_warehouse.application.adv_bulk_fetch.fetch_reports_metadata_bytes",
            side_effect=_fake_metadata_fetch,
        ),
        patch(
            "edgar_warehouse.application.firm_roster_fetch.fetch_listing_bytes",
            side_effect=_fake_listing_fetch,
        ),
        patch(
            "edgar_warehouse.acquisition.source_family_registry.download_sec_bytes",
            side_effect=_fake_download,
        ) as mocked_fetch,
    ):
        exit_code = run_command(
            "drive-adv-bulk-dataset-discovery",
            Namespace(
                window_months=1,
                worker_id="adv-bulk-dataset-worker-1",
                lease_seconds=None,
                registry_version=None,
                run_id="run-adv-bulk-dataset-1",
            ),
        )

    assert exit_code == 0
    assert mocked_fetch.call_count == 1

    result = json.loads(capsys.readouterr().out)
    assert result["candidate_count"] == 1
    assert result["interval_complete"] is True
    assert result["silver_interval_complete"] is True
    outcome = result["outcomes"][0]
    assert outcome["source_kind"] == "adv_bulk"
    assert outcome["fetch_state"] == "CAPTURED"
    assert outcome["silver_outcome"] == "PUBLISHED"
    assert outcome["silver_error"] is None

    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_support.session import open_silver_database

    silver_root = StorageLocation(str(tmp_path / "silver"))
    verify_db = open_silver_database(silver_root)
    try:
        rows = verify_db.fetch("SELECT accession_number, crd_number FROM sec_adv_filing")
        assert rows == [{"accession_number": "iapd-adv:2115188", "crd_number": "129052"}]
    finally:
        verify_db.close()
