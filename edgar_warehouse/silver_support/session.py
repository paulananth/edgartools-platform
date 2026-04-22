"""Silver database session boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from edgar_warehouse.infrastructure.object_storage import StorageLocation

if TYPE_CHECKING:
    from edgar_warehouse.silver_store import SilverDatabase

def open_silver_database(silver_root: StorageLocation) -> "SilverDatabase":
    from edgar_warehouse.silver_store import SilverDatabase

    db_path = silver_root.join("silver", "sec", "silver.duckdb")
    return SilverDatabase(db_path)


def reset_submission_state(db: Any, cik: int) -> None:
    db._conn.execute("DELETE FROM sec_company_former_name WHERE cik = ?", [cik])
    db._conn.execute("DELETE FROM sec_company_submission_file WHERE cik = ?", [cik])
