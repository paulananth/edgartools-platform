from __future__ import annotations

import json
import os
from decimal import Decimal

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


def test_snowflake_connector_writer_multi_row_upsert_keeps_parse_json_out_of_values():
    """PARSE_JSON must live in the SELECT list, not the VALUES clause.

    snowflake-connector-python's executemany rewrites INSERT ... VALUES (...)
    into a multi-row VALUES list, and Snowflake rejects any non-constant
    expression there ("002014 (22000): Invalid expression [PARSE_JSON(...)]
    in VALUES clause"). Hit live by bronze_seed_silver_gold's MdmExport at
    real batch sizes (single-row batches masked it in dev). The supported
    pattern is INSERT ... SELECT PARSE_JSON(columnN) ... FROM VALUES (...).
    """
    connection = FakeConnection()
    writer = SnowflakeConnectorWriter(connection, database="EDGARTOOLS_PROD", schema="MDM")

    count = writer.upsert(
        "MDM_COMPANY",
        [
            {"entity_id": "company-1", "canonical_name": "Issuer Corp"},
            {"entity_id": "company-2", "canonical_name": "Bank 2020 Bnk25"},
        ],
    )

    assert count == 2
    cursor = connection.fake_cursor
    assert len(cursor.batches) == 1
    insert_sql, values = cursor.batches[0]
    values_clause = insert_sql[insert_sql.index("VALUES") :]
    assert "PARSE_JSON" not in values_clause
    assert "SELECT PARSE_JSON(column1), PARSE_JSON(column2)" in insert_sql
    assert "FROM VALUES (%s, %s)" in insert_sql
    assert len(values) == 2
    assert all(len(row) == 2 for row in values)


def test_snowflake_connector_writer_serializes_decimal_values_as_json_numbers():
    connection = FakeConnection()
    writer = SnowflakeConnectorWriter(connection, database="EDGARTOOLS_PROD", schema="MDM")

    count = writer.upsert(
        "MDM_FUND",
        [{"entity_id": "fund-1", "aum_amount": Decimal("1234.50")}],
    )

    assert count == 1
    _, values = connection.fake_cursor.batches[0]
    encoded_values = values[0]
    assert json.loads(encoded_values[0]) == 1234.5
    assert json.loads(encoded_values[1]) == "fund-1"


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


def test_snowflake_connection_settings_read_json_secret(monkeypatch):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "MDM_SNOWFLAKE_SECRET_JSON",
        json.dumps(
            {
                "account": "acct",
                "user": "user",
                "password": "secret",
                "database": "EDGARTOOLS_DEV",
                "schema": "MDM",
                "warehouse": "LOAD_WH",
                "role": "MDM_LOADER",
            }
        ),
    )

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


def test_snowflake_connection_settings_env_overrides_json_secret(monkeypatch):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "MDM_SNOWFLAKE_SECRET_JSON",
        json.dumps(
            {
                "account": "secret-acct",
                "user": "user",
                "password": "secret",
                "database": "EDGARTOOLS_DEV",
                "warehouse": "LOAD_WH",
            }
        ),
    )
    monkeypatch.setenv("MDM_SNOWFLAKE_ACCOUNT", "env-acct")

    settings = SnowflakeConnectionSettings.from_env()

    assert settings.account == "env-acct"


def test_snowflake_connection_settings_missing_values_preserve_error_names(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith("MDM_SNOWFLAKE_") or name.startswith("DBT_SNOWFLAKE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

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
