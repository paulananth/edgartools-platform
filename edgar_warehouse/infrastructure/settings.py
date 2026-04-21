"""Typed settings boundary for warehouse runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

from edgar_warehouse.application.errors import WarehouseRuntimeError

RUNTIME_MODES = frozenset({"bronze_capture", "infrastructure_validation"})
SNOWFLAKE_EXPORT_COMMANDS = frozenset(
    {
        "bootstrap-full",
        "bootstrap-recent-10",
        "bootstrap-batch",
        "daily-incremental",
        "targeted-resync",
        "full-reconcile",
        "seed-universe",
    }
)


@dataclass(frozen=True)
class WarehouseSettings:
    """Validated environment settings."""

    identity: str
    runtime_mode: str
    environment_name: str
    bronze_root: str
    storage_root: str
    silver_root: str
    snowflake_export_root: str | None

    @classmethod
    def from_env(cls, command_name: str) -> "WarehouseSettings":
        identity = os.environ.get("EDGAR_IDENTITY", "").strip()
        if not identity:
            raise WarehouseRuntimeError("EDGAR_IDENTITY is required for warehouse commands")
        if "@" not in identity:
            raise WarehouseRuntimeError("EDGAR_IDENTITY must include an email address")

        runtime_mode = os.environ.get("WAREHOUSE_RUNTIME_MODE", "infrastructure_validation").strip() or "infrastructure_validation"
        if runtime_mode not in RUNTIME_MODES:
            raise WarehouseRuntimeError(
                "WAREHOUSE_RUNTIME_MODE must be one of: " + ", ".join(sorted(RUNTIME_MODES))
            )

        environment_name = os.environ.get("WAREHOUSE_ENVIRONMENT", "").strip() or "local"
        bronze_root = os.environ.get("WAREHOUSE_BRONZE_ROOT", "").strip()
        storage_root = os.environ.get("WAREHOUSE_STORAGE_ROOT", "").strip()
        if not bronze_root:
            raise WarehouseRuntimeError("WAREHOUSE_BRONZE_ROOT is required for warehouse commands")
        if not storage_root:
            raise WarehouseRuntimeError("WAREHOUSE_STORAGE_ROOT is required for warehouse commands")

        silver_root_override = os.environ.get("WAREHOUSE_SILVER_ROOT", "").strip()
        if silver_root_override:
            silver_root = silver_root_override
        elif "://" in storage_root:
            silver_root = "/tmp/edgar-warehouse-silver"
        else:
            silver_root = storage_root

        snowflake_export_root = None
        if command_name in SNOWFLAKE_EXPORT_COMMANDS:
            value = os.environ.get("SNOWFLAKE_EXPORT_ROOT", "").strip()
            if not value:
                raise WarehouseRuntimeError("SNOWFLAKE_EXPORT_ROOT is required for gold-affecting warehouse commands")
            snowflake_export_root = value
        return cls(
            identity=identity,
            runtime_mode=runtime_mode,
            environment_name=environment_name,
            bronze_root=bronze_root,
            storage_root=storage_root,
            silver_root=silver_root,
            snowflake_export_root=snowflake_export_root,
        )
