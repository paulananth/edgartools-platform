"""seed-universe-narrow-hydrate ticket 05: seed-universe's active-CIK filter
sources from MDM (the system of record), not a silver sec_company_sync_state
read -- MDM's mdm_company.tracking_status mirrors silver's but needs no
duckdb hydrate to query.

Real DB-backed, matching this workstream's established discipline: a genuine
SilverDatabase plays the role of what's on disk, and it deliberately
disagrees with the mocked MDM response for one CIK, so the test can only
pass if the code actually reads from MDM and not from silver.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from edgar_warehouse.application.warehouse_orchestrator import _capture_bronze_raw
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase


def _build_context(tmp_path):
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="dev@example.com",
        runtime_mode="bronze_capture",
    )


def test_seed_universe_active_filter_reads_mdm_not_silver(tmp_path):
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    # Silver marks CIK 100 as active -- if the code still read db.get_active_ciks(),
    # CIK 100 would be excluded from universe_rows. It must NOT be excluded here,
    # because MDM (mocked below) says CIK 100 is not yet active -- proving the
    # filter now reads from MDM, not silver.
    db.upsert_company_sync_state(
        {
            "cik": 100,
            "tracking_status": "active",
            "last_main_sync_at": datetime.now(UTC),
            "last_error_message": None,
        }
    )

    context = _build_context(tmp_path)
    now = datetime.now(UTC)

    universe_rows = [
        {"cik": 100, "ticker": "AAA"},
        {"cik": 200, "ticker": "BBB"},
        {"cik": 300, "ticker": "CCC"},
    ]

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._sync_reference_data",
            return_value={
                "raw_writes": [{"sha256": "deadbeef", "path": "s3://bucket/ref.json"}],
                "rows_written": 0,
                "rows_skipped": 0,
                "seed_document": {},
                "reference_snapshot_identity": None,
            },
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator.seed_universe_loader",
            return_value=universe_rows,
        ),
        # MDM says only CIK 300 is active -- disagrees with silver (which says CIK 100 is).
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._get_mdm_tracked_ciks",
            return_value=[300],
        ) as mock_mdm,
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._seed_silver_tracking_status",
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._write_cik_universe_batches",
            return_value="s3://bucket/cik_universe/batch-0.jsonl",
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._emit_pipeline_event",
        ) as mock_emit,
    ):
        raw_writes, metrics = _capture_bronze_raw(
            context=context,
            db=db,
            bookkeeping=object(),
            command_name="seed-universe",
            arguments={},
            scope={},
            now=now,
            sync_run_id="test-run",
        )

    mock_mdm.assert_called_once_with("active")
    # CIK 100 (silver-active, MDM-inactive) stays in the universe; CIK 300
    # (MDM-active) is excluded. Proves the source is MDM, not silver.
    assert metrics["cik_count"] == 2

    filtered_events = [
        call for call in mock_emit.call_args_list if call.args[0] == "seed_universe_filtered"
    ]
    assert len(filtered_events) == 1
    assert filtered_events[0].kwargs["skipped_mdm_active"] == 1
    assert filtered_events[0].kwargs["new_ciks"] == 2

    db.close()
