"""Unit tests for scripts/ops/watch_release.py event rendering and helpers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "watch_release", REPO_ROOT / "scripts" / "ops" / "watch_release.py"
)
watch_release = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(watch_release)


def test_parser_defaults_to_prod_us_east_1() -> None:
    args = watch_release.build_parser().parse_args([])
    assert args.env == "prod"
    assert args.region == "us-east-1"
    assert args.execution_arn is None
    assert args.interval == 10.0


def test_render_state_entered_and_exited() -> None:
    entered = {
        "type": "TaskStateEntered",
        "timestamp": 1789000000.0,
        "stateEnteredEventDetails": {"name": "StrictMdmVerify"},
    }
    exited = {
        "type": "TaskStateExited",
        "timestamp": 1789000060.0,
        "stateExitedEventDetails": {"name": "StrictMdmVerify"},
    }
    (line_in,) = watch_release.render_event(entered, "prod")
    (line_out,) = watch_release.render_event(exited, "prod")
    assert "> StrictMdmVerify" in line_in
    assert "StrictMdmVerify done" in line_out


def test_render_task_submitted_extracts_ecs_task_id_and_tail_hint() -> None:
    payload = {"Tasks": [{"TaskArn": "arn:aws:ecs:us-east-1:1:task/c/abc123"}]}
    event = {
        "type": "TaskSubmitted",
        "timestamp": 1789000000.0,
        "taskSubmittedEventDetails": {"output": json.dumps(payload)},
    }
    (line,) = watch_release.render_event(event, "prod")
    assert "ECS task abc123 started" in line
    assert "tail-task.sh abc123 --env prod" in line


def test_render_task_submitted_without_ecs_payload_is_silent() -> None:
    event = {
        "type": "TaskSubmitted",
        "timestamp": 1789000000.0,
        "taskSubmittedEventDetails": {"output": "not-json"},
    }
    assert watch_release.render_event(event, "prod") == []


def test_render_execution_failed_includes_error_and_cause() -> None:
    event = {
        "type": "ExecutionFailed",
        "timestamp": 1789000000.0,
        "executionFailedEventDetails": {
            "error": "States.TaskFailed",
            "cause": "batch exited 1",
        },
    }
    (line,) = watch_release.render_event(event, "prod")
    assert "FAILED" in line
    assert "States.TaskFailed" in line
    assert "batch exited 1" in line


def test_map_run_arn_found_from_history() -> None:
    events = [
        {"type": "ExecutionStarted", "timestamp": 0},
        {
            "type": "MapRunStarted",
            "timestamp": 1,
            "mapRunStartedEventDetails": {"mapRunArn": "arn:aws:states:::mapRun/x"},
        },
    ]
    assert watch_release.map_run_arn_from(events) == "arn:aws:states:::mapRun/x"
    assert watch_release.map_run_arn_from([events[0]]) is None


def test_format_map_progress_counts() -> None:
    line = watch_release.format_map_progress(
        {"total": 56, "succeeded": 12, "running": 4, "pending": 40, "failed": 0}
    )
    assert "12/56 batches succeeded" in line
    assert "4 running" in line
    assert "40 pending" in line
    assert "0 failed" in line


def test_exit_codes_map_terminal_statuses() -> None:
    assert watch_release.exit_code_for("SUCCEEDED") == 0
    for status in ("FAILED", "ABORTED", "TIMED_OUT"):
        assert watch_release.exit_code_for(status) == 2
