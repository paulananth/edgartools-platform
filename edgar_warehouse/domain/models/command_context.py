"""Runtime context models."""

from __future__ import annotations

from dataclasses import dataclass

from edgar_warehouse.infrastructure.object_storage import StorageLocation


@dataclass(frozen=True)
class WarehouseCommandContext:
    """Runtime context shared by warehouse commands."""

    bronze_root: StorageLocation
    storage_root: StorageLocation
    silver_root: StorageLocation
    snowflake_export_root: StorageLocation | None
    environment_name: str
    identity: str
    runtime_mode: str
