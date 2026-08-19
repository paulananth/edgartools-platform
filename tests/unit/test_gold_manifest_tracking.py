from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pyarrow as pa

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase


def _context(tmp_path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=StorageLocation(str(tmp_path / "snowflake-export")),
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
    )


def test_silver_database_records_gold_manifest_diffs(tmp_path) -> None:
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.record_gold_manifest(
            run_id="run-1",
            command_name="gold-refresh",
            entries=[
                {
                    "table_name": "dim_company",
                    "storage_layer": "warehouse_gold",
                    "relative_path": "gold/dim_company/run_id=run-1/dim_company.parquet",
                    "storage_path": "/warehouse/gold/dim_company/run_id=run-1/dim_company.parquet",
                    "row_count": 1,
                    "parquet_sha256": "aaa",
                    "byte_size": 10,
                }
            ],
        )
        db.record_gold_manifest(
            run_id="run-2",
            command_name="gold-refresh",
            entries=[
                {
                    "table_name": "dim_company",
                    "storage_layer": "warehouse_gold",
                    "relative_path": "gold/dim_company/run_id=run-2/dim_company.parquet",
                    "storage_path": "/warehouse/gold/dim_company/run_id=run-2/dim_company.parquet",
                    "row_count": 3,
                    "parquet_sha256": "bbb",
                    "byte_size": 11,
                }
            ],
        )

        rows = db.get_gold_manifest("run-2")
    finally:
        db.close()

    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-2"
    assert rows[0]["table_name"] == "dim_company"
    assert rows[0]["row_count"] == 3
    assert rows[0]["previous_run_id"] == "run-1"
    assert rows[0]["previous_row_count"] == 1
    assert rows[0]["previous_parquet_sha256"] == "aaa"
    assert rows[0]["row_count_delta"] == 2
    assert rows[0]["parquet_changed"] is True


def test_write_gold_to_storage_manifest_hashes_parquet_files(tmp_path) -> None:
    from edgar_warehouse.serving.source_dimensional_export import write_gold_to_storage_manifest

    storage_root = StorageLocation(str(tmp_path / "warehouse"))
    table = pa.table({"cik": pa.array([320193], type=pa.int64())})

    entries = write_gold_to_storage_manifest(
        {"dim_company": table},
        storage_root,
        "run-1",
    )

    assert len(entries) == 1
    entry = entries[0]
    payload = (tmp_path / "warehouse" / entry["relative_path"]).read_bytes()
    assert entry["table_name"] == "dim_company"
    assert entry["row_count"] == 1
    assert entry["storage_layer"] == "warehouse_gold"
    assert entry["parquet_sha256"] == hashlib.sha256(payload).hexdigest()
    assert entry["byte_size"] == len(payload)


def test_gold_refresh_records_gold_manifest_rows(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )

    context = _context(tmp_path)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {}
    manifest_entries = [
        {
            "table_name": "dim_company",
            "storage_layer": "warehouse_gold",
            "relative_path": "gold/dim_company/run_id=run-2/dim_company.parquet",
            "storage_path": "/warehouse/gold/dim_company/run_id=run-2/dim_company.parquet",
            "row_count": 1,
            "parquet_sha256": "abc",
            "byte_size": 100,
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
            return_value=([], {"rows_inserted": 0, "rows_skipped": 0, "sync_status": "succeeded"}),
        ),
        patch(
            "edgar_warehouse.serving.source_dimensional_export.iter_gold_tables",
            return_value=iter([("dim_company", MagicMock(num_rows=1))]),
        ),
        patch(
            "edgar_warehouse.serving.source_dimensional_export.write_gold_table_manifest_entry",
            return_value=manifest_entries[0],
        ),
        patch(
            "edgar_warehouse.serving.targets.snowflake.write_gold_table_to_serving_export",
            return_value=("company", 1),
        ),
    ):
        _execute_warehouse_bronze_capture(
            context=context,
            command_name="gold-refresh",
            arguments={"run_id": "run-2"},
        )

    fake_db.record_gold_manifest.assert_called_once_with(
        run_id="run-2",
        command_name="gold-refresh",
        entries=manifest_entries,
    )
    complete_metrics = fake_db.complete_pipeline_run.call_args.kwargs["metrics"]
    assert complete_metrics["gold_manifest"] == manifest_entries


def test_bootstrap_next_silver_only_skips_gold_in_bronze_capture(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )

    context = _context(tmp_path)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {"sec_company": 1}

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
            return_value=fake_db,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._resolve_scope",
            return_value={"limit": 100, "offset": 0},
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            return_value=(
                [],
                {"rows_inserted": 1, "rows_skipped": 0, "sync_status": "succeeded"},
            ),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_with_retry",
            return_value={"layer": "silver_database", "path": "silver.duckdb"},
        ),
        patch(
            "edgar_warehouse.serving.source_dimensional_export.iter_gold_tables",
            return_value=iter(()),
        ) as iter_gold,
        patch(
            "edgar_warehouse.serving.targets.snowflake.write_gold_table_to_serving_export"
        ) as export_gold,
    ):
        result = _execute_warehouse_bronze_capture(
            context=context,
            command_name="bootstrap-next",
            arguments={"run_id": "silver-only-run", "silver_only": True},
        )

    iter_gold.assert_not_called()
    export_gold.assert_not_called()
    fake_db.record_gold_manifest.assert_not_called()
    assert result["gold_row_counts"] is None
    assert result["snowflake_export_manifest"] is None
    assert not {"gold", "snowflake_export_manifest"} & {
        write["layer"] for write in result["writes"]
    }


def test_bootstrap_next_default_still_publishes_gold_in_bronze_capture(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )

    context = _context(tmp_path)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {"sec_company": 1}

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
            return_value=fake_db,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._resolve_scope",
            return_value={"limit": 100, "offset": 0},
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            return_value=(
                [],
                {"rows_inserted": 1, "rows_skipped": 0, "sync_status": "succeeded"},
            ),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_with_retry",
            return_value={"layer": "silver_database", "path": "silver.duckdb"},
        ),
        patch(
            "edgar_warehouse.serving.source_dimensional_export.iter_gold_tables",
            return_value=iter(()),
        ) as iter_gold,
    ):
        result = _execute_warehouse_bronze_capture(
            context=context,
            command_name="bootstrap-next",
            arguments={"run_id": "default-publication-run"},
        )

    iter_gold.assert_called_once_with(fake_db)
    assert result["gold_row_counts"] == {}
    assert result["snowflake_export_manifest"] is not None
