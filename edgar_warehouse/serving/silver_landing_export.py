"""Landing-zone export buffer for Snowflake-native silver.

silver-snowflake-migration map, Ticket 01: the landing zone is fed by
exactly the rows a command parses and hands to `SilverDatabase`'s
merge_*/upsert_* methods this run -- not a full re-read of the local
silver.duckdb (which would re-export rows that were already exported by an
earlier run, defeating "append-only" the moment two runs overlap in
content). `SilverDatabase` is the single chokepoint every one of those
methods lives on. Each writer records into this buffer through
`SilverDatabase._record_landing_passthrough`, which adds the write-time
columns the landing schema carries (silver-merge-engine-migration Tickets
02-06); the `track_landing_rows`/`track_landing_row` decorators that
recorded the caller's raw rows were deleted with Ticket 06e, once no writer
used them.

Opt-in: `SilverDatabase(db_path)` with no `landing_export` argument records
nothing.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


class LandingExportBuffer:
    """Accumulates the rows a single command run wrote to silver, per landing table.

    Keyed by lowercase landing table name (matching the table names in
    `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql`, lowercased).
    Flushed to Parquet + a run manifest at the end of a command by
    `edgar_warehouse.serving.silver_landing_writer.flush_landing_export`.
    """

    def __init__(self) -> None:
        self._rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def record(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        if rows:
            self._rows[table_name].extend(rows)

    def tables(self) -> dict[str, list[dict[str, Any]]]:
        """A snapshot dict of {table_name: rows}, table names with zero rows omitted."""
        return {name: rows for name, rows in self._rows.items() if rows}

    def row_count(self, table_name: str) -> int:
        return len(self._rows.get(table_name, ()))

    def total_row_count(self) -> int:
        return sum(len(rows) for rows in self._rows.values())
