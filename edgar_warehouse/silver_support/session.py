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


def open_silver_shard(path: str) -> "SilverDatabase":
    """Open a SilverDatabase at the given shard file path.

    Unlike ``open_silver_database`` (which appends the canonical
    ``silver/sec/silver.duckdb`` suffix to a storage root), this function
    accepts an already-resolved local filesystem path and opens the
    SilverDatabase there directly.  Used by the shard-aware bootstrap
    chunk path in ``warehouse_orchestrator._execute_warehouse_bronze_capture``.

    Parameters
    ----------
    path:
        Absolute local filesystem path to a shard DuckDB file
        (e.g. ``/tmp/silver/sec/shards/shard-1.duckdb``).

    Returns
    -------
    SilverDatabase
        An open SilverDatabase instance at the provided path.
    """
    from edgar_warehouse.silver_store import SilverDatabase

    return SilverDatabase(path)


def reset_submission_state(db: Any, cik: int) -> None:
    db._conn.execute("DELETE FROM sec_company_former_name WHERE cik = ?", [cik])
    db._conn.execute("DELETE FROM sec_company_submission_file WHERE cik = ?", [cik])
