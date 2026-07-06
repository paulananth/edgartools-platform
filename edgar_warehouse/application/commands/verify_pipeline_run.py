"""verify-pipeline-run command module."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from edgar_warehouse.application.command_context_factory import build_warehouse_context
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import read_bytes


def execute(args: Any) -> int:
    from edgar_warehouse.application import warehouse_orchestrator

    arguments = warehouse_orchestrator._namespace_to_payload(args)
    try:
        context = build_warehouse_context("verify-pipeline-run")
        report = verify_pipeline_run(
            context=context,
            run_id=str(arguments.get("run_id") or ""),
        )
    except WarehouseRuntimeError as exc:
        print(
            json.dumps(
                warehouse_orchestrator._error_payload(
                    "verify-pipeline-run",
                    arguments,
                    str(exc),
                    runtime_mode="bronze_capture",
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ok" else 1


def verify_pipeline_run(
    *,
    context: WarehouseCommandContext,
    run_id: str,
) -> dict[str, Any]:
    if not run_id:
        raise WarehouseRuntimeError("run_id is required")

    from edgar_warehouse.application.warehouse_orchestrator import (
        _hydrate_silver_database_from_storage,
        _publish_silver_database_if_remote,
    )
    from edgar_warehouse.silver_support.session import open_silver_database

    _hydrate_silver_database_from_storage(context)
    db = open_silver_database(context.silver_root)
    try:
        row = db.get_pipeline_run(run_id)
        if row is None:
            raise WarehouseRuntimeError(f"pipeline_run not found for run_id={run_id}")

        raw_writes = _json_list(row.get("raw_writes_json"))
        writes = _json_list(row.get("writes_json"))
        report = _verify_records(run_id=run_id, raw_writes=raw_writes, writes=writes)
        db.record_pipeline_verification(
            run_id,
            verification_status=report["status"],
            report=report,
        )
    finally:
        db.close()

    _publish_silver_database_if_remote(context)
    return report


def _json_list(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []


def _verify_records(
    *,
    run_id: str,
    raw_writes: list[dict[str, Any]],
    writes: list[dict[str, Any]],
) -> dict[str, Any]:
    missing_paths: list[dict[str, Any]] = []
    hash_mismatches: list[dict[str, Any]] = []
    hashes_checked = 0
    paths_checked = 0

    for record in raw_writes + [write for write in writes if write.get("sha256")]:
        path = str(record.get("path") or "")
        if not path:
            missing_paths.append({"layer": record.get("layer"), "path": path})
            continue
        try:
            payload = read_bytes(path)
        except Exception as exc:
            missing_paths.append(
                {"layer": record.get("layer"), "path": path, "error": str(exc)}
            )
            continue
        paths_checked += 1
        expected = str(record.get("sha256") or "")
        if expected:
            hashes_checked += 1
            actual = hashlib.sha256(payload).hexdigest()
            if actual != expected:
                hash_mismatches.append(
                    {
                        "layer": record.get("layer"),
                        "path": path,
                        "expected_sha256": expected,
                        "actual_sha256": actual,
                    }
                )

    status = "ok" if not missing_paths and not hash_mismatches else "failed"
    return {
        "run_id": run_id,
        "status": status,
        "hashes_checked": hashes_checked,
        "paths_checked": paths_checked,
        "missing_paths": missing_paths,
        "hash_mismatches": hash_mismatches,
    }
