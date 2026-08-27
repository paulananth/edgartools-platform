"""Ticket 46 (change-propagation map): filing_artifact's gated discovery/
capture, run in-process from daily-incremental's own per-date loop.

Mirrors tests/unit/test_discovery_checkpoint.py's own patching convention
(patch module-level function references on warehouse_orchestrator, call
_capture_bronze_raw directly with a plain arguments dict) rather than
inventing a new harness.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


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


def _stub_index_result(*, target_date: date) -> dict:
    return {
        "raw_writes": [],
        "rows_written": 0,
        "rows_skipped": 0,
        "impacted_ciks": [],
        "status": "succeeded",
    }


def _run_daily_incremental(
    *,
    tmp_path: Path,
    arguments: dict,
    business_date_start: str,
    business_date_end: str,
    now: datetime,
    load_daily_index_side_effect=None,
):
    db = MagicMock()
    db.get_tracked_ciks.return_value = []
    db.claim_discovery_ciks.return_value = []
    context = _context(tmp_path)

    with (
        patch.object(
            warehouse_orchestrator,
            "_load_daily_index_for_date",
            side_effect=load_daily_index_side_effect or (lambda *, target_date, **kw: _stub_index_result(target_date=target_date)),
        ) as load_daily_index,
        patch.object(
            warehouse_orchestrator,
            "_run_submissions_bronze_then_silver",
            return_value={"raw_writes": [], "rows_written": 0, "rows_skipped": 0},
        ) as run_submissions,
        patch.object(
            warehouse_orchestrator,
            "_run_filing_artifact_gated_capture",
            return_value={"interval_complete": True},
        ) as gated_capture,
    ):
        raw_writes, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="daily-incremental",
            arguments=arguments,
            scope={
                "business_date_start": business_date_start,
                "business_date_end": business_date_end,
            },
            now=now,
            sync_run_id="daily-run",
        )
    return raw_writes, metrics, load_daily_index, run_submissions, gated_capture


def test_gated_capture_off_by_default_leaves_metrics_unchanged(tmp_path) -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    _raw_writes, metrics, _load, _submissions, gated_capture = _run_daily_incremental(
        tmp_path=tmp_path,
        arguments={"recurring_index_lookback_days": 0},
        business_date_start="2026-08-27",
        business_date_end="2026-08-27",
        now=now,
    )

    gated_capture.assert_not_called()
    assert "filing_artifact_gated_capture" not in metrics


def test_gated_capture_runs_once_for_business_date_end_when_enabled(tmp_path) -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    _raw_writes, metrics, _load, _submissions, gated_capture = _run_daily_incremental(
        tmp_path=tmp_path,
        arguments={
            "recurring_index_lookback_days": 0,
            "enable_filing_artifact_gated_capture": True,
        },
        business_date_start="2026-08-27",
        business_date_end="2026-08-27",
        now=now,
    )

    gated_capture.assert_called_once()
    assert gated_capture.call_args.kwargs["business_date"] == "2026-08-27"
    assert metrics["filing_artifact_gated_capture"]["status"] == "ok"
    assert metrics["filing_artifact_gated_capture"]["interval_complete"] is True


def test_gated_capture_scoped_to_business_date_end_not_every_recurring_day(tmp_path) -> None:
    now = datetime(2026, 8, 27, 12, tzinfo=UTC)
    _raw_writes, metrics, load_daily_index, _submissions, gated_capture = _run_daily_incremental(
        tmp_path=tmp_path,
        arguments={
            "recurring_index_lookback_days": 7,
            "enable_filing_artifact_gated_capture": True,
        },
        business_date_start="2026-08-27",
        business_date_end="2026-08-27",
        now=now,
    )

    # Recurring lookback expands the loop across 7 sealed daily indexes...
    assert len(load_daily_index.call_args_list) == 7
    # ...but the gated capture side channel only ever runs once, for the
    # final business date -- not fanned out across the whole window (Ticket
    # 46's Answer: bounding SEC-fetch/memory cost on a task with documented
    # OOM history).
    gated_capture.assert_called_once()
    assert gated_capture.call_args.kwargs["business_date"] == "2026-08-27"


def test_gated_capture_failure_is_isolated_and_does_not_fail_daily_incremental(tmp_path) -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    db = MagicMock()
    db.get_tracked_ciks.return_value = []
    db.claim_discovery_ciks.return_value = []
    context = _context(tmp_path)

    with (
        patch.object(
            warehouse_orchestrator,
            "_load_daily_index_for_date",
            side_effect=lambda *, target_date, **kw: _stub_index_result(target_date=target_date),
        ),
        patch.object(
            warehouse_orchestrator,
            "_run_submissions_bronze_then_silver",
            return_value={"raw_writes": [], "rows_written": 0, "rows_skipped": 0},
        ),
        patch.object(
            warehouse_orchestrator,
            "_run_filing_artifact_gated_capture",
            side_effect=RuntimeError("boom"),
        ) as gated_capture,
    ):
        # Must not raise -- an unverified, off-by-default side channel can
        # never be allowed to fail this command outright (it would trip the
        # state machine's MaxAttempts:3 retry for a side-channel that hasn't
        # earned trust yet).
        raw_writes, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="daily-incremental",
            arguments={
                "recurring_index_lookback_days": 0,
                "enable_filing_artifact_gated_capture": True,
            },
            scope={
                "business_date_start": "2026-08-27",
                "business_date_end": "2026-08-27",
            },
            now=now,
            sync_run_id="daily-run",
        )

    gated_capture.assert_called_once()
    assert metrics["filing_artifact_gated_capture"]["status"] == "error"
    assert "boom" in metrics["filing_artifact_gated_capture"]["error"]
    # The rest of daily-incremental's own outcome is untouched by the failure.
    assert metrics["sync_status"] == "succeeded"


def test_gated_capture_skipped_when_daily_index_load_is_partial(tmp_path) -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)

    def load_index(*, target_date, **kwargs):
        return {
            "raw_writes": [],
            "rows_written": 0,
            "rows_skipped": 0,
            "impacted_ciks": [],
            "status": "waiting_for_publish",
        }

    _raw_writes, metrics, _load, _submissions, gated_capture = _run_daily_incremental(
        tmp_path=tmp_path,
        arguments={
            "recurring_index_lookback_days": 0,
            "enable_filing_artifact_gated_capture": True,
        },
        business_date_start="2026-08-27",
        business_date_end="2026-08-27",
        now=now,
        load_daily_index_side_effect=load_index,
    )

    assert metrics["sync_status"] == "partial"
    gated_capture.assert_not_called()
    assert "filing_artifact_gated_capture" not in metrics
