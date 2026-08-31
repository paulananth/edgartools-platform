"""_silver_reader() hard cutover to EDGARTOOLS_SILVER (DuckDB Retirement
Cutover Ticket 05). The MDM_SILVER_READ_TARGET toggle (silver-snowflake-
migration map, Ticket 12) that used to let this call site fall back to
DuckDB is retired -- every value, including unset/absent, must now reach
SnowflakeSilverReader, ignoring MDM_SILVER_DUCKDB/WAREHOUSE_STORAGE_ROOT
entirely.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from edgar_warehouse.mdm import cli as mdm_cli
from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader


@pytest.mark.parametrize(
    "read_target_value", [None, "duckdb", "DuckDB", " duckdb ", "snowflake", "garbage"]
)
def test_silver_reader_always_reaches_snowflake(monkeypatch, read_target_value):
    if read_target_value is None:
        monkeypatch.delenv("MDM_SILVER_READ_TARGET", raising=False)
    else:
        monkeypatch.setenv("MDM_SILVER_READ_TARGET", read_target_value)
    monkeypatch.delenv("MDM_SILVER_DUCKDB", raising=False)
    monkeypatch.delenv("WAREHOUSE_STORAGE_ROOT", raising=False)

    with (
        patch.object(mdm_cli, "_duckdb_silver_reader") as duckdb_reader,
        patch.object(SnowflakeSilverReader, "connect", return_value="snowflake-reader-sentinel") as connect,
    ):
        result = mdm_cli._silver_reader()

    connect.assert_called_once_with()
    duckdb_reader.assert_not_called()
    assert result == "snowflake-reader-sentinel"


def test_silver_reader_ignores_duckdb_env_vars_entirely(monkeypatch):
    """Even a fully-configured legacy DuckDB environment (MDM_SILVER_DUCKDB
    and WAREHOUSE_STORAGE_ROOT both set) must not influence _silver_reader()
    post-cutover -- only _duckdb_silver_reader() (used by the parity
    commands) still reads those."""
    monkeypatch.delenv("MDM_SILVER_READ_TARGET", raising=False)
    monkeypatch.setenv("MDM_SILVER_DUCKDB", "/tmp/legacy-shard-dir")
    monkeypatch.setenv("WAREHOUSE_STORAGE_ROOT", "s3://bucket/warehouse")

    with (
        patch.object(mdm_cli, "_duckdb_silver_reader") as duckdb_reader,
        patch.object(SnowflakeSilverReader, "connect", return_value="snowflake-reader-sentinel") as connect,
    ):
        result = mdm_cli._silver_reader()

    connect.assert_called_once_with()
    duckdb_reader.assert_not_called()
    assert result == "snowflake-reader-sentinel"
