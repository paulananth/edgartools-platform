from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext


def _context(tmp_path: Path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="tester@example.com",
        runtime_mode="bronze_capture",
    )


def test_discovery_checkpoint_claims_prevent_active_overlap(tmp_path) -> None:
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    now = datetime(2026, 7, 6, tzinfo=UTC)
    try:
        assert db.claim_discovery_ciks(
            [100, 200],
            discovery_source="daily_incremental",
            run_id="daily-run",
            claimed_at=now,
        ) == [100, 200]
        assert db.claim_discovery_ciks(
            [100, 200, 300],
            discovery_source="bootstrap_next",
            run_id="bootstrap-run",
            claimed_at=now,
        ) == [300]

        db.finish_discovery_ciks(
            [100],
            discovery_source="daily_incremental",
            run_id="daily-run",
            status="succeeded",
            finished_at=now,
        )
        assert db.claim_discovery_ciks(
            [100],
            discovery_source="bootstrap_next",
            run_id="bootstrap-run-2",
            claimed_at=now,
        ) == [100]
    finally:
        db.close()


def test_daily_incremental_claims_discovery_ciks_before_submissions(tmp_path) -> None:
    db = MagicMock()
    db.get_company_sync_state.return_value = {"tracking_status": "active"}
    db.get_tracked_ciks.return_value = [100, 200]
    db.claim_discovery_ciks.return_value = [100]
    context = _context(tmp_path)
    now = datetime(2026, 7, 6, tzinfo=UTC)

    with (
        patch.object(
            warehouse_orchestrator,
            "_load_daily_index_for_date",
            return_value={
                "raw_writes": [],
                "rows_written": 0,
                "rows_skipped": 0,
                "impacted_ciks": [100, 200],
                "status": "succeeded",
            },
        ),
        patch.object(
            warehouse_orchestrator,
            "_run_submissions_bronze_then_silver",
            return_value={"raw_writes": [], "rows_written": 1, "rows_skipped": 0},
        ) as run_submissions,
    ):
        warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="daily-incremental",
            arguments={},
            scope={"business_date_start": "2026-07-06", "business_date_end": "2026-07-06"},
            now=now,
            sync_run_id="daily-run",
        )

    db.claim_discovery_ciks.assert_called_once_with(
        [100, 200],
        discovery_source="daily_incremental",
        run_id="daily-run",
        claimed_at=now,
    )
    run_submissions.assert_called_once()
    assert run_submissions.call_args.kwargs["ciks"] == [100]
    db.finish_discovery_ciks.assert_called_once_with(
        [100],
        discovery_source="daily_incremental",
        run_id="daily-run",
        status="succeeded",
        finished_at=now,
    )


def test_bootstrap_next_claims_discovery_ciks_before_submissions(tmp_path) -> None:
    db = MagicMock()
    db.get_tracked_ciks.return_value = [100, 200]
    db.claim_discovery_ciks.return_value = [200]
    context = _context(tmp_path)
    now = datetime(2026, 7, 6, tzinfo=UTC)

    with patch.object(
        warehouse_orchestrator,
        "_run_submissions_bronze_then_silver",
        return_value={"raw_writes": [], "rows_written": 1, "rows_skipped": 0},
    ) as run_submissions:
        warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="bootstrap-next",
            arguments={},
            scope={"cik_limit": 100, "tracking_status_filter": "bootstrap_pending"},
            now=now,
            sync_run_id="bootstrap-run",
        )

    db.claim_discovery_ciks.assert_called_once_with(
        [100, 200],
        discovery_source="bootstrap_next",
        run_id="bootstrap-run",
        claimed_at=now,
    )
    run_submissions.assert_called_once()
    assert run_submissions.call_args.kwargs["ciks"] == [200]
    db.finish_discovery_ciks.assert_called_once_with(
        [200],
        discovery_source="bootstrap_next",
        run_id="bootstrap-run",
        status="succeeded",
        finished_at=now,
    )
