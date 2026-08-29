"""Ticket 35: retirement records drop a key from the silver collapse.

Mirrors the shared dbt macro's SQL against DuckDB so the anti-join is
proven without a live Snowflake dynamic table. QUALIFY is DuckDB-native.
"""

from __future__ import annotations

from pathlib import Path

import duckdb


_COLLAPSE_SQL = """
select
    cik,
    ticker,
    exchange,
    source_name
from sec_company_ticker
qualify row_number() over (
    partition by cik, ticker, source_name
    order by parse_sequence desc
) = 1
  and not exists (
    select 1
    from (
        select
            business_key,
            parse_sequence,
            row_number() over (
                partition by business_key
                order by parse_sequence desc
            ) as rn
        from silver_landing_retirement
        where upper(target_table) = upper('sec_company_ticker')
    ) retired
    where retired.rn = 1
      and retired.business_key = concat_ws('|', cik, ticker, source_name)
      and retired.parse_sequence > sec_company_ticker.parse_sequence
  )
"""


def test_retired_ticker_drops_from_collapse_without_touching_unrelated_keys() -> None:
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        create table sec_company_ticker (
            cik bigint,
            ticker varchar,
            exchange varchar,
            source_name varchar,
            parse_sequence bigint
        )
        """
    )
    conn.execute(
        """
        create table silver_landing_retirement (
            source_family varchar,
            target_table varchar,
            business_key varchar,
            cause_reference varchar,
            retired_at timestamp,
            parse_sequence bigint
        )
        """
    )
    conn.execute(
        """
        insert into sec_company_ticker values
            (320193, 'AAPL', 'NASDAQ', 'company_tickers', 1),
            (789019, 'MSFT', 'NASDAQ', 'company_tickers', 2)
        """
    )
    conn.execute(
        """
        insert into silver_landing_retirement values
            ('reference_catalog', 'sec_company_ticker',
             '320193|AAPL|company_tickers', 'cause-1', now(), 3)
        """
    )

    rows = {
        (row[0], row[1], row[3])
        for row in conn.execute(_COLLAPSE_SQL).fetchall()
    }
    assert (320193, "AAPL", "company_tickers") not in rows
    assert (789019, "MSFT", "company_tickers") in rows


def test_later_landing_row_reinstates_a_retired_key() -> None:
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        create table sec_company_ticker (
            cik bigint,
            ticker varchar,
            exchange varchar,
            source_name varchar,
            parse_sequence bigint
        )
        """
    )
    conn.execute(
        """
        create table silver_landing_retirement (
            source_family varchar,
            target_table varchar,
            business_key varchar,
            cause_reference varchar,
            retired_at timestamp,
            parse_sequence bigint
        )
        """
    )
    conn.execute(
        """
        insert into sec_company_ticker values
            (320193, 'AAPL', 'NASDAQ', 'company_tickers', 1),
            (320193, 'AAPL', 'NASDAQ', 'company_tickers', 4)
        """
    )
    conn.execute(
        """
        insert into silver_landing_retirement values
            ('reference_catalog', 'sec_company_ticker',
             '320193|AAPL|company_tickers', 'cause-1', now(), 3)
        """
    )

    rows = conn.execute(_COLLAPSE_SQL).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 320193
    assert rows[0][1] == "AAPL"


def test_silver_model_config_keeps_six_hour_target_lag() -> None:
    """Ticket 35: the completion barrier layers on top of this lag, not over it."""

    text = Path(
        "infra/snowflake/dbt/edgartools_gold/macros/silver_model_config.sql"
    ).read_text()
    assert "target_lag='6 hours'" in text
