from edgar_warehouse.serving.gold_verify import (
    GOLD_LIVE_TABLES,
    GOLD_PILOT_TABLES,
    verify_gold_live,
)


class FakeCursor:
    def __init__(self, counts: dict[str, int], errors: set[str] | None = None) -> None:
        self._counts = counts
        self._errors = errors or set()
        self._pending: int | None = None
        self.executed: list[str] = []
        self.closed = False

    def execute(self, sql: str) -> None:
        self.executed.append(sql)
        table = sql.rsplit(".", 1)[-1].strip('"')
        if table in self._errors:
            raise RuntimeError(f"002043: Object '{table}' does not exist or not authorized")
        self._pending = self._counts.get(table, 0)

    def fetchone(self):
        return (self._pending,)

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def test_passes_when_every_table_has_rows():
    counts = {table: 5 for table in GOLD_LIVE_TABLES}
    connection = FakeConnection(FakeCursor(counts))

    result = verify_gold_live(connection, database="EDGARTOOLS_PROD")

    assert result.passed is True
    assert result.empty_tables == ()
    assert result.errors == {}
    assert set(result.row_counts) == set(GOLD_LIVE_TABLES)
    assert all(count == 5 for count in result.row_counts.values())
    assert connection._cursor.closed is True


def test_fails_when_one_table_is_empty():
    counts = {table: 5 for table in GOLD_LIVE_TABLES}
    counts["TICKER_REFERENCE"] = 0
    connection = FakeConnection(FakeCursor(counts))

    result = verify_gold_live(connection, database="EDGARTOOLS_PROD")

    assert result.passed is False
    assert result.empty_tables == ("TICKER_REFERENCE",)
    assert result.row_counts["TICKER_REFERENCE"] == 0


def test_query_error_counts_as_empty_and_is_recorded():
    counts = {table: 5 for table in GOLD_LIVE_TABLES}
    connection = FakeConnection(FakeCursor(counts, errors={"GUIDANCE_FACTS"}))

    result = verify_gold_live(connection, database="EDGARTOOLS_PROD")

    assert result.passed is False
    assert "GUIDANCE_FACTS" in result.empty_tables
    assert result.row_counts["GUIDANCE_FACTS"] == 0
    assert "does not exist" in result.errors["GUIDANCE_FACTS"]
    # A query error on one table does not stop the rest from being checked.
    other_tables = [t for t in GOLD_LIVE_TABLES if t != "GUIDANCE_FACTS"]
    assert all(result.row_counts[t] == 5 for t in other_tables)


def test_queries_use_the_given_database_and_schema():
    counts = {table: 1 for table in GOLD_LIVE_TABLES}
    cursor = FakeCursor(counts)
    connection = FakeConnection(cursor)

    verify_gold_live(connection, database="EDGARTOOLS_PROD", schema="EDGARTOOLS_GOLD")

    assert any(
        'SELECT COUNT(*) FROM "EDGARTOOLS_PROD"."EDGARTOOLS_GOLD"."COMPANY"' in sql
        for sql in cursor.executed
    )


def test_pilot_tables_are_excluded_and_never_checked():
    # CONSENSUS_ESTIMATES/TRANSCRIPT_EVENTS are intentionally pilot-scoped
    # with no automated producer -- verify_gold_live must never require them
    # to be non-empty, even when they're absent from Snowflake entirely.
    assert set(GOLD_PILOT_TABLES) == {"CONSENSUS_ESTIMATES", "TRANSCRIPT_EVENTS"}
    assert set(GOLD_PILOT_TABLES).isdisjoint(GOLD_LIVE_TABLES)

    counts = {table: 5 for table in GOLD_LIVE_TABLES}
    connection = FakeConnection(FakeCursor(counts, errors=set(GOLD_PILOT_TABLES)))

    result = verify_gold_live(connection, database="EDGARTOOLS_PROD")

    assert result.passed is True
    assert set(result.row_counts) == set(GOLD_LIVE_TABLES)
    assert set(result.row_counts).isdisjoint(GOLD_PILOT_TABLES)


def test_payload_shape():
    counts = {table: 1 for table in GOLD_LIVE_TABLES}
    connection = FakeConnection(FakeCursor(counts))

    result = verify_gold_live(connection, database="EDGARTOOLS_PROD")
    payload = result.payload

    assert payload["passed"] is True
    assert payload["database"] == "EDGARTOOLS_PROD"
    assert payload["schema"] == "EDGARTOOLS_GOLD"
    assert payload["tables_checked"] == len(GOLD_LIVE_TABLES)
    assert payload["empty_tables"] == []
    assert payload["errors"] == {}
