from __future__ import annotations

import datetime
import unittest

import duckdb

from edgar_warehouse.serving.gold_models import (
    _SEC_FINANCIAL_DERIVED_SCHEMA,
    _build_sec_financial_derived,
)


class BuildSecFinancialDerivedTests(unittest.TestCase):
    def _connection(self) -> duckdb.DuckDBPyConnection:
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE sec_financial_derived (
                cik                 BIGINT NOT NULL,
                accession_number    TEXT NOT NULL,
                fiscal_year         INTEGER NOT NULL,
                fiscal_period       TEXT NOT NULL,
                period_end          DATE NOT NULL,
                form_type           TEXT NOT NULL,
                revenue             DOUBLE,
                gross_profit        DOUBLE,
                ebitda              DOUBLE,
                ebit                DOUBLE,
                net_income          DOUBLE,
                eps_diluted         DOUBLE,
                total_assets        DOUBLE,
                total_liabilities   DOUBLE,
                total_equity        DOUBLE,
                cash_and_equivalents DOUBLE,
                total_debt          DOUBLE,
                operating_cash_flow DOUBLE,
                capex               DOUBLE,
                free_cash_flow      DOUBLE,
                gross_margin        DOUBLE,
                ebitda_margin       DOUBLE,
                net_margin          DOUBLE,
                roic                DOUBLE,
                roe                 DOUBLE,
                roa                 DOUBLE,
                parser_version      TEXT,
                ingested_at         TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        return conn

    def test_current_and_comparative_rows_survive_as_two_rows_with_period_end(self) -> None:
        conn = self._connection()
        conn.execute(
            """
            INSERT INTO sec_financial_derived
                (cik, accession_number, fiscal_year, fiscal_period, period_end,
                 form_type, revenue, net_income, parser_version, ingested_at)
            VALUES
                (320193, '0001193125-24-100000', 2024, 'Q2', '2024-06-30',
                 '10-Q', 85777000000, 21448000000, 'v1', '2024-01-01T00:00:00Z'),
                (320193, '0001193125-24-100000', 2023, 'Q2', '2023-06-30',
                 '10-Q', 81797000000, 19881000000, 'v1', '2024-01-01T00:00:00Z')
            """
        )

        table = _build_sec_financial_derived(conn)

        self.assertEqual(table.schema, _SEC_FINANCIAL_DERIVED_SCHEMA)
        self.assertEqual(table.num_rows, 2)

        period_ends = sorted(table.column("period_end").to_pylist())
        self.assertEqual(
            period_ends,
            [datetime.date(2023, 6, 30), datetime.date(2024, 6, 30)],
        )

        revenue_by_period_end = dict(
            zip(table.column("period_end").to_pylist(), table.column("revenue").to_pylist())
        )
        self.assertEqual(revenue_by_period_end[datetime.date(2024, 6, 30)], 85777000000)
        self.assertEqual(revenue_by_period_end[datetime.date(2023, 6, 30)], 81797000000)

    def test_empty_table_uses_sentinel_schema(self) -> None:
        conn = self._connection()
        table = _build_sec_financial_derived(conn)
        self.assertEqual(table.schema, _SEC_FINANCIAL_DERIVED_SCHEMA)
        self.assertEqual(table.num_rows, 0)


if __name__ == "__main__":
    unittest.main()
