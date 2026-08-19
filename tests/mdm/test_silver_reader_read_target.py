"""MDM_SILVER_READ_TARGET gating on _silver_reader() (silver-snowflake-migration
map, Ticket 12). Default/unset/"duckdb" must be a complete no-op against the
pre-existing DuckDB shard-hydration path; "snowflake" must short-circuit to
SnowflakeSilverReader without touching MDM_SILVER_DUCKDB/WAREHOUSE_STORAGE_ROOT
at all.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from edgar_warehouse.mdm import cli as mdm_cli
from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader


@pytest.mark.parametrize("read_target_value", [None, "duckdb", "DuckDB", " duckdb "])
def test_silver_reader_defaults_to_duckdb_path(monkeypatch, read_target_value):
    if read_target_value is None:
        monkeypatch.delenv("MDM_SILVER_READ_TARGET", raising=False)
    else:
        monkeypatch.setenv("MDM_SILVER_READ_TARGET", read_target_value)
    monkeypatch.delenv("MDM_SILVER_DUCKDB", raising=False)
    monkeypatch.delenv("WAREHOUSE_STORAGE_ROOT", raising=False)

    with patch.object(mdm_cli, "_duckdb_silver_reader", return_value="duckdb-reader-sentinel") as duckdb_reader:
        result = mdm_cli._silver_reader()

    duckdb_reader.assert_called_once()
    assert result == "duckdb-reader-sentinel"


@pytest.mark.parametrize("read_target_value", ["snowflake", "Snowflake", " SNOWFLAKE "])
def test_silver_reader_short_circuits_to_snowflake(monkeypatch, read_target_value):
    monkeypatch.setenv("MDM_SILVER_READ_TARGET", read_target_value)

    with (
        patch.object(mdm_cli, "_duckdb_silver_reader") as duckdb_reader,
        patch.object(SnowflakeSilverReader, "connect", return_value="snowflake-reader-sentinel") as connect,
    ):
        result = mdm_cli._silver_reader()

    connect.assert_called_once_with()
    duckdb_reader.assert_not_called()
    assert result == "snowflake-reader-sentinel"
