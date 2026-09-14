"""Silver database session boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from edgar_warehouse.infrastructure.object_storage import StorageLocation

if TYPE_CHECKING:
    from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
    from edgar_warehouse.silver_store import SilverDatabase

def open_silver_database(
    silver_root: StorageLocation, *, landing_export: "LandingExportBuffer | None" = None
) -> "SilverDatabase":
    from edgar_warehouse.silver_store import SilverDatabase

    db_path = silver_root.join("silver", "sec", "silver.duckdb")
    return SilverDatabase(db_path, landing_export=landing_export)

