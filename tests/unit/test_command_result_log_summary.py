"""Tests for ops-cost-control ticket 02: bound the `raw_writes` field a
command result prints to stdout instead of dumping one write receipt per
document. The full list stays durable elsewhere (pipeline_run.raw_writes_json
in the published silver database, plus the underlying S3 objects) -- see
ops-cost-control ticket 01 for the production measurement that found this
dump was the single largest contributor to CloudWatch log volume.
"""
from __future__ import annotations

from argparse import Namespace
from unittest.mock import patch

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.workflows import command_runner


def _raw_write(i: int) -> dict:
    return {
        "layer": "bronze_raw",
        "path": f"s3://bucket/bronze/doc-{i}.xml",
        "relative_path": f"doc-{i}.xml",
        "sha256": f"sha-{i}",
        "cik": 320193,
        "cached": False,
    }


def test_small_raw_writes_list_is_unchanged():
    payload = {"command": "bootstrap-next", "raw_writes": [_raw_write(0), _raw_write(1)]}
    result = warehouse_orchestrator._command_result_for_log(payload)
    assert result is payload
    assert result["raw_writes"] == [_raw_write(0), _raw_write(1)]


def test_raw_writes_list_at_exactly_the_sample_size_is_unchanged():
    limit = warehouse_orchestrator.COMMAND_RESULT_RAW_WRITES_LOG_SAMPLE
    raw_writes = [_raw_write(i) for i in range(limit)]
    payload = {"command": "bootstrap-next", "raw_writes": raw_writes}
    result = warehouse_orchestrator._command_result_for_log(payload)
    assert result is payload
    assert "raw_writes_total_count" not in result


def test_large_raw_writes_list_is_bounded_to_the_sample_size():
    raw_writes = [_raw_write(i) for i in range(5583)]
    payload = {"command": "bootstrap-next", "raw_writes": raw_writes, "bronze_object_count": 5583}
    result = warehouse_orchestrator._command_result_for_log(payload)
    limit = warehouse_orchestrator.COMMAND_RESULT_RAW_WRITES_LOG_SAMPLE
    assert len(result["raw_writes"]) == limit
    assert result["raw_writes"] == raw_writes[:limit]
    assert result["raw_writes_total_count"] == 5583
    assert result["raw_writes_sample_size"] == limit


def test_bounding_does_not_mutate_the_original_payload():
    raw_writes = [_raw_write(i) for i in range(50)]
    payload = {"command": "bootstrap-next", "raw_writes": raw_writes}
    warehouse_orchestrator._command_result_for_log(payload)
    assert len(payload["raw_writes"]) == 50
    assert "raw_writes_total_count" not in payload


def test_required_forensic_fields_survive_bounding():
    """Run/image identity, aggregate counts, and dispositions must not be
    dropped by the summarization -- only `raw_writes` shrinks."""
    raw_writes = [_raw_write(i) for i in range(500)]
    payload = {
        "command": "bootstrap-next",
        "run_id": "run-abc123",
        "runtime_mode": "bronze_capture",
        "status": "ok",
        "message": "Warehouse bronze capture completed successfully.",
        "bronze_object_count": 500,
        "silver_table_counts": {"sec_company": 1},
        "gold_row_counts": {"company": 1},
        "snowflake_export_row_counts": {"company": 1},
        "raw_writes": raw_writes,
    }
    result = warehouse_orchestrator._command_result_for_log(payload)
    for field in (
        "command",
        "run_id",
        "runtime_mode",
        "status",
        "message",
        "bronze_object_count",
        "silver_table_counts",
        "gold_row_counts",
        "snowflake_export_row_counts",
    ):
        assert result[field] == payload[field]


def test_payload_without_raw_writes_key_is_unchanged():
    payload = {"command": "gold-refresh", "status": "ok"}
    result = warehouse_orchestrator._command_result_for_log(payload)
    assert result is payload


def test_run_command_prints_bounded_raw_writes(capsys):
    raw_writes = [_raw_write(i) for i in range(5583)]
    payload = {
        "command": "bootstrap-next",
        "run_id": "run-abc123",
        "status": "ok",
        "raw_writes": raw_writes,
        "bronze_object_count": 5583,
    }
    with (
        patch.object(warehouse_orchestrator, "_build_warehouse_context") as build_ctx,
        patch.object(warehouse_orchestrator, "_execute_warehouse", return_value=payload),
    ):
        build_ctx.return_value.runtime_mode = "bronze_capture"
        exit_code = warehouse_orchestrator.run_command("bootstrap-next", Namespace())

    assert exit_code == 0
    printed = capsys.readouterr().out
    assert printed.count('"path":') == warehouse_orchestrator.COMMAND_RESULT_RAW_WRITES_LOG_SAMPLE
    assert '"raw_writes_total_count": 5583' in printed
    assert '"bronze_object_count": 5583' in printed
    assert '"run_id": "run-abc123"' in printed


def test_execute_standard_command_prints_bounded_raw_writes(capsys):
    raw_writes = [_raw_write(i) for i in range(5583)]
    payload = {
        "command": "daily-incremental",
        "run_id": "run-def456",
        "status": "ok",
        "raw_writes": raw_writes,
        "bronze_object_count": 5583,
    }
    with (
        patch.object(command_runner, "build_warehouse_context") as build_ctx,
        patch.object(warehouse_orchestrator, "_execute_warehouse", return_value=payload),
    ):
        build_ctx.return_value.runtime_mode = "bronze_capture"
        exit_code = command_runner.execute_standard_command("daily-incremental", Namespace())

    assert exit_code == 0
    printed = capsys.readouterr().out
    assert printed.count('"path":') == warehouse_orchestrator.COMMAND_RESULT_RAW_WRITES_LOG_SAMPLE
    assert '"raw_writes_total_count": 5583' in printed
