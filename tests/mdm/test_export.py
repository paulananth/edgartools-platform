from __future__ import annotations

import os

from edgar_warehouse.mdm.export import SnowflakeConnectorWriter
from edgar_warehouse.mdm.export import SnowflakeConnectionSettings


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


def test_snowflake_connection_settings_read_mdm_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MDM_SNOWFLAKE_ACCOUNT", "acct")
    monkeypatch.setenv("MDM_SNOWFLAKE_USER", "user")
    monkeypatch.setenv("MDM_SNOWFLAKE_PASSWORD", "secret")
    monkeypatch.setenv("MDM_SNOWFLAKE_DATABASE", "EDGARTOOLS_DEV")
    monkeypatch.setenv("MDM_SNOWFLAKE_SCHEMA", "MDM")
    monkeypatch.setenv("MDM_SNOWFLAKE_WAREHOUSE", "LOAD_WH")
    monkeypatch.setenv("MDM_SNOWFLAKE_ROLE", "MDM_LOADER")

    settings = SnowflakeConnectionSettings.from_env()

    assert settings.connection_kwargs() == {
        "account": "acct",
        "user": "user",
        "password": "secret",
        "database": "EDGARTOOLS_DEV",
        "schema": "MDM",
        "warehouse": "LOAD_WH",
        "role": "MDM_LOADER",
    }


def test_snowflake_connection_settings_preserve_dbt_fallbacks(monkeypatch):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DBT_SNOWFLAKE_ACCOUNT", "acct")
    monkeypatch.setenv("DBT_SNOWFLAKE_USER", "user")
    monkeypatch.setenv("DBT_SNOWFLAKE_PASSWORD", "secret")
    monkeypatch.setenv("DBT_SNOWFLAKE_DATABASE", "EDGARTOOLS_DEV")
    monkeypatch.setenv("DBT_SNOWFLAKE_WAREHOUSE", "LOAD_WH")

    settings = SnowflakeConnectionSettings.from_env()

    assert settings.database == "EDGARTOOLS_DEV"
    assert settings.schema == "EDGARTOOLS_GOLD"
    assert settings.connection_kwargs()["warehouse"] == "LOAD_WH"


def test_snowflake_connection_settings_missing_values_preserve_error_names(monkeypatch):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)

    try:
        SnowflakeConnectionSettings.from_env()
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected missing settings to raise")

    assert "MDM_SNOWFLAKE_ACCOUNT or DBT_SNOWFLAKE_ACCOUNT" in message
    assert "MDM_SNOWFLAKE_USER or DBT_SNOWFLAKE_USER" in message
    assert "MDM_SNOWFLAKE_PASSWORD or DBT_SNOWFLAKE_PASSWORD" in message
    assert "MDM_SNOWFLAKE_DATABASE or DBT_SNOWFLAKE_DATABASE" in message
    assert "MDM_SNOWFLAKE_WAREHOUSE or DBT_SNOWFLAKE_WAREHOUSE" in message
    assert "NEO4J_" not in message
