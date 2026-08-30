"""End-to-end fetch-adv-bulk command dispatch, network boundary mocked."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.adv_bulk_fetch import rolling_window_periods
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase
from tests.support.bookkeeping_fixtures import bookkeeping_fixture

_METADATA_JSON = json.dumps({
    "advFilingData": {
        "2026": {
            "files": [
                {
                    "displayName": "June",
                    "fileName": "ADV_Filing_Data_20260601_20260630.zip",
                    "size": 123,
                    "year": "2026",
                    "fileType": "advFilingData",
                    "uploadedOn": "2026-07-01 21:13:14",
                },
            ]
        },
    },
}).encode("utf-8")


def _context(tmp_path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
    )


def _db_path(context: WarehouseCommandContext) -> str:
    return context.silver_root.join("silver", "sec", "silver.duckdb")


def test_fetch_adv_bulk_fetches_missing_period_and_writes_manifest(tmp_path, monkeypatch) -> None:
    context = _context(tmp_path)

    responses = {
        "https://reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json": _METADATA_JSON,
        "https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/2026/ADV_Filing_Data_20260601_20260630.zip": b"zip-bytes",
    }

    def _fake_download(url: str, identity: str) -> bytes:
        assert identity == context.identity
        return responses[url]

    monkeypatch.setattr(
        "edgar_warehouse.infrastructure.sec_client.download_sec_bytes", _fake_download
    )
    monkeypatch.setattr(
        "edgar_warehouse.application.warehouse_orchestrator.datetime",
        type("_FixedDatetime", (datetime,), {
            "now": classmethod(lambda cls, tz=None: datetime(2026, 6, 15, tzinfo=UTC)),
        }),
    )
    monkeypatch.setattr(
        warehouse_orchestrator, "_bookkeeping_store", lambda: bookkeeping_fixture()
    )

    result = warehouse_orchestrator._execute_warehouse(
        context=context,
        command_name="fetch-adv-bulk",
        arguments={"run_id": "test-run-1"},
    )

    assert result["status"] == "ok"
    manifest = json.loads(
        (tmp_path / "bronze" / "runs" / "fetch-adv-bulk" / "test-run-1" / "source_manifest.json").read_text()
    )
    assert manifest["sources"] == [
        {
            "kind": "iapd_adv_bulk",
            "storage_path": str(
                tmp_path / "bronze" / "runs" / "fetch-adv-bulk" / "test-run-1" / "ADV_Filing_Data_20260601_20260630.zip"
            ),
            "sha256": hashlib.sha256(b"zip-bytes").hexdigest(),
            "dataset_period": "2026-06",
        }
    ]
    staged_archive = (
        tmp_path / "bronze" / "runs" / "fetch-adv-bulk" / "test-run-1" / "ADV_Filing_Data_20260601_20260630.zip"
    )
    assert staged_archive.read_bytes() == b"zip-bytes"


def test_fetch_adv_bulk_is_a_no_op_when_window_fully_ingested(tmp_path, monkeypatch) -> None:
    # Mirrors ticket 04's real finding in prod: once the full 13-month
    # rolling window is already in silver, a rerun must make zero network
    # calls, not just skip a single period.
    context = _context(tmp_path)
    db = SilverDatabase(_db_path(context))
    try:
        for index, period in enumerate(rolling_window_periods(date(2026, 6, 15))):
            db._conn.execute(
                "INSERT INTO sec_adv_private_fund "
                "(accession_number, fund_index, filing_id, adviser_crd_number, "
                " private_fund_id, schedule_section, reporting_role, filing_action, "
                " fund_name, source_dataset_period, parser_version, last_sync_run_id) "
                "VALUES (?, 1, ?, '801-1', ?, '7B1', 'detailed_reporter', 'current_compilation', "
                " 'Test Fund', ?, 'iapd_bulk_v1', 'seed-run')",
                [f"iapd-adv:{index}", str(index), f"805-{index}", period],
            )
    finally:
        db.close()

    def _fail_if_called(url: str, identity: str) -> bytes:
        raise AssertionError(f"unexpected network call to {url}")

    monkeypatch.setattr(
        "edgar_warehouse.infrastructure.sec_client.download_sec_bytes", _fail_if_called
    )
    monkeypatch.setattr(
        "edgar_warehouse.application.warehouse_orchestrator.datetime",
        type("_FixedDatetime", (datetime,), {
            "now": classmethod(lambda cls, tz=None: datetime(2026, 6, 15, tzinfo=UTC)),
        }),
    )
    monkeypatch.setattr(
        warehouse_orchestrator, "_bookkeeping_store", lambda: bookkeeping_fixture()
    )

    result = warehouse_orchestrator._execute_warehouse(
        context=context,
        command_name="fetch-adv-bulk",
        arguments={"run_id": "test-run-2"},
    )

    assert result["status"] == "ok"
    manifest = json.loads(
        (tmp_path / "bronze" / "runs" / "fetch-adv-bulk" / "test-run-2" / "source_manifest.json").read_text()
    )
    assert manifest == {"sources": []}
