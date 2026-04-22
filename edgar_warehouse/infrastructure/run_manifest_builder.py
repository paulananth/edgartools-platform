"""Manifest pathing and payload helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory, default_path_resolver

SNOWFLAKE_EXPORT_TABLES = {
    "COMPANY": "company",
    "FILING_ACTIVITY": "filing_activity",
    "OWNERSHIP_ACTIVITY": "ownership_activity",
    "OWNERSHIP_HOLDINGS": "ownership_holdings",
    "ADVISER_OFFICES": "adviser_offices",
    "ADVISER_DISCLOSURES": "adviser_disclosures",
    "PRIVATE_FUNDS": "private_funds",
    "FILING_DETAIL": "filing_detail",
}


def planned_writes(command_name: str, command_path: str, run_id: str, scope: dict[str, Any]) -> dict[str, str]:
    return default_path_resolver().planned_manifest_paths(
        command_name=command_name,
        command_path=command_path,
        run_id=run_id,
        scope={key: str(value) for key, value in scope.items()},
    )


def layer_manifest(
    command_name: str,
    run_id: str,
    layer: str,
    relative_path: str,
    arguments: dict[str, Any],
    scope: dict[str, Any],
    now: datetime,
    runtime_mode: str,
) -> dict[str, Any]:
    return {
        "arguments": arguments,
        "command": command_name,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "layer": layer,
        "relative_path": relative_path,
        "run_id": run_id,
        "runtime_mode": runtime_mode,
        "scope": scope,
    }


def snowflake_export_manifest(
    table_name: str,
    command_name: str,
    run_id: str,
    business_date: str,
    arguments: dict[str, Any],
    now: datetime,
    runtime_mode: str,
    row_count: int = 0,
    file_count: int = 0,
) -> dict[str, Any]:
    return {
        "business_date": business_date,
        "command": command_name,
        "compression": "snappy",
        "exported_at": now.isoformat().replace("+00:00", "Z"),
        "file_count": file_count,
        "format": "parquet",
        "row_count": row_count,
        "run_id": run_id,
        "runtime_mode": runtime_mode,
        "schema_version": 1,
        "table_name": table_name,
        "workflow_arguments": arguments,
        "workflow_name": command_name.replace("-", "_"),
    }


def snowflake_export_run_manifest_relative_path(workflow_name: str, business_date: str, run_id: str) -> str:
    return default_path_resolver().snowflake_export_run_manifest_path(
        workflow_name=workflow_name,
        business_date=business_date,
        run_id=run_id,
    )


def snowflake_export_run_manifest(
    *,
    environment_name: str,
    command_name: str,
    run_id: str,
    business_date: str,
    now: datetime,
    export_counts: dict[str, int],
) -> dict[str, Any]:
    tables = [
        snowflake_export_run_manifest_table(
            table_name=table_name,
            table_path=table_path,
            run_id=run_id,
            business_date=business_date,
            row_count=export_counts.get(table_path, 0),
        )
        for table_name, table_path in SNOWFLAKE_EXPORT_TABLES.items()
    ]
    return {
        "business_date": business_date,
        "completed_at": now.isoformat().replace("+00:00", "Z"),
        "environment": environment_name,
        "run_id": run_id,
        "schema_version": 1,
        "tables": tables,
        "workflow_name": command_name.replace("-", "_"),
    }


def snowflake_export_run_manifest_table(
    *,
    table_name: str,
    table_path: str,
    run_id: str,
    business_date: str,
    row_count: int,
) -> dict[str, Any]:
    relative_path = default_capture_spec_factory().snowflake_export_table(
        table_path=table_path,
        business_date=business_date,
        run_id=run_id,
    ).relative_path
    return {
        "file_count": 1,
        "relative_path": relative_path,
        "row_count": row_count,
        "table_name": table_name,
    }


def warehouse_success_message(has_snowflake_exports: bool) -> str:
    if has_snowflake_exports:
        return (
            "Warehouse infrastructure validation completed successfully. "
            "Run manifests were written to the configured bronze, warehouse, and Snowflake export roots."
        )
    return (
        "Warehouse infrastructure validation completed successfully. "
        "Run manifests were written to the configured bronze and warehouse roots."
    )
