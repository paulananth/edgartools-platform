"""release-readiness Ticket 74 item 3: an up-front, cheap gate at the very
start of a daily-incremental recurring attempt that detects a prior attempt's
unresolved terminal-repair markers under the same run_id, failing fast
instead of redoing the ~95-minute daily-index/submissions-silver phases only
to hit the identical, much-later check inside
_run_configured_form_artifact_pipeline (prepare_resume).

Mirrors tests/unit/test_daily_incremental_gated_capture.py's own patching
convention (patch module-level function references on
warehouse_orchestrator, call _capture_bronze_raw directly with a plain
arguments dict) rather than inventing a new harness.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.daily_artifact_resume import (
    prepare_resume,
    record_terminal_repair,
)
from edgar_warehouse.application.errors import WarehouseRuntimeError
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
        "impacted_ciks": [320193],
        "accession_numbers": ["0000320193-26-000001"],
        "candidate_rows": [],
        "status": "succeeded",
    }


def _run_daily_incremental(*, tmp_path: Path, arguments: dict, run_id: str = "daily-run"):
    bookkeeping = MagicMock()
    bookkeeping.get_tracked_ciks.return_value = [320193]
    bookkeeping.claim_discovery_ciks.return_value = [320193]
    context = _context(tmp_path)

    with (
        patch.object(
            warehouse_orchestrator,
            "_load_daily_index_for_date",
            side_effect=lambda *, target_date, **kw: _stub_index_result(target_date=target_date),
        ) as load_daily_index,
        patch.object(
            warehouse_orchestrator,
            "_run_submissions_bronze_then_silver",
            return_value={"raw_writes": [], "rows_written": 0, "rows_skipped": 0},
        ) as run_submissions,
    ):
        raw_writes, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=MagicMock(),
            bookkeeping=bookkeeping,
            command_name="daily-incremental",
            arguments=arguments,
            scope={
                "business_date_start": "2026-09-12",
                "business_date_end": "2026-09-12",
            },
            now=datetime(2026, 9, 12, tzinfo=UTC),
            sync_run_id=run_id,
        )
    return raw_writes, metrics, load_daily_index, run_submissions


def test_recurring_attempt_with_unresolved_repair_marker_fails_before_expensive_phases(tmp_path) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    accessions = ["0000320193-26-000001"]
    _, _, manifest = prepare_resume(
        storage, run_id="daily-run", image_identity="sha256:image",
        daily_index_accessions=accessions, selected_accessions=accessions,
    )
    record_terminal_repair(
        storage, run_id="daily-run", accession="0000320193-26-000001", manifest=manifest,
        error_type="WarehouseRuntimeError", error="immutable object already exists with different content",
    )

    with pytest.raises(WarehouseRuntimeError, match="unresolved terminal-repair"):
        _run_daily_incremental(
            tmp_path=tmp_path,
            arguments={"recurring_index_lookback_days": 7},
            run_id="daily-run",
        )


def test_recurring_first_attempt_has_no_manifest_and_proceeds_normally(tmp_path) -> None:
    _raw_writes, metrics, load_daily_index, run_submissions = _run_daily_incremental(
        tmp_path=tmp_path,
        arguments={"recurring_index_lookback_days": 7},
        run_id="daily-run",
    )

    load_daily_index.assert_called()
    run_submissions.assert_called_once()
    assert metrics["sync_status"] == "succeeded"


def test_non_recurring_attempt_skips_the_gate_entirely_even_with_a_marker_present(tmp_path) -> None:
    storage = StorageLocation(str(tmp_path / "warehouse"))
    accessions = ["0000320193-26-000001"]
    _, _, manifest = prepare_resume(
        storage, run_id="daily-run", image_identity="sha256:image",
        daily_index_accessions=accessions, selected_accessions=accessions,
    )
    record_terminal_repair(
        storage, run_id="daily-run", accession="0000320193-26-000001", manifest=manifest,
        error_type="WarehouseRuntimeError", error="immutable object already exists with different content",
    )

    # recurring_index_lookback_days=0 (the non-recurring path) never calls
    # prepare_resume downstream either -- the gate matches that same condition.
    _raw_writes, metrics, load_daily_index, run_submissions = _run_daily_incremental(
        tmp_path=tmp_path,
        arguments={"recurring_index_lookback_days": 0},
        run_id="daily-run",
    )

    load_daily_index.assert_called()
    run_submissions.assert_called_once()
    assert metrics["sync_status"] == "succeeded"


def test_recurring_attempt_after_repair_attestation_proceeds_normally(tmp_path) -> None:
    from edgar_warehouse.application.daily_artifact_resume import record_repair_attestation

    storage = StorageLocation(str(tmp_path / "warehouse"))
    accessions = ["0000320193-26-000001"]
    _, _, manifest = prepare_resume(
        storage, run_id="daily-run", image_identity="sha256:image",
        daily_index_accessions=accessions, selected_accessions=accessions,
    )
    record_terminal_repair(
        storage, run_id="daily-run", accession="0000320193-26-000001", manifest=manifest,
        error_type="WarehouseRuntimeError", error="immutable object already exists with different content",
    )
    record_repair_attestation(
        storage, run_id="daily-run", accession="0000320193-26-000001", manifest=manifest,
        operator_identity="operator@example.com", repair_action="registered byte-exact content",
        conflict_evidence={"expected_sha256": "a" * 64},
    )

    _raw_writes, metrics, load_daily_index, run_submissions = _run_daily_incremental(
        tmp_path=tmp_path,
        arguments={"recurring_index_lookback_days": 7},
        run_id="daily-run",
    )

    load_daily_index.assert_called()
    run_submissions.assert_called_once()
    assert metrics["sync_status"] == "succeeded"
