from __future__ import annotations

from edgar_warehouse.mdm.export import SnowflakeConnectorWriter


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.batches: list[tuple[str, list[tuple[str, ...]]]] = []
        self.closed = False

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def executemany(self, sql: str, values: list[tuple[str, ...]]) -> None:
        self.batches.append((sql, values))

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self) -> None:
        self.fake_cursor = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.fake_cursor


def test_snowflake_connector_writer_upserts_rows_with_merge_sql():
    connection = FakeConnection()
    writer = SnowflakeConnectorWriter(connection, database="EDGARTOOLS_DEV", schema="MDM")

    count = writer.upsert(
        "MDM_COMPANY",
        [{"entity_id": "company-1", "canonical_name": "Issuer Corp"}],
    )

    cursor = connection.fake_cursor
    assert count == 1
    assert cursor.closed is True
    assert any("CREATE TEMPORARY TABLE" in sql for sql in cursor.executed)
    assert cursor.batches
    merge_sql = cursor.executed[-1]
    assert 'MERGE INTO "EDGARTOOLS_DEV"."MDM"."MDM_COMPANY"' in merge_sql
    assert 'ON target."ENTITY_ID" = source."ENTITY_ID"' in merge_sql
