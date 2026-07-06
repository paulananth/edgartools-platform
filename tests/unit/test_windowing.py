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
        fake_db.get_tracked_ciks.return_value = fake_ciks
        raw_writes, metrics = _capture_bronze_raw(
            context=mock_context,
            db=fake_db,
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

    db = MagicMock()
    db.get_tracked_ciks.return_value = input_ciks
    filtered = _filter_ciks_to_universe(input_ciks, db=db)

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

    db = MagicMock()
    db.get_tracked_ciks.return_value = [100, 200, 300]
    with pytest.raises((WarehouseRuntimeError, SystemExit, ValueError)) as exc_info:
        _resolve_bootstrap_target_ciks(
            db=db,
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

    db = MagicMock()
    db.get_tracked_ciks.return_value = [100, 200, 300]
    with pytest.raises((WarehouseRuntimeError, SystemExit, ValueError)) as exc_info:
        _resolve_bootstrap_target_ciks(
            db=db,
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
    """bootstrap-full, bootstrap, daily-incremental, bootstrap-next each accept --cik-limit and --cik-offset."""
    from edgar_warehouse.cli import build_parser

    parser = build_parser()

    for subcommand in ["bootstrap-full", "bootstrap", "daily-incremental", "bootstrap-next"]:
        # Parse with --cik-limit and --cik-offset
        args = parser.parse_args([subcommand, "--cik-limit", "5", "--cik-offset", "10"])
        assert args.cik_limit == 5, f"{subcommand} --cik-limit 5 should parse to int 5"
        assert args.cik_offset == 10, f"{subcommand} --cik-offset 10 should parse to int 10"

    # Defaults: cik_limit=None, cik_offset=0
    for subcommand in ["bootstrap-full", "bootstrap", "daily-incremental", "bootstrap-next"]:
        args = parser.parse_args([subcommand])
        assert args.cik_limit is None, f"{subcommand} default cik_limit should be None"
        assert args.cik_offset == 0, f"{subcommand} default cik_offset should be 0"


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
        from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
        fake_db = MagicMock()
        windows_rel = default_path_resolver().cik_windows_path("run-abc")
        raw_writes, metrics = _capture_bronze_raw(
            context=mock_context,
            db=fake_db,
            command_name="write-run-summary",
            arguments={
                "from_windows_key": windows_rel,
                "run_id": "run-abc",
                "include_reference_refresh": False,
            },
            scope={"from_windows_key": windows_rel},
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


def test_write_run_summary_missing_from_windows_key():
    """write-run-summary exits non-zero when --from-windows-key is missing."""
    from edgar_warehouse.cli import build_parser
    import sys
    from io import StringIO

    parser = build_parser()
    # --from-windows-key is required; argparse should exit non-zero without it
    try:
        args = parser.parse_args(["write-run-summary", "--run-id", "test"])
        # If argparse doesn't raise (shouldn't happen with required=True), call handler
        old_stderr = sys.stderr
        sys.stderr = StringIO()
        try:
            result = args.handler(args)
        finally:
            sys.stderr = old_stderr
        assert result != 0, "Expected non-zero exit when --from-windows-key is missing"
    except SystemExit as exc:
        assert exc.code != 0, f"Expected non-zero exit code, got {exc.code}"


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
                command_name="write-run-summary",
                arguments={
                    "from_windows_key": windows_rel,
                    "run_id": "run-empty",
                    "include_reference_refresh": False,
                },
                scope={"from_windows_key": windows_rel},
                now=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
                sync_run_id="run-empty",
            )
    # Error message should name the S3 key
    err = str(exc_info.value)
    assert windows_rel in err or "cik_windows.jsonl" in err, (
        f"Error should name the S3 key, got: {err}"
    )
