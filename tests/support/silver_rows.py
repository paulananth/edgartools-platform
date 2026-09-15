"""Test helpers for tables whose merge_* and mark_* writers are landing-only.

silver-merge-engine-migration Tickets 02-06 and 12 made those writers skip
local DuckDB. A test that still needs rows physically present in a local
SilverDatabase -- schema-migration tests, MDM real-schema
tests -- inserts them directly; those tests guard the migration or the
reader, not a writer. `open_landing_db` opens a SilverDatabase with a
`LandingExportBuffer` attached, for tests that assert on the rows a
landing-only writer records. `CountingConnection` lets a volume test
assert such a writer does no per-row DuckDB I/O.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.silver_store import SilverDatabase


def insert_silver_rows(db: Any, table: str, rows: list[dict[str, Any]]) -> int:
    for row in rows:
        columns = ", ".join(row)
        placeholders = ", ".join("?" * len(row))
        db._conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(row.values())
        )
    return len(rows)


def open_landing_db(tmp_path: Path) -> SilverDatabase:
    """A SilverDatabase whose landing-only writers record into an attached
    LandingExportBuffer, readable back as `db.landing_export`."""
    return SilverDatabase(str(tmp_path / "silver.duckdb"), landing_export=LandingExportBuffer())


class CountingConnection:
    """Wraps a DuckDB connection to count execute() calls."""

    def __init__(self, wrapped: Any):
        self.wrapped = wrapped
        self.executes = 0

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.executes += 1
        return self.wrapped.execute(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.wrapped, name)
