"""Landing-zone row buffer for immutable Snowflake export artifacts.

Rows are accumulated explicitly and flushed to Parquet plus a run manifest.
The historical SilverLandingStore parser/writer API is retired from runtime;
its frozen test oracle still uses this buffer to verify prior landed evidence.
This buffer does not parse SEC documents or classify filers.
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
