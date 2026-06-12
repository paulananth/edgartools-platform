from __future__ import annotations

import datetime
import unittest

import duckdb

from edgar_warehouse.serving.gold_models import (
    _SEC_FINANCIAL_FACT_SCHEMA,
    _build_sec_financial_fact,
)


class BuildSecFinancialFactTests(unittest.TestCase):
    def _connection(self) -> duckdb.DuckDBPyConnection:
        conn = duckdb.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE sec_financial_fact (
                cik                 BIGINT NOT NULL,
                accession_number    TEXT NOT NULL,
                fiscal_year         INTEGER NOT NULL,
                fiscal_period       TEXT NOT NULL,
                period_end          DATE NOT NULL,
                period_start        DATE NOT NULL,
                form_type           TEXT NOT NULL,
                concept             TEXT NOT NULL,
                value               DOUBLE,
                unit                TEXT,
                decimals            INTEGER,
                segment             TEXT NOT NULL DEFAULT 'consolidated',
                parser_version      TEXT,
                ingested_at         TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        return conn

    def test_qtd_ytd_pair_survives_as_two_rows_with_period_start(self) -> None:
        conn = self._connection()
        conn.execute(
            """
            INSERT INTO sec_financial_fact
                (cik, accession_number, fiscal_year, fiscal_period, period_end,
                 period_start, form_type, concept, value, unit, decimals,
                 segment, parser_version, ingested_at)
            VALUES
                (320193, '0001193125-24-100000', 2024, 'Q2', '2024-06-30',
                 '2024-04-01', '10-Q', 'us-gaap:NetIncomeLoss', 1000.0, 'USD', -6,
                 'consolidated', 'v1', '2024-01-01T00:00:00Z'),
                (320193, '0001193125-24-100000', 2024, 'Q2', '2024-06-30',
                 '2024-01-01', '10-Q', 'us-gaap:NetIncomeLoss', 2500.0, 'USD', -6,
                 'consolidated', 'v1', '2024-01-01T00:00:00Z')
            """
        )

        table = _build_sec_financial_fact(conn)

        self.assertEqual(table.schema, _SEC_FINANCIAL_FACT_SCHEMA)
        self.assertEqual(table.num_rows, 2)

        period_starts = sorted(table.column("period_start").to_pylist())
        self.assertEqual(
            period_starts,
            [datetime.date(2024, 1, 1), datetime.date(2024, 4, 1)],
        )

        values_by_start = dict(
            zip(table.column("period_start").to_pylist(), table.column("value").to_pylist())
        )
        self.assertEqual(values_by_start[datetime.date(2024, 4, 1)], 1000.0)
        self.assertEqual(values_by_start[datetime.date(2024, 1, 1)], 2500.0)

    def test_empty_table_uses_sentinel_schema(self) -> None:
        conn = self._connection()
        table = _build_sec_financial_fact(conn)
        self.assertEqual(table.schema, _SEC_FINANCIAL_FACT_SCHEMA)
        self.assertEqual(table.num_rows, 0)


if __name__ == "__main__":
    unittest.main()
