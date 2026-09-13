"""Test helpers for tables whose merge_* writers are landing-only.

silver-merge-engine-migration Tickets 02-06 made those writers skip local
DuckDB. A test that still needs rows physically present in a local
SilverDatabase -- schema-migration tests, ShardedSilverReader allowlist
tests -- inserts them directly; those tests guard the migration or the
reader, not a writer. `CountingConnection` lets a volume test assert a
landing-only writer does no per-row DuckDB I/O.
"""

from __future__ import annotations

from typing import Any


def insert_silver_rows(db: Any, table: str, rows: list[dict[str, Any]]) -> int:
    for row in rows:
        columns = ", ".join(row)
        placeholders = ", ".join("?" * len(row))
        db._conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(row.values())
        )
    return len(rows)


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
