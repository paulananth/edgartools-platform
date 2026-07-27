"""Unit tests for ERDP-01 consensus estimates Explore product."""

from __future__ import annotations

import unittest
from datetime import date

from edgar_warehouse.explore.consensus_estimates import (
    ConsensusRowError,
    build_consensus_estimates_table,
    consensus_fact_key,
    current_consensus_rows,
    load_firm_manual_csv,
    normalize_consensus_row,
    parse_yahoo_consensus_estimate,
)


class NormalizeTests(unittest.TestCase):
    def test_quarterly_row(self) -> None:
        row = normalize_consensus_row(
            {
                "cik": "0000320193",
                "ticker": "aapl",
                "metric": "eps_diluted",
                "period_type": "quarterly",
                "fiscal_year": 2026,
                "fiscal_quarter": 3,
                "estimate_value": 1.42,
                "statistic": "mean",
                "as_of": "2026-06-01",
                "source_system": "yahoo",
            }
        )
        self.assertEqual(row["cik"], 320193)
        self.assertEqual(row["ticker"], "AAPL")
        self.assertEqual(row["unit"], "per_share")
        self.assertIsNotNone(row["fact_key"])

    def test_annual_forces_fiscal_quarter_zero(self) -> None:
        """D2: annual encodes fiscal_quarter=0."""
        row = normalize_consensus_row(
            {
                "cik": 1,
                "metric": "revenue",
                "period_type": "annual",
                "fiscal_year": 2026,
                "estimate_value": 5000.0,
                "statistic": "mean",
                "as_of": "2026-01-01",
                "source_system": "firm_manual",
            }
        )
        self.assertEqual(row["fiscal_quarter"], 0)
        self.assertEqual(row["unit"], "USD")

    def test_ntm_allows_null_fiscal_period(self) -> None:
        row = normalize_consensus_row(
            {
                "cik": 1,
                "metric": "revenue",
                "period_type": "ntm",
                "estimate_value": 20000.0,
                "statistic": "mean",
                "as_of": "2026-01-01",
                "source_system": "firm_manual",
            }
        )
        self.assertIsNone(row["fiscal_year"])
        self.assertIsNone(row["fiscal_quarter"])

    def test_quarterly_requires_fiscal_quarter(self) -> None:
        with self.assertRaises(ConsensusRowError):
            normalize_consensus_row(
                {
                    "cik": 1,
                    "metric": "revenue",
                    "period_type": "quarterly",
                    "fiscal_year": 2026,
                    "estimate_value": 100.0,
                    "statistic": "mean",
                    "as_of": "2026-01-01",
                    "source_system": "firm_manual",
                }
            )

    def test_unknown_metric_rejected(self) -> None:
        """ERDP-01-06: unknown metrics rejected."""
        with self.assertRaises(ConsensusRowError):
            normalize_consensus_row(
                {
                    "cik": 1,
                    "metric": "vaporware_multiple",
                    "period_type": "annual",
                    "fiscal_year": 2026,
                    "estimate_value": 1.0,
                    "statistic": "mean",
                    "as_of": "2026-01-01",
                    "source_system": "firm_manual",
                }
            )

    def test_unknown_source_system_falls_back_to_other(self) -> None:
        row = normalize_consensus_row(
            {
                "cik": 1,
                "metric": "revenue",
                "period_type": "annual",
                "fiscal_year": 2026,
                "estimate_value": 100.0,
                "statistic": "mean",
                "as_of": "2026-01-01",
                "source_system": "some_new_vendor",
            }
        )
        self.assertEqual(row["source_system"], "other")

    def test_fact_key_deterministic(self) -> None:
        k1 = consensus_fact_key(1, "revenue", "annual", 2026, 0, "mean", date(2026, 1, 1), "yahoo")
        k2 = consensus_fact_key(1, "revenue", "annual", 2026, 0, "mean", date(2026, 1, 1), "yahoo")
        self.assertEqual(k1, k2)

    def test_arrow_table_schema(self) -> None:
        table = build_consensus_estimates_table(
            [
                {
                    "cik": 320193,
                    "ticker": "AAPL",
                    "metric": "eps_diluted",
                    "period_type": "quarterly",
                    "fiscal_year": 2026,
                    "fiscal_quarter": 3,
                    "estimate_value": 1.42,
                    "statistic": "mean",
                    "as_of": date(2026, 6, 1),
                    "source_system": "yahoo",
                }
            ]
        )
        self.assertEqual(table.num_rows, 1)
        names = set(table.schema.names)
        for col in (
            "fact_key", "cik", "metric", "period_type", "fiscal_year",
            "fiscal_quarter", "estimate_value", "unit", "statistic",
            "as_of", "source_system",
        ):
            self.assertIn(col, names)

    def test_empty_rows_returns_empty_table_with_schema(self) -> None:
        table = build_consensus_estimates_table([])
        self.assertEqual(table.num_rows, 0)
        self.assertIn("fact_key", table.schema.names)


class FirmManualTests(unittest.TestCase):
    def test_load_one_cik_round_trip(self) -> None:
        """A01.6 / ERDP-01-07 — firm_manual CSV round-trip for ≥1 CIK."""
        csv_text = """cik,ticker,metric,period_type,fiscal_year,fiscal_quarter,estimate_value,as_of
320193,AAPL,revenue,quarterly,2026,3,95000,2026-06-01
320193,AAPL,eps_diluted,quarterly,2026,3,1.42,2026-06-01
"""
        rows = load_firm_manual_csv(csv_text)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["source_system"] for r in rows}, {"firm_manual"})
        self.assertEqual({r["statistic"] for r in rows}, {"mean"})
        table = build_consensus_estimates_table(rows)
        self.assertEqual(table.num_rows, 2)


class YahooParseTests(unittest.TestCase):
    def test_parse_earnings_estimate_frame(self) -> None:
        frame = {
            "0q": {"avg": 1.42, "low": 1.30, "high": 1.55, "numberOfAnalysts": 20},
            "+1q": {"avg": 1.50, "low": 1.40, "high": 1.60, "numberOfAnalysts": 18},
        }
        resolution = {
            "0q": {"period_type": "quarterly", "fiscal_year": 2026, "fiscal_quarter": 3},
            "+1q": {"period_type": "quarterly", "fiscal_year": 2026, "fiscal_quarter": 4},
        }
        rows = parse_yahoo_consensus_estimate(
            cik=320193, ticker="AAPL", metric="eps_diluted",
            estimate_frame=frame, period_resolution=resolution,
            as_of=date(2026, 6, 1),
        )
        # 4 stats (mean/low/high/n_analysts) x 2 periods
        self.assertEqual(len(rows), 8)
        self.assertEqual({r["source_system"] for r in rows}, {"yahoo"})
        mean_row = next(r for r in rows if r["statistic"] == "mean" and r["fiscal_quarter"] == 3)
        self.assertEqual(mean_row["estimate_value"], 1.42)

    def test_unresolved_label_is_skipped(self) -> None:
        frame = {"0q": {"avg": 1.42}}
        rows = parse_yahoo_consensus_estimate(
            cik=1, ticker="X", metric="eps_diluted",
            estimate_frame=frame, period_resolution={},
        )
        self.assertEqual(rows, [])


class CurrentRowsTests(unittest.TestCase):
    def test_keeps_latest_as_of_per_base_key(self) -> None:
        """A01.2 semantics at read time: latest as_of wins per base key."""
        rows = [
            {
                "cik": 1, "metric": "revenue", "period_type": "annual",
                "fiscal_year": 2026, "estimate_value": 100.0, "statistic": "mean",
                "as_of": "2026-01-01", "source_system": "yahoo",
            },
            {
                "cik": 1, "metric": "revenue", "period_type": "annual",
                "fiscal_year": 2026, "estimate_value": 110.0, "statistic": "mean",
                "as_of": "2026-02-01", "source_system": "yahoo",
            },
        ]
        cur = current_consensus_rows(rows)
        self.assertEqual(len(cur), 1)
        self.assertEqual(cur[0]["estimate_value"], 110.0)

    def test_two_as_of_snapshots_both_retained_upstream(self) -> None:
        """A01.2: two different as_of for the same period are both retained
        (this validates upstream retention -- current_consensus_rows only
        projects the read-time 'latest' view; it does not discard history)."""
        rows = [
            {
                "cik": 1, "metric": "revenue", "period_type": "annual",
                "fiscal_year": 2026, "estimate_value": 100.0, "statistic": "mean",
                "as_of": "2026-01-01", "source_system": "yahoo",
            },
            {
                "cik": 1, "metric": "revenue", "period_type": "annual",
                "fiscal_year": 2026, "estimate_value": 110.0, "statistic": "mean",
                "as_of": "2026-02-01", "source_system": "yahoo",
            },
        ]
        table = build_consensus_estimates_table(rows)
        self.assertEqual(table.num_rows, 2)
        self.assertEqual(sorted(table.column("as_of").to_pylist()), [date(2026, 1, 1), date(2026, 2, 1)])

    def test_multi_source_coexist_via_source_system_in_key(self) -> None:
        """D3: yahoo and firm_manual rows for the same period both survive."""
        rows = [
            {
                "cik": 1, "metric": "revenue", "period_type": "annual",
                "fiscal_year": 2026, "estimate_value": 100.0, "statistic": "mean",
                "as_of": "2026-01-01", "source_system": "yahoo",
            },
            {
                "cik": 1, "metric": "revenue", "period_type": "annual",
                "fiscal_year": 2026, "estimate_value": 105.0, "statistic": "mean",
                "as_of": "2026-01-01", "source_system": "firm_manual",
            },
        ]
        cur = current_consensus_rows(rows)
        self.assertEqual(len(cur), 2)
        self.assertEqual({r["source_system"] for r in cur}, {"yahoo", "firm_manual"})


if __name__ == "__main__":
    unittest.main()
