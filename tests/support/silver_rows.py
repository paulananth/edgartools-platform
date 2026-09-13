"""Raw DuckDB row inserts for tests whose tables no longer have a DuckDB writer.

silver-merge-engine-migration Tickets 02-04 made those tables' merge_*
methods landing-only, so a test that still needs rows physically present in
a local SilverDatabase -- schema-migration tests, ShardedSilverReader
allowlist tests -- inserts them directly. These tests guard the migration or
the reader, not a writer.
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
