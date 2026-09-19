"""_silver_reader() hard cutover to EDGARTOOLS_SILVER (DuckDB Retirement
Cutover Ticket 05). The MDM_SILVER_READ_TARGET toggle (silver-snowflake-
migration map, Ticket 12) that used to let this call site fall back to
DuckDB is retired -- every value, including unset/absent, must now reach
SnowflakeSilverReader, ignoring MDM_SILVER_DUCKDB/WAREHOUSE_STORAGE_ROOT
entirely.

Local offline work is a separate, explicit opt-in: SILVER_DATABASE_URL
selects PostgresSilverReader. Production leaves that variable unset.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from edgar_warehouse.mdm import cli as mdm_cli
from edgar_warehouse.silver_support.postgres_reader import PostgresSilverReader
from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader


def _clear_legacy_silver_env(monkeypatch) -> None:
    monkeypatch.delenv("MDM_SILVER_READ_TARGET", raising=False)
    monkeypatch.delenv("MDM_SILVER_DUCKDB", raising=False)
    monkeypatch.delenv("WAREHOUSE_STORAGE_ROOT", raising=False)
    monkeypatch.delenv("SILVER_DATABASE_URL", raising=False)


@pytest.mark.parametrize(
    "read_target_value", [None, "duckdb", "DuckDB", " duckdb ", "snowflake", "garbage"]
)
def test_silver_reader_always_reaches_snowflake(monkeypatch, read_target_value):
    _clear_legacy_silver_env(monkeypatch)
    if read_target_value is not None:
        monkeypatch.setenv("MDM_SILVER_READ_TARGET", read_target_value)

    with patch.object(SnowflakeSilverReader, "connect", return_value="snowflake-reader-sentinel") as connect:
        result = mdm_cli._silver_reader()

    connect.assert_called_once_with()
    assert result == "snowflake-reader-sentinel"


def test_silver_reader_ignores_duckdb_env_vars_entirely(monkeypatch):
    """Even a fully-configured legacy DuckDB environment (MDM_SILVER_DUCKDB
    and WAREHOUSE_STORAGE_ROOT both set) must not influence _silver_reader()
    post-cutover. The DuckDB reader that still read those variables was
    deleted with the parity commands (silver-merge-engine-migration Ticket 08)."""
    _clear_legacy_silver_env(monkeypatch)
    monkeypatch.setenv("MDM_SILVER_DUCKDB", "/tmp/legacy-shard-dir")
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", "s3://bucket/warehouse")

    with patch.object(SnowflakeSilverReader, "connect", return_value="snowflake-reader-sentinel") as connect:
        result = mdm_cli._silver_reader()

    connect.assert_called_once_with()
    assert result == "snowflake-reader-sentinel"


def test_silver_reader_uses_postgres_when_silver_database_url_set(monkeypatch):
    _clear_legacy_silver_env(monkeypatch)
    monkeypatch.setenv(
        "SILVER_DATABASE_URL", "postgresql://postgres:test@127.0.0.1:5432/silver"
    )

    with patch.object(PostgresSilverReader, "connect", return_value="postgres-reader-sentinel") as connect:
        result = mdm_cli._silver_reader()

    connect.assert_called_once_with()
    assert result == "postgres-reader-sentinel"
