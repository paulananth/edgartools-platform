from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
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


def test_scheduled_daily_incremental_carries_forced_index_accession_union(tmp_path) -> None:
    db = MagicMock()
    db.get_company_sync_state.return_value = {"tracking_status": "active"}
    db.get_tracked_ciks.return_value = [100, 200]
    db.claim_discovery_ciks.return_value = [100, 200]
    context = _context(tmp_path)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)

    def load_index(*, target_date, **kwargs):
        return {
            "raw_writes": [],
            "rows_written": 1,
            "rows_skipped": 0,
            "impacted_ciks": [100 if target_date.day % 2 else 200],
            "accession_numbers": [f"accession-{target_date.isoformat()}"],
            "candidate_rows": [
                {
                    "accession_number": f"accession-{target_date.isoformat()}",
                    "cik": 100 if target_date.day % 2 else 200,
                    "form": "4",
                    "filing_date": target_date,
                }
            ],
            "status": "succeeded",
        }

    with (
        patch.object(
            warehouse_orchestrator,
            "_load_daily_index_for_date",
            side_effect=load_index,
        ) as load_daily_index,
        patch.object(
            warehouse_orchestrator,
            "_run_submissions_bronze_then_silver",
            return_value={"raw_writes": [], "rows_written": 0, "rows_skipped": 0},
        ) as run_submissions,
    ):
        warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="daily-incremental",
            arguments={"recurring_index_lookback_days": 7},
            scope={
                "business_date_start": "2026-07-29",
                "business_date_end": "2026-07-29",
            },
            now=now,
            sync_run_id="daily-run",
        )

    assert [call.kwargs["target_date"] for call in load_daily_index.call_args_list] == [
        date(2026, 7, day) for day in range(23, 30)
    ]
    assert all(call.kwargs["force"] for call in load_daily_index.call_args_list)
    assert run_submissions.call_args.kwargs["recurring_mode"] is True
    assert run_submissions.call_args.kwargs["required_accessions"] == {
        f"accession-2026-07-{day:02d}" for day in range(23, 30)
    }
    assert set(run_submissions.call_args.kwargs["required_candidate_rows"]) == {
        f"accession-2026-07-{day:02d}" for day in range(23, 30)
    }


def test_scheduled_daily_processes_index_union_when_no_cik_claim_is_available(tmp_path) -> None:
    db = MagicMock()
    db.get_tracked_ciks.return_value = [100]
    db.claim_discovery_ciks.return_value = []
    context = _context(tmp_path)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    index_result = {
        "raw_writes": [],
        "rows_written": 1,
        "rows_skipped": 0,
        "impacted_ciks": [100],
        "accession_numbers": ["daily-accession"],
        "candidate_rows": [
            {
                "accession_number": "daily-accession",
                "cik": 100,
                "form": "4",
                "filing_date": date(2026, 7, 29),
            }
        ],
        "status": "succeeded",
    }

    with (
        patch.object(
            warehouse_orchestrator,
            "_load_daily_index_for_date",
            return_value=index_result,
        ),
        patch.object(
            warehouse_orchestrator,
            "_run_submissions_bronze_then_silver",
            return_value={"raw_writes": [], "rows_written": 0, "rows_skipped": 0},
        ) as run_submissions,
    ):
        warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="daily-incremental",
            arguments={"recurring_index_lookback_days": 1},
            scope={
                "business_date_start": "2026-07-29",
                "business_date_end": "2026-07-29",
            },
            now=now,
            sync_run_id="daily-run",
        )

    run_submissions.assert_called_once()
    assert run_submissions.call_args.kwargs["ciks"] == []
    assert run_submissions.call_args.kwargs["required_accessions"] == {"daily-accession"}


def test_forced_daily_index_result_exposes_exact_accessions_and_candidate_rows() -> None:
    db = MagicMock()
    db.get_daily_index_checkpoint.return_value = None
    db.merge_daily_index_filings.side_effect = lambda rows, _run_id: len(rows)
    payload = (
        b"4  TEST COMPANY  1001  20260729  "
        b"edgar/data/1001/0000001001-26-000001-index.html\n"
        b"10-K  OTHER COMPANY  2002  20260729  "
        b"edgar/data/2002/0000002002-26-000002-index.html\n"
    )

    with (
        patch.object(warehouse_orchestrator, "_download_sec_bytes", return_value=payload),
        patch.object(
            warehouse_orchestrator,
            "_write_bronze_object",
            return_value={"sha256": "index-sha", "source_name": "daily_form_index"},
        ),
    ):
        result = warehouse_orchestrator._load_daily_index_for_date(
            context=SimpleNamespace(identity="tester@example.com"),
            db=db,
            target_date=date(2026, 7, 29),
            sync_run_id="daily-run",
            now=datetime(2026, 7, 30, 12, tzinfo=UTC),
            force=True,
        )

    assert result["accession_numbers"] == [
        "0000001001-26-000001",
        "0000002002-26-000002",
    ]
    assert [row["accession_number"] for row in result["candidate_rows"]] == [
        "0000001001-26-000001",
        "0000002002-26-000002",
    ]
    assert result["candidate_rows"][0]["form"] == "4"


def test_daily_incremental_cli_accepts_recurring_index_lookback() -> None:
    from edgar_warehouse.cli import build_parser

    args = build_parser().parse_args(
        ["daily-incremental", "--recurring-index-lookback-days", "7"]
    )
    assert args.recurring_index_lookback_days == 7


def test_daily_incremental_cli_is_bounded_by_default() -> None:
    from edgar_warehouse import cli

    args = cli.build_parser().parse_args(["daily-incremental"])
    with patch.object(cli, "run_command", return_value=0) as run_command:
        args.handler(args)
    assert run_command.call_args.args[1].recurring_index_lookback_days == 7


def test_daily_incremental_cli_preserves_explicit_date_range_discovery() -> None:
    from edgar_warehouse import cli

    args = cli.build_parser().parse_args(
        ["daily-incremental", "--start-date", "2026-01-01", "--end-date", "2026-07-29"]
    )
    with patch.object(cli, "run_command", return_value=0) as run_command:
        args.handler(args)
    assert run_command.call_args.args[1].recurring_index_lookback_days == 0


def test_daily_incremental_cli_gated_capture_flag_is_off_by_default() -> None:
    from edgar_warehouse.cli import build_parser

    args = build_parser().parse_args(["daily-incremental"])
    assert args.enable_filing_artifact_gated_capture is False


def test_daily_incremental_cli_gated_capture_flag_can_be_enabled() -> None:
    from edgar_warehouse.cli import build_parser

    args = build_parser().parse_args(
        ["daily-incremental", "--enable-filing-artifact-gated-capture"]
    )
    assert args.enable_filing_artifact_gated_capture is True


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
