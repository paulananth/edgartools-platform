"""Command-context factory for warehouse execution."""

from __future__ import annotations

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.infrastructure.warehouse_settings import WarehouseSettings


def build_warehouse_context(command_name: str) -> WarehouseCommandContext:
    settings = WarehouseSettings.from_env(command_name)
    bronze_root = StorageLocation(settings.bronze_root)
    storage_root = StorageLocation(settings.storage_root)
    silver_root = StorageLocation(settings.silver_root)
    if bronze_root.root == storage_root.root:
        raise WarehouseRuntimeError(
            "WAREHOUSE_BRONZE_ROOT and WAREHOUSE_STORAGE_ROOT must be different locations"
        )

    snowflake_export_root = None
    if settings.snowflake_export_root is not None:
        snowflake_export_root = StorageLocation(settings.snowflake_export_root)
        if snowflake_export_root.root in {bronze_root.root, storage_root.root}:
            raise WarehouseRuntimeError(
                "SNOWFLAKE_EXPORT_ROOT must be isolated from bronze and warehouse roots"
            )

    return WarehouseCommandContext(
        bronze_root=bronze_root,
        storage_root=storage_root,
        silver_root=silver_root,
        snowflake_export_root=snowflake_export_root,
        environment_name=settings.environment_name,
        identity=settings.identity,
        runtime_mode=settings.runtime_mode,
    )
