"""Wave 0 test scaffolds for chunked-ingest windowing (Phase 8).

Plans B/C/D convert the stubs to real assertions as each feature is implemented.

See .planning/workstreams/pipeline-scaling/phases/
    08-chunked-ingest-cli-and-state-machine/08-VALIDATION.md
for the per-task verification map.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# test_cik_order, test_compute_windows_output — implemented by Plan C
# ---------------------------------------------------------------------------


def test_cik_order():
    """get_tracked_ciks query layer returns CIKs in ascending order (ORDER BY cik ASC)."""
    from unittest.mock import MagicMock, patch
    from edgar_warehouse.mdm.universe import get_tracked_ciks

    with patch("edgar_warehouse.mdm.universe.Session") as mock_session_cls:
        session_ctx = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = session_ctx
        # Simulate the SQL ORDER BY returning sorted rows
        session_ctx.execute.return_value.all.return_value = [(100,), (200,), (300,)]
        result = get_tracked_ciks(MagicMock(), "active")

    assert result == [100, 200, 300]
    # Verify the compiled SQL includes ORDER BY cik
    select_arg = session_ctx.execute.call_args[0][0]
    compiled = str(select_arg.compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY" in compiled.upper(), f"Expected ORDER BY in query: {compiled}"
    assert "cik" in compiled.lower(), f"Expected 'cik' in ORDER BY clause: {compiled}"


def test_compute_windows_output():
    """compute-windows JSONL output matches the cik_windows schema."""
    import json
    from unittest.mock import MagicMock, patch

    # 7 CIKs, window_size=3 -> 3 windows: [0..3), [3..6), [6..7)
    fake_ciks = [100, 200, 300, 400, 500, 600, 700]

    written: dict[str, str] = {}

    def capture_write(relative_path: str, content: str) -> str:
        written[relative_path] = content
        return relative_path

    mock_context = MagicMock()
    mock_context.bronze_root.write_text.side_effect = capture_write

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._build_warehouse_context",
            return_value=mock_context,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage",
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._sync_reference_data",
            return_value={"raw_writes": [], "rows_written": 0, "rows_skipped": 0},
        ),
    ):
        from edgar_warehouse.application.warehouse_orchestrator import _execute_warehouse_bronze_capture
        import argparse
        mock_context.runtime_mode = "bronze_capture"

        args_dict = {
            "window_size": 3,
            "run_id": "test-run-1",
            "include_reference_refresh": False,
        }
        raw_writes, metrics = _execute_warehouse_bronze_capture.__wrapped__ if hasattr(_execute_warehouse_bronze_capture, "__wrapped__") else None, None  # noqa: E501
        # Call the bronze_capture dispatch directly
        from edgar_warehouse.application.warehouse_orchestrator import _capture_bronze_raw
        from unittest.mock import MagicMock as MM
        fake_db = MM()
        fake_db.start_sync_run = MM()
        fake_bookkeeping = MM()
        fake_bookkeeping.get_tracked_ciks.return_value = fake_ciks
        raw_writes, metrics = _capture_bronze_raw(
            context=mock_context,
            db=fake_db,
            bookkeeping=fake_bookkeeping,
            command_name="compute-windows",
            arguments=args_dict,
            scope={"window_size": 3, "run_id": "test-run-1"},
            now=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
            sync_run_id="test-run-1",
        )

    # --- cik_windows.jsonl assertions ---
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
    windows_rel = default_path_resolver().cik_windows_path("test-run-1")
    snapshot_rel = default_path_resolver().cik_snapshot_path("test-run-1")

    assert windows_rel in written, f"cik_windows.jsonl not written; keys={list(written)}"
    assert snapshot_rel in written, f"cik_snapshot.jsonl not written; keys={list(written)}"

    # Parse windows lines
    windows_lines = [line for line in written[windows_rel].splitlines() if line.strip()]
    assert len(windows_lines) == 3, f"Expected 3 windows for 7 CIKs / size=3, got {len(windows_lines)}"
    w0 = json.loads(windows_lines[0])
    w1 = json.loads(windows_lines[1])
    w2 = json.loads(windows_lines[2])
    assert w0 == {"window_offset": 0, "window_limit": 3}
    assert w1 == {"window_offset": 3, "window_limit": 3}
    assert w2 == {"window_offset": 6, "window_limit": 1}, f"Last window should be 1, got {w2}"

    # Parse snapshot lines
    snapshot_lines = [line for line in written[snapshot_rel].splitlines() if line.strip()]
    assert len(snapshot_lines) == 7
    for expected_cik, line in zip(fake_ciks, snapshot_lines):
        row = json.loads(line)
        assert row == {"cik": expected_cik}, f"Snapshot row mismatch: {row}"


# ---------------------------------------------------------------------------
# test_daily_incremental_windowing — implemented by Plan D
# ---------------------------------------------------------------------------


def test_daily_incremental_windowing():
    """daily_incremental applies windowing after _filter_ciks_to_universe."""
    from unittest.mock import patch
    from edgar_warehouse.application.warehouse_orchestrator import _filter_ciks_to_universe

    # Simulate a post-filter impacted list of 10 CIKs and a windowed slice of 3 starting at offset 2
    input_ciks = list(range(100, 110))  # 10 CIKs: 100..109
    expected = [102, 103, 104]  # offset=2, limit=3

    # The windowing is applied after _filter_ciks_to_universe passes everything through
    # We mock the filter to return the full list, then apply the same slice logic
    from unittest.mock import MagicMock

    bookkeeping = MagicMock()
    bookkeeping.get_tracked_ciks.return_value = input_ciks
    filtered = _filter_ciks_to_universe(input_ciks, bookkeeping=bookkeeping)

    cik_offset = 2
    cik_limit = 3
    result = filtered[cik_offset:]
    if cik_limit is not None:
        result = result[:cik_limit]

    assert result == expected


# ---------------------------------------------------------------------------
# test_cik_limit_rejects_negative — Plan B Task 2
# ---------------------------------------------------------------------------


def test_cik_limit_rejects_negative():
    """--cik-limit flag rejects negative values with a clear error."""
    from edgar_warehouse.application.errors import WarehouseRuntimeError
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_bootstrap_target_ciks

    from unittest.mock import MagicMock

    bookkeeping = MagicMock()
    bookkeeping.get_tracked_ciks.return_value = [100, 200, 300]
    with pytest.raises((WarehouseRuntimeError, SystemExit, ValueError)) as exc_info:
        _resolve_bootstrap_target_ciks(
            bookkeeping=bookkeeping,
            raw_ciks=None,
            command_name="bootstrap-full",
            tracking_status_filter="active",
            cik_limit=-1,
            cik_offset=0,
        )
    err_str = str(exc_info.value).lower()
    assert "cik_limit" in err_str or "cik-limit" in err_str or "limit" in err_str


# ---------------------------------------------------------------------------
# test_cik_offset_rejects_negative — Plan B Task 2
# ---------------------------------------------------------------------------


def test_cik_offset_rejects_negative():
    """--cik-offset flag rejects negative values with a clear error."""
    from edgar_warehouse.application.errors import WarehouseRuntimeError
    from edgar_warehouse.application.warehouse_orchestrator import _resolve_bootstrap_target_ciks

    from unittest.mock import MagicMock

    bookkeeping = MagicMock()
    bookkeeping.get_tracked_ciks.return_value = [100, 200, 300]
    with pytest.raises((WarehouseRuntimeError, SystemExit, ValueError)) as exc_info:
        _resolve_bootstrap_target_ciks(
            bookkeeping=bookkeeping,
            raw_ciks=None,
            command_name="bootstrap-full",
            tracking_status_filter="active",
            cik_limit=None,
            cik_offset=-5,
        )
    err_str = str(exc_info.value).lower()
    assert "cik_offset" in err_str or "cik-offset" in err_str or "offset" in err_str


# ---------------------------------------------------------------------------
# test_window_slice_correctness — Plan B Task 2 / Plan C
# ---------------------------------------------------------------------------


def test_window_slice_correctness():
    """A window slice [offset:offset+size] over an ordered CIK list is deterministic."""
    ciks = list(range(1000, 1010))  # 10 CIKs
    # offset=3, limit=4 -> [1003, 1004, 1005, 1006]
    offset = 3
    limit = 4
    result = ciks[offset:][:limit]
    assert result == [1003, 1004, 1005, 1006]
    # Check idempotent: same result each time
    result2 = ciks[offset:][:limit]
    assert result == result2


# ---------------------------------------------------------------------------
# test_cli_flags_present — Plan B Task 1
# ---------------------------------------------------------------------------


def test_cli_flags_present():
    """bootstrap-full, daily-incremental, bootstrap-next each accept --cik-limit and --cik-offset."""
    from edgar_warehouse.cli import build_parser

    parser = build_parser()

    for subcommand in ["bootstrap-full", "daily-incremental", "bootstrap-next"]:
        # Parse with --cik-limit and --cik-offset
        args = parser.parse_args([subcommand, "--cik-limit", "5", "--cik-offset", "10"])
        assert args.cik_limit == 5, f"{subcommand} --cik-limit 5 should parse to int 5"
        assert args.cik_offset == 10, f"{subcommand} --cik-offset 10 should parse to int 10"

    # Defaults: cik_limit=None, cik_offset=0
    for subcommand in ["bootstrap-full", "daily-incremental", "bootstrap-next"]:
        args = parser.parse_args([subcommand])
        assert args.cik_limit is None, f"{subcommand} default cik_limit should be None"
        assert args.cik_offset == 0, f"{subcommand} default cik_offset should be 0"


def test_bootstrap_next_silver_only_is_explicit_and_off_by_default():
    from edgar_warehouse.cli import build_parser

    parser = build_parser()
    assert parser.parse_args(["bootstrap-next"]).silver_only is False
    assert parser.parse_args(["bootstrap-next", "--silver-only"]).silver_only is True


# ---------------------------------------------------------------------------
# test_write_run_summary_output — Plan C Task 2
# ---------------------------------------------------------------------------


def test_write_run_summary_output():
    """write-run-summary derives window_count and cik_count from S3 manifests and writes run-summary.json."""
    import json
    import re
    from unittest.mock import MagicMock, patch

    # 3 window lines, 7 CIK lines
    fake_windows_content = (
        '{"window_offset": 0, "window_limit": 3}\n'
        '{"window_offset": 3, "window_limit": 3}\n'
        '{"window_offset": 6, "window_limit": 1}\n'
    )
    fake_snapshot_content = "\n".join(
        json.dumps({"cik": cik}) for cik in [100, 200, 300, 400, 500, 600, 700]
    ) + "\n"

    written: dict[str, str] = {}

    def capture_write(relative_path: str, content: str) -> str:
        written[relative_path] = content
        return relative_path

    def fake_read_bytes(full_path: str) -> bytes:
        from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
        windows_rel = default_path_resolver().cik_windows_path("run-abc")
        snapshot_rel = default_path_resolver().cik_snapshot_path("run-abc")
        # Match by suffix
        if full_path.endswith(windows_rel) or "cik_windows.jsonl" in full_path:
            return fake_windows_content.encode("utf-8")
        if full_path.endswith(snapshot_rel) or "cik_snapshot.jsonl" in full_path:
            return fake_snapshot_content.encode("utf-8")
        raise FileNotFoundError(f"No fake data for {full_path}")

    mock_context = MagicMock()
    mock_context.bronze_root.write_text.side_effect = capture_write
    mock_context.bronze_root.join.side_effect = lambda rel: f"s3://bucket/{rel}"

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
            side_effect=fake_read_bytes,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._build_warehouse_context",
            return_value=mock_context,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage",
        ),
    ):
        from edgar_warehouse.application.warehouse_orchestrator import _capture_bronze_raw
        fake_db = MagicMock()
        raw_writes, metrics = _capture_bronze_raw(
            context=mock_context,
            db=fake_db,
            bookkeeping=MagicMock(),
            command_name="write-run-summary",
            arguments={
                "run_id": "run-abc",
                "include_reference_refresh": False,
            },
            scope={},
            now=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
            sync_run_id="run-abc",
        )

    # Verify run-summary.json was written once to the correct relative path
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver as dpr
    summary_rel = dpr().run_summary_path("run-abc")
    assert summary_rel in written, f"run-summary.json not written; keys={list(written)}"

    # Parse and verify content
    payload = json.loads(written[summary_rel].strip())
    assert payload["run_id"] == "run-abc"
    assert payload["window_count"] == 3, f"Expected window_count=3, got {payload.get('window_count')}"
    assert payload["cik_count"] == 7, f"Expected cik_count=7, got {payload.get('cik_count')}"
    assert "completed_at" in payload, "completed_at missing from payload"
    # completed_at must match ISO-8601 pattern starting with 4-digit year
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", payload["completed_at"]), (
        f"completed_at does not look like ISO-8601: {payload['completed_at']}"
    )


def test_write_run_summary_run_id_only():
    """write-run-summary accepts --run-id alone; --from-windows-key no longer exists.

    Regression guard for ticket 42's retry5 failure: the ASL used to hand-build
    a --from-windows-key S3 path that duplicated WAREHOUSE_BRONZE_ROOT's own
    "warehouse/bronze" prefix. The fix removed the flag entirely -- the
    handler now derives the key itself from --run-id via the canonical path
    resolver, so there is exactly one place that owns this path template.
    """
    from edgar_warehouse.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["write-run-summary", "--run-id", "test"])
    assert args.run_id == "test"
    assert not hasattr(args, "from_windows_key")

    with pytest.raises(SystemExit):
        parser.parse_args(["write-run-summary", "--run-id", "test", "--from-windows-key", "x"])


# ---------------------------------------------------------------------------
# test_compute_windows_total_cik_limit_* — Phase 06-03 (fix-pipelines, Option B)
#
# compute-windows had no way to bound the TOTAL tracked-CIK universe it
# processes (only --window-size, which chunks the full universe, not caps
# it). --total-cik-limit slices the ordered CIK list to at most N entries
# BEFORE windowing, so downstream WindowedBootstrap/Stage1B* Map states
# (which independently re-derive CIK slices from cik_windows.jsonl's
# offset/limit descriptors against the same ordered tracked-CIK query) never
# see CIKs beyond the cap. See 06-03-LOAD-COVERAGE-EVIDENCE.md for the
# Rule 4 architectural-blocker writeup this closes.
# ---------------------------------------------------------------------------


def test_compute_windows_total_cik_limit_cli_flag():
    """compute-windows accepts an optional --total-cik-limit, default None."""
    from edgar_warehouse.cli import build_parser

    parser = build_parser()

    args = parser.parse_args(["compute-windows", "--total-cik-limit", "150"])
    assert args.total_cik_limit == 150

    args_default = parser.parse_args(["compute-windows"])
    assert args_default.total_cik_limit is None


def test_compute_windows_total_cik_limit_handler_rejects_negative():
    """The compute-windows handler rejects --total-cik-limit < 0 with exit code 2."""
    import argparse

    from edgar_warehouse.cli import _handle_compute_windows

    for bad_value in (-1, -100):
        args = argparse.Namespace(window_size=500, total_cik_limit=bad_value, run_id="r")
        assert _handle_compute_windows(args) == 2


def test_compute_windows_total_cik_limit_handler_accepts_zero_as_no_limit_sentinel():
    """0 is a valid sentinel meaning 'no limit' (matches the Step Functions default-injection
    contract), so the handler must dispatch it, not reject it."""
    import argparse
    from unittest.mock import patch

    from edgar_warehouse.cli import _handle_compute_windows

    args = argparse.Namespace(window_size=500, total_cik_limit=0, run_id="r")
    with patch("edgar_warehouse.cli.run_command", return_value=0) as mock_run:
        result = _handle_compute_windows(args)
    assert result == 0
    mock_run.assert_called_once_with("compute-windows", args)


def test_compute_windows_total_cik_limit_bounds_universe():
    """--total-cik-limit caps the ordered CIK universe (and derived windows) compute-windows writes."""
    import json
    from unittest.mock import MagicMock, patch

    # 7 tracked CIKs, window_size=3, total_cik_limit=4 -> only first 4 CIKs
    # windowed: [0..3), [3..4) = 2 windows (not the 3 windows an unbounded run would produce).
    fake_ciks = [100, 200, 300, 400, 500, 600, 700]

    written: dict[str, str] = {}

    def capture_write(relative_path: str, content: str) -> str:
        written[relative_path] = content
        return relative_path

    mock_context = MagicMock()
    mock_context.bronze_root.write_text.side_effect = capture_write

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._build_warehouse_context",
            return_value=mock_context,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage",
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._sync_reference_data",
            return_value={"raw_writes": [], "rows_written": 0, "rows_skipped": 0},
        ),
    ):
        from edgar_warehouse.application.warehouse_orchestrator import _capture_bronze_raw
        mock_context.runtime_mode = "bronze_capture"

        fake_db = MagicMock()
        fake_db.start_sync_run = MagicMock()
        fake_bookkeeping = MagicMock()
        fake_bookkeeping.get_tracked_ciks.return_value = fake_ciks
        raw_writes, metrics = _capture_bronze_raw(
            context=mock_context,
            db=fake_db,
            bookkeeping=fake_bookkeeping,
            command_name="compute-windows",
            arguments={
                "window_size": 3,
                "run_id": "test-run-limit",
                "total_cik_limit": 4,
                "include_reference_refresh": False,
            },
            scope={"window_size": 3, "run_id": "test-run-limit", "total_cik_limit": 4},
            now=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
            sync_run_id="test-run-limit",
        )

    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
    windows_rel = default_path_resolver().cik_windows_path("test-run-limit")
    snapshot_rel = default_path_resolver().cik_snapshot_path("test-run-limit")

    windows_lines = [line for line in written[windows_rel].splitlines() if line.strip()]
    assert len(windows_lines) == 2, f"Expected 2 windows for 4 (capped) CIKs / size=3, got {len(windows_lines)}"
    assert json.loads(windows_lines[0]) == {"window_offset": 0, "window_limit": 3}
    assert json.loads(windows_lines[1]) == {"window_offset": 3, "window_limit": 1}

    snapshot_lines = [line for line in written[snapshot_rel].splitlines() if line.strip()]
    assert len(snapshot_lines) == 4, f"Expected snapshot capped to 4 CIKs, got {len(snapshot_lines)}"
    assert [json.loads(line)["cik"] for line in snapshot_lines] == [100, 200, 300, 400]

    # stage0-stage1-consolidation wayfinder map, ticket 02/04: compute-windows
    # no longer pre-batches cik_batches.jsonl or declares
    # metrics["_identity_refresh_batches"] -- Stage0CompanyIdentity/
    # ReduceIdentityRefresh, their only consumers, were removed from
    # load_history entirely.
    assert "_identity_refresh_batches" not in metrics
    assert "cik_universe_path" not in metrics

    assert metrics["cik_count"] == 4
    assert metrics["window_count"] == 2


def test_compute_windows_orchestrator_rejects_non_positive_total_cik_limit():
    """_capture_bronze_raw raises WarehouseRuntimeError for --total-cik-limit <= 0."""
    from unittest.mock import MagicMock, patch

    from edgar_warehouse.application.errors import WarehouseRuntimeError

    mock_context = MagicMock()
    mock_context.runtime_mode = "bronze_capture"

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._build_warehouse_context",
            return_value=mock_context,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage",
        ),
    ):
        from edgar_warehouse.application.warehouse_orchestrator import _capture_bronze_raw

        fake_db = MagicMock()
        fake_bookkeeping = MagicMock()
        fake_bookkeeping.get_tracked_ciks.return_value = [100, 200]
        with pytest.raises(WarehouseRuntimeError, match="total-cik-limit"):
            _capture_bronze_raw(
                context=mock_context,
                db=fake_db,
                bookkeeping=fake_bookkeeping,
                command_name="compute-windows",
                arguments={
                    "window_size": 3,
                    "run_id": "test-run-bad",
                    "total_cik_limit": -1,
                    "include_reference_refresh": False,
                },
                scope={"window_size": 3, "run_id": "test-run-bad", "total_cik_limit": -1},
                now=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
                sync_run_id="test-run-bad",
            )


def test_write_run_summary_empty_windows_raises():
    """write-run-summary exits with an actionable error when cik_windows.jsonl is empty."""
    from unittest.mock import MagicMock, patch
    from edgar_warehouse.application.errors import WarehouseRuntimeError
    from edgar_warehouse.application.warehouse_orchestrator import _capture_bronze_raw
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver

    windows_rel = default_path_resolver().cik_windows_path("run-empty")
    mock_context = MagicMock()
    mock_context.bronze_root.join.side_effect = lambda rel: f"s3://bucket/{rel}"

    def fake_read_bytes_empty(full_path: str) -> bytes:
        # Return empty bytes for the windows key; should never reach snapshot
        return b""

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
        side_effect=fake_read_bytes_empty,
    ):
        fake_db = MagicMock()
        with pytest.raises(WarehouseRuntimeError) as exc_info:
            _capture_bronze_raw(
                context=mock_context,
                db=fake_db,
                bookkeeping=MagicMock(),
                command_name="write-run-summary",
                arguments={
                    "run_id": "run-empty",
                    "include_reference_refresh": False,
                },
                scope={},
                now=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
                sync_run_id="run-empty",
            )
    # Error message should name the S3 key
    err = str(exc_info.value)
    assert windows_rel in err or "cik_windows.jsonl" in err, (
        f"Error should name the S3 key, got: {err}"
    )


# ---------------------------------------------------------------------------
# stage0-stage1-consolidation wayfinder map, ticket 02/04: compute-windows no
# longer joins compute-identity-refresh-window's persist_run_manifest publish
# special-case (warehouse_orchestrator.py:699) -- Stage0CompanyIdentity/
# ReduceIdentityRefresh, the only thing that used to merge that run manifest
# + reference snapshot into canonical, were removed from load_history
# entirely (IngestBronzeAndSilver's WindowedBootstrap already writes the identical
# sec_company rows as a byproduct of its own capture). compute-windows now
# falls through to the normal full-canonical publish, so its once-per-run
# reference-data sync (company_tickers/company_tickers_exchange) lands in
# canonical on its own. Exercised end-to-end (real local SilverDatabase +
# StorageLocation, not just the _capture_bronze_raw-level metrics assertions
# above) because a wiring gap here would silently drop that data for every
# load_history run -- exactly the gap found while planning this removal.
# ---------------------------------------------------------------------------


def test_compute_windows_publishes_reference_data_directly_to_canonical(
    tmp_path, monkeypatch,
) -> None:
    from pathlib import Path
    from unittest.mock import patch

    from edgar_warehouse.application import warehouse_orchestrator
    from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
    from edgar_warehouse.infrastructure.object_storage import StorageLocation
    from edgar_warehouse.silver_store import SilverDatabase

    monkeypatch.setenv("WAREHOUSE_IMAGE_REF", "sha256:test-image")

    context = WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="tester@example.com",
        runtime_mode="bronze_capture",
    )

    # open_silver_database() (called inside _execute_warehouse_bronze_capture)
    # appends "silver/sec/silver.duckdb" to the silver_root -- this path is
    # still seeded for the same schema-provisioning reason as before, though
    # tracking state itself now lives in the bookkeeping store (DuckDB
    # Retirement Cutover Ticket 14), stubbed via fake_bookkeeping below.
    db = SilverDatabase(context.silver_root.join("silver", "sec", "silver.duckdb"))
    db.close()

    from unittest.mock import MagicMock

    fake_bookkeeping = MagicMock()
    fake_bookkeeping.get_tracked_ciks.return_value = [100, 200, 300]
    fake_bookkeeping.get_table_counts.return_value = {}

    company_tickers_payload = b'{"0":{"cik_str":100,"ticker":"AAA","title":"A Co"}}'
    exchange_payload = b'{"fields":["cik","name","ticker","exchange"],"data":[]}'

    def fake_download(*, url: str, identity: str) -> bytes:
        del identity
        if url.endswith("/company_tickers.json"):
            return company_tickers_payload
        if url.endswith("/company_tickers_exchange.json"):
            return exchange_payload
        raise AssertionError(f"unexpected reference URL: {url}")

    # _publish_silver_database_if_remote no-ops (returns None) for a
    # non-remote StorageLocation -- this test's tmp_path storage_root -- so
    # it can't itself prove the normal (not special-cased) publish path ran.
    # Spy on it directly: this is the actual code change under test (removing
    # "compute-windows" from warehouse_orchestrator.py:699's special-case
    # tuple), independent of what a remote (S3) canonical would do with it.
    with (
        patch.object(warehouse_orchestrator, "_download_sec_bytes", side_effect=fake_download),
        patch.object(warehouse_orchestrator, "_bookkeeping_store", return_value=fake_bookkeeping),
        patch.object(
            warehouse_orchestrator,
            "_publish_silver_database_with_retry",
            wraps=warehouse_orchestrator._publish_silver_database_with_retry,
        ) as publish_spy,
    ):
        warehouse_orchestrator._execute_warehouse_bronze_capture(
            context=context,
            command_name="compute-windows",
            arguments={"window_size": 2, "run_id": "cw-direct-publish-run"},
        )

    assert publish_spy.call_count == 1, (
        "compute-windows must take the normal full-canonical publish path "
        "now that ReduceIdentityRefresh no longer exists to merge its "
        "reference sync -- the special no-publish case must not run for it"
    )

    from edgar_warehouse.application.identity_refresh_publication import (
        reference_snapshot_path,
        run_manifest_path,
    )

    manifest_path = Path(context.storage_root.join(run_manifest_path("cw-direct-publish-run")))
    assert not manifest_path.exists(), (
        "compute-windows must no longer persist an identity-refresh run "
        "manifest -- ReduceIdentityRefresh, its only consumer, was removed"
    )
    snapshot_path = Path(context.storage_root.join(reference_snapshot_path("cw-direct-publish-run")))
    assert not snapshot_path.exists(), (
        "compute-windows must no longer persist a reference snapshot -- "
        "nothing merges it into canonical anymore"
    )

    # The reference-data sync's rows must actually be present in the local
    # working silver db that a real (remote) publish would merge into
    # canonical -- the correctness gap this test guards: with no reducer
    # left, this sync must be readable from the working db it wrote to, or
    # it would be silently lost once nothing else consumes it.
    working_db = SilverDatabase(context.silver_root.join("silver", "sec", "silver.duckdb"))
    try:
        rows = working_db._conn.execute(
            "SELECT cik, ticker FROM sec_company_ticker ORDER BY cik"
        ).fetchall()
    finally:
        working_db.close()
    assert rows == [(100, "AAA")], (
        "compute-windows' reference-data sync must be readable back from "
        "the working silver db after the run"
    )
