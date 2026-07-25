"""Unit tests for ERDP-03 earnings calendar Explore product."""

from __future__ import annotations

import os
import unittest
from datetime import date, datetime, timezone

from edgar_warehouse.explore.earnings_calendar import (
    CalendarRowError,
    build_earnings_calendar_table,
    coverage_for_universe,
    current_calendar_rows,
    load_firm_manual_csv,
    map_session,
    mark_reported,
    next_n_days,
    normalize_calendar_row,
    parse_finnhub_earnings_calendar,
)


class MapSessionTests(unittest.TestCase):
    def test_vendor_aliases(self) -> None:
        self.assertEqual(map_session("bmo"), "pre_market")
        self.assertEqual(map_session("AMC"), "after_close")
        self.assertEqual(map_session("dmh"), "during_session")
        self.assertEqual(map_session(None), "unknown")
        self.assertEqual(map_session("???"), "unknown")


class NormalizeTests(unittest.TestCase):
    def test_minimal_row(self) -> None:
        row = normalize_calendar_row(
            {
                "cik": "0000320193",
                "fiscal_year": 2025,
                "fiscal_quarter": 3,
                "expected_date": "2025-07-31",
                "hour": "amc",
                "source_system": "finnhub",
                "as_of": "2025-07-01",
            }
        )
        self.assertEqual(row["cik"], 320193)
        self.assertEqual(row["session"], "after_close")
        self.assertEqual(row["status"], "estimated")
        self.assertEqual(row["source_system"], "finnhub")
        self.assertIsNotNone(row["fact_key"])

    def test_confirmed_rejects_unknown_session(self) -> None:
        with self.assertRaises(CalendarRowError):
            normalize_calendar_row(
                {
                    "cik": 1,
                    "fiscal_year": 2025,
                    "fiscal_quarter": 1,
                    "expected_date": "2025-01-15",
                    "status": "confirmed",
                    "session": "unknown",
                    "source_system": "firm_manual",
                    "as_of": "2025-01-01",
                }
            )

    def test_arrow_table_schema(self) -> None:
        table = build_earnings_calendar_table(
            [
                {
                    "cik": 320193,
                    "ticker": "AAPL",
                    "fiscal_year": 2025,
                    "fiscal_quarter": 3,
                    "expected_date": date(2025, 7, 31),
                    "session": "after_close",
                    "status": "estimated",
                    "source_system": "finnhub",
                    "as_of": date(2025, 7, 1),
                }
            ]
        )
        self.assertEqual(table.num_rows, 1)
        names = set(table.schema.names)
        for col in (
            "fact_key",
            "cik",
            "expected_date",
            "session",
            "status",
            "source_system",
            "as_of",
            "expected_time",
            "timezone",
        ):
            self.assertIn(col, names)


class FirmManualTests(unittest.TestCase):
    def test_load_three_ciks(self) -> None:
        """A03.6 / ERDP-03-06 — firm_manual for ≥3 CIKs."""
        csv_text = """cik,ticker,fiscal_year,fiscal_quarter,expected_date,session,status,as_of
320193,AAPL,2025,3,2025-07-31,after_close,confirmed,2025-07-01
789019,MSFT,2025,4,2025-07-30,after_close,confirmed,2025-07-01
1652044,GOOGL,2025,2,2025-07-29,after_close,confirmed,2025-07-01
"""
        rows = load_firm_manual_csv(csv_text)
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["source_system"] for r in rows}, {"firm_manual"})
        self.assertTrue(all(r["status"] == "confirmed" for r in rows))
        self.assertTrue(all(r["session"] != "unknown" for r in rows))
        table = build_earnings_calendar_table(rows)
        self.assertEqual(table.num_rows, 3)


class FinnhubParseTests(unittest.TestCase):
    def test_parse_payload(self) -> None:
        payload = {
            "earningsCalendar": [
                {
                    "symbol": "AAPL",
                    "date": "2025-07-31",
                    "hour": "amc",
                    "quarter": 3,
                    "year": 2025,
                },
                {
                    "symbol": "UNKNOWN",
                    "date": "2025-08-01",
                    "hour": "bmo",
                    "quarter": 2,
                    "year": 2025,
                },
            ]
        }
        rows = parse_finnhub_earnings_calendar(
            payload,
            ticker_to_cik={"AAPL": 320193},
            as_of=date(2025, 7, 1),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "AAPL")
        self.assertEqual(rows[0]["session"], "after_close")
        self.assertEqual(rows[0]["source_system"], "finnhub")


class CurrentAndCoverageTests(unittest.TestCase):
    def test_current_keeps_latest_as_of(self) -> None:
        rows = [
            {
                "cik": 1,
                "fiscal_year": 2025,
                "fiscal_quarter": 1,
                "expected_date": "2025-04-15",
                "session": "after_close",
                "status": "estimated",
                "source_system": "finnhub",
                "as_of": "2025-01-01",
            },
            {
                "cik": 1,
                "fiscal_year": 2025,
                "fiscal_quarter": 1,
                "expected_date": "2025-04-16",
                "session": "after_close",
                "status": "confirmed",
                "source_system": "finnhub",
                "as_of": "2025-02-01",
            },
        ]
        cur = current_calendar_rows(rows)
        self.assertEqual(len(cur), 1)
        self.assertEqual(cur[0]["expected_date"], date(2025, 4, 16))
        self.assertEqual(cur[0]["status"], "confirmed")

    def test_a03_1_coverage_rate(self) -> None:
        today = date(2025, 7, 1)
        # 10 CIKs; 8 with forward dates → 80%
        rows = []
        for i in range(1, 11):
            if i <= 8:
                rows.append(
                    {
                        "cik": i,
                        "fiscal_year": 2025,
                        "fiscal_quarter": 3,
                        "expected_date": "2025-07-15",
                        "session": "after_close",
                        "status": "estimated",
                        "source_system": "finnhub",
                        "as_of": "2025-07-01",
                    }
                )
        stats = coverage_for_universe(rows, range(1, 11), today=today)
        self.assertEqual(stats["universe_size"], 10)
        self.assertEqual(stats["covered"], 8)
        self.assertAlmostEqual(stats["coverage_rate"], 0.8)
        self.assertTrue(stats["meets_a03_1"])

    def test_next_14_days(self) -> None:
        today = date(2025, 7, 1)
        rows = [
            {
                "cik": 1,
                "fiscal_year": 2025,
                "fiscal_quarter": 3,
                "expected_date": "2025-07-10",
                "session": "pre_market",
                "status": "confirmed",
                "source_system": "firm_manual",
                "as_of": "2025-07-01",
            },
            {
                "cik": 2,
                "fiscal_year": 2025,
                "fiscal_quarter": 3,
                "expected_date": "2025-08-20",
                "session": "after_close",
                "status": "estimated",
                "source_system": "finnhub",
                "as_of": "2025-07-01",
            },
        ]
        upcoming = next_n_days(rows, days=14, today=today)
        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming[0]["cik"], 1)


class MarkReportedTests(unittest.TestCase):
    def test_marks_matching_period(self) -> None:
        cal = [
            {
                "cik": 320193,
                "fiscal_year": 2025,
                "fiscal_quarter": 2,
                "expected_date": "2025-04-30",
                "session": "after_close",
                "status": "confirmed",
                "source_system": "firm_manual",
                "as_of": "2025-04-01",
            }
        ]
        releases = [
            {
                "cik": 320193,
                "fiscal_year": 2025,
                "fiscal_quarter": 2,
                "accession_number": "0000320193-25-000001",
            }
        ]
        out = mark_reported(cal, releases, as_of=date(2025, 5, 1))
        self.assertEqual(out[0]["status"], "reported")
        self.assertEqual(out[0]["accession_number"], "0000320193-25-000001")
        self.assertEqual(out[0]["as_of"], date(2025, 5, 1))


class GoldSchemaRegistryTests(unittest.TestCase):
    def test_calendar_schema_registered(self) -> None:
        from edgar_warehouse.serving.gold_schema_registry import GOLD_SCHEMAS

        schema = GOLD_SCHEMAS["_FACT_EARNINGS_CALENDAR_SCHEMA"]
        self.assertEqual(schema.field("fact_key").nullable, False)
        self.assertEqual(schema.field("session").nullable, False)
        self.assertEqual(schema.field("source_system").nullable, False)


class ExportMapTests(unittest.TestCase):
    def test_manifest_includes_earnings_calendar(self) -> None:
        from edgar_warehouse.infrastructure.run_manifest_builder import (
            SNOWFLAKE_EXPORT_TABLES,
        )

        self.assertEqual(SNOWFLAKE_EXPORT_TABLES["EARNINGS_CALENDAR"], "earnings_calendar")


@unittest.skipUnless(
    os.environ.get("ERDP03_LIVE") == "1" and os.environ.get("FINNHUB_API_KEY"),
    "Set ERDP03_LIVE=1 and FINNHUB_API_KEY for live Finnhub fetch.",
)
class LiveFinnhubTests(unittest.TestCase):
    def test_fetch_window(self) -> None:
        from datetime import timedelta

        from edgar_warehouse.explore.earnings_calendar import (
            fetch_finnhub_earnings_calendar,
        )

        today = date.today()
        rows = fetch_finnhub_earnings_calendar(
            from_date=today,
            to_date=today + timedelta(days=14),
            ticker_to_cik={
                "AAPL": 320193,
                "MSFT": 789019,
                "GOOGL": 1652044,
                "AMZN": 1018724,
                "NVDA": 1045810,
            },
        )
        # Free API may return empty outside earnings season; just ensure no crash
        self.assertIsInstance(rows, list)
        for r in rows:
            self.assertEqual(r["source_system"], "finnhub")
            self.assertIn(r["session"], {"pre_market", "after_close", "during_session", "unknown"})


if __name__ == "__main__":
    unittest.main()
