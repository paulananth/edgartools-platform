from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


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


def test_silver_database_records_pipeline_run_lifecycle(tmp_path) -> None:
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.start_pipeline_run(
            {
                "pipeline_run_id": "run-1",
                "command_name": "seed-universe",
                "runtime_mode": "bronze_capture",
                "environment_name": "test",
                "started_at": datetime(2026, 1, 1, tzinfo=UTC),
                "status": "running",
                "arguments": {"run_id": "run-1"},
                "scope": {"run_date": "2026-01-01"},
                "bronze_root": "s3://bronze",
                "storage_root": "s3://warehouse",
                "silver_root": "/tmp/silver",
            }
        )
        db.complete_pipeline_run(
            "run-1",
            status="succeeded",
            writes=[{"layer": "bronze", "path": "s3://bronze/runs/run-1/manifest.json"}],
            raw_writes=[{"path": "s3://bronze/raw.json", "sha256": "abc"}],
            metrics={"rows_inserted": 1},
        )

        row = db.get_pipeline_run("run-1")
    finally:
        db.close()

    assert row is not None
    assert row["pipeline_run_id"] == "run-1"
    assert row["status"] == "succeeded"
    assert json.loads(row["writes_json"])[0]["layer"] == "bronze"
    assert json.loads(row["raw_writes_json"])[0]["sha256"] == "abc"
    assert json.loads(row["metrics_json"]) == {"rows_inserted": 1}


def test_bronze_capture_records_pipeline_run(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )

    context = _context(tmp_path)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {}
    raw_path = context.bronze_root.write_bytes("raw/test.json", b'{"ok": true}')
    raw_writes = [
        {
            "layer": "bronze_raw",
            "path": raw_path,
            "relative_path": "raw/test.json",
            "sha256": "c0ffee",
        }
    ]

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
            return_value=fake_db,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            return_value=(raw_writes, {"rows_inserted": 1, "rows_skipped": 0}),
        ),
    ):
        _execute_warehouse_bronze_capture(
            context=context,
            command_name="seed-universe",
            arguments={"run_id": "run-1"},
        )

    fake_db.start_pipeline_run.assert_called_once()
    fake_db.complete_pipeline_run.assert_called_once()
    complete_kwargs = fake_db.complete_pipeline_run.call_args.kwargs
    assert complete_kwargs["status"] == "succeeded"
    assert complete_kwargs["raw_writes"] == raw_writes
    assert any(write["layer"] == "bronze" for write in complete_kwargs["writes"])


def test_bronze_capture_writes_consolidated_run_manifest(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )

    context = _context(tmp_path)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {"sec_company": 1}
    raw_writes = [
        {
            "layer": "bronze_raw",
            "path": context.bronze_root.write_bytes("raw/test.json", b'{"ok": true}'),
            "relative_path": "raw/test.json",
            "sha256": "c0ffee",
        }
    ]

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
            return_value=fake_db,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            return_value=(raw_writes, {"rows_inserted": 1, "rows_skipped": 0}),
        ),
    ):
        result = _execute_warehouse_bronze_capture(
            context=context,
            command_name="seed-universe",
            arguments={"run_id": "run-1"},
        )

    manifest_path = tmp_path / "bronze" / "runs" / "seed-universe" / "run-1" / "run_manifest.json"
    payload = json.loads(manifest_path.read_text())
    assert payload["schema_version"] == 1
    assert payload["command"] == "seed-universe"
    assert payload["run_id"] == "run-1"
    assert payload["created_at"].endswith("Z")
    assert payload["row_counts"]["rows_inserted"] == 1
    assert payload["row_counts"]["silver_table_counts"] == {"sec_company": 1}

    manifests = {entry["layer"]: entry for entry in payload["manifests"]}
    assert {"bronze", "staging", "artifacts"} <= set(manifests)
    assert manifests["bronze"]["path"].endswith("runs/seed-universe/run-1/manifest.json")
    assert manifests["bronze"]["row_counts"] == {"rows_inserted": 1, "rows_skipped": 0}
    assert manifests["staging"]["written_at"].endswith("Z")
    assert any(write["layer"] == "run_manifest" for write in result["writes"])


def test_verify_pipeline_run_rechecks_raw_write_hashes(tmp_path) -> None:
    from edgar_warehouse.application.commands.verify_pipeline_run import verify_pipeline_run
    from edgar_warehouse.silver_store import SilverDatabase

    context = _context(tmp_path)
    raw_payload = b'{"ok": true}'
    raw_path = context.bronze_root.write_bytes("raw/test.json", raw_payload)

    db = SilverDatabase(context.silver_root.join("silver", "sec", "silver.duckdb"))
    try:
        db.start_pipeline_run(
            {
                "pipeline_run_id": "run-1",
                "command_name": "seed-universe",
                "runtime_mode": "bronze_capture",
                "environment_name": "test",
                "started_at": datetime(2026, 1, 1, tzinfo=UTC),
                "status": "running",
                "arguments": {},
                "scope": {},
                "bronze_root": context.bronze_root.root,
                "storage_root": context.storage_root.root,
                "silver_root": context.silver_root.root,
            }
        )
        db.complete_pipeline_run(
            "run-1",
            status="succeeded",
            writes=[],
            raw_writes=[
                {
                    "layer": "bronze_raw",
                    "path": raw_path,
                    "relative_path": "raw/test.json",
                    "sha256": "6bc0da1f42f96fc37b8bd7ed20ba57606d2a0da5cda2b135c7854fbdc985b8a3",
                }
            ],
            metrics={},
        )
    finally:
        db.close()

    report = verify_pipeline_run(context=context, run_id="run-1")

    assert report["status"] == "ok"
    assert report["hashes_checked"] == 1
    assert report["missing_paths"] == []
    assert report["hash_mismatches"] == []
