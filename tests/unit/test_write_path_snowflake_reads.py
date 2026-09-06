"""DuckDB Retirement Cutover Ticket 10: write-path read call sites repointed
at EDGARTOOLS_SILVER (via SnowflakeSilverReader) instead of local DuckDB,
since the write path no longer hydrates silver.duckdb from canonical storage.

- _company_identity_ciks_snowflake: replaces SilverDatabase.get_company_identity_ciks.
- _snowflake_distinct_values: replaces the fetch-adv-bulk/fetch-firm-roster
  already_ingested idempotency checks.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader


def _fake_reader(fetch_return):
    reader = MagicMock()
    reader.fetch.return_value = fetch_return
    return reader


def test_company_identity_ciks_snowflake_intersects_tracked_and_eligible():
    reader = _fake_reader([{"cik": 100}, {"cik": 300}])
    with patch.object(SnowflakeSilverReader, "connect", return_value=reader):
        result = warehouse_orchestrator._company_identity_ciks_snowflake({100, 200, 300})

    assert result == [100, 300]
    reader.close.assert_called_once()
    sql, params = reader.fetch.call_args[0]
    assert "sec_company" in sql and "sec_company_ticker" in sql
    half = len(params) // 2
    assert sorted(params[:half]) == sorted(params[half:]) == [100, 200, 300]


def test_company_identity_ciks_snowflake_short_circuits_on_empty_tracked_set():
    with patch.object(SnowflakeSilverReader, "connect") as connect:
        result = warehouse_orchestrator._company_identity_ciks_snowflake(set())

    assert result == []
    connect.assert_not_called()


def test_company_identity_ciks_snowflake_closes_reader_even_on_error():
    reader = MagicMock()
    reader.fetch.side_effect = RuntimeError("boom")
    with patch.object(SnowflakeSilverReader, "connect", return_value=reader):
        try:
            warehouse_orchestrator._company_identity_ciks_snowflake({100})
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError to propagate")
    reader.close.assert_called_once()


def test_snowflake_distinct_values_returns_string_set():
    reader = _fake_reader([{"source_dataset_period": "2026-06"}, {"source_dataset_period": "2026-07"}])
    with patch.object(SnowflakeSilverReader, "connect", return_value=reader):
        result = warehouse_orchestrator._snowflake_distinct_values(
            "sec_adv_private_fund", "source_dataset_period"
        )

    assert result == {"2026-06", "2026-07"}
    reader.close.assert_called_once()
    (sql,), _kwargs = reader.fetch.call_args
    assert sql == (
        "SELECT DISTINCT source_dataset_period FROM sec_adv_private_fund "
        "WHERE source_dataset_period IS NOT NULL"
    )


def test_snowflake_distinct_values_empty_result():
    reader = _fake_reader([])
    with patch.object(SnowflakeSilverReader, "connect", return_value=reader):
        result = warehouse_orchestrator._snowflake_distinct_values("sec_adv_firm_roster", "dataset_period")

    assert result == set()
