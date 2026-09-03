"""Fake Snowflake connector test double.

Shared by tests covering source_dimensional_export.py's Snowflake-silver-reading builders
(dbt-gold-silver-rewiring map, Ticket 06) -- those builders open a real
snowflake-connector-python connection via
edgar_warehouse.mdm.export.silver_connection_settings().connect(), so tests
patch that function to return a FakeSnowflakeConnectionSettings instead of
requiring a live Snowflake session.
"""

from __future__ import annotations


class FakeSnowflakeCursor:
    def __init__(self, table_data: dict[str, tuple[list[str], list[tuple]]]) -> None:
        self._table_data = table_data
        self.description: list[tuple[str]] = []
        self._rows: list[tuple] = []
        self.last_query: str | None = None
        self.last_params: list | tuple | None = None
        self.closed = False

    def execute(self, query: str, params: list | tuple | None = None) -> None:
        self.last_query = query
        self.last_params = params
        query_upper = query.upper()
        for table_name, (columns, rows) in self._table_data.items():
            if table_name.upper() in query_upper:
                self.description = [(column,) for column in columns]
                self._rows = rows
                return
        raise AssertionError(f"FakeSnowflakeCursor has no fixture for query: {query}")

    def fetchall(self) -> list[tuple]:
        return self._rows

    def close(self) -> None:
        self.closed = True


class FakeSnowflakeConnection:
    def __init__(self, table_data: dict[str, tuple[list[str], list[tuple]]]) -> None:
        self._table_data = table_data
        self.closed = False
        self.cursors: list[FakeSnowflakeCursor] = []

    def cursor(self) -> FakeSnowflakeCursor:
        created = FakeSnowflakeCursor(self._table_data)
        self.cursors.append(created)
        return created

    def close(self) -> None:
        self.closed = True


class FakeSnowflakeConnectionSettings:
    """Stand-in for edgar_warehouse.mdm.export.SnowflakeConnectionSettings --
    .connect() returns a FakeSnowflakeConnection instead of opening a real
    Snowflake session."""

    def __init__(self, table_data: dict[str, tuple[list[str], list[tuple]]]) -> None:
        self._table_data = table_data

    def connect(self) -> FakeSnowflakeConnection:
        return FakeSnowflakeConnection(self._table_data)


class RecordingConnectSettings:
    """Stand-in settings object that records the module-global paramstyle
    at the moment .connect() is called, so tests can assert a qmark-scoping
    window without touching a real Snowflake connection or the module
    global outside the test's control. Shared by every test proving a
    connect() call site is correctly wrapped in
    connect_with_qmark_paramstyle()."""

    def __init__(self, connection: "FakeSnowflakeConnection") -> None:
        self._connection = connection
        self.paramstyle_during_connect: str | None = None

    def connect(self) -> "FakeSnowflakeConnection":
        import snowflake.connector as sc

        self.paramstyle_during_connect = sc.paramstyle
        return self._connection


class RaisingConnectSettings:
    """Settings object whose .connect() always raises -- proves the
    paramstyle restore in connect_with_qmark_paramstyle() runs even when
    the wrapped connect() call fails."""

    def connect(self):
        raise RuntimeError("boom")


# The 5 orphan evidence tables source_dimensional_export.py's Snowflake-silver-reading
# builders query (dbt-gold-silver-rewiring map, Ticket 06). Callers that
# only need those builders to complete without error -- not to exercise
# specific row content -- can pass this straight to
# FakeSnowflakeConnectionSettings(...); an empty row list means the columns
# name list is never consulted (see FakeSnowflakeCursor.execute).
EMPTY_ORPHAN_EVIDENCE_TABLE_DATA: dict[str, tuple[list[str], list[tuple]]] = {
    "SEC_SUBSIDIARY_EVIDENCE": ([], []),
    "SEC_AUDITOR_REPORT_EVIDENCE": ([], []),
    "SEC_EMPLOYMENT_EVENT": ([], []),
    "SEC_ADV_FIRM_ROSTER": ([], []),
    "SEC_ADV_PRIVATE_FUND": ([], []),
}
