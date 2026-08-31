from __future__ import annotations

from typing import Any

import duckdb
import pytest


class DuckDBFakeReader:
    """Minimal Reader-protocol adapter over a raw in-memory DuckDB
    connection, used to stand in for both "DuckDB canonical" and
    "Snowflake EDGARTOOLS_SILVER" in tests -- the collector only ever talks
    through ``.fetch(sql, params) -> list[dict]``, so a second DuckDB
    connection is a faithful enough double for either side.
    """

    def __init__(self) -> None:
        self._conn = duckdb.connect(":memory:")

    def execute(self, sql: str, params: list[Any] | None = None) -> None:
        self._conn.execute(sql, params or [])

    def fetch(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        cursor = self._conn.execute(sql, params or [])
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        self._conn.close()


@pytest.fixture
def duckdb_reader() -> DuckDBFakeReader:
    reader = DuckDBFakeReader()
    yield reader
    reader.close()


@pytest.fixture
def snowflake_reader() -> DuckDBFakeReader:
    reader = DuckDBFakeReader()
    yield reader
    reader.close()
