"""Integration test for ERDP-02 wiring into edgar_warehouse.parsers.earnings_release.

Confirms parse_earnings_release() emits sec_guidance_fact rows (not just the
has_guidance presence flag) when the EarningsRelease exposes a guidance
table, without needing a real bronze 8-K fetch -- mocks edgar.earnings.
EarningsRelease at the construction site, same boundary the parser itself
treats as external (bronze-replay architecture, see module docstring).
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from edgar_warehouse.parsers.earnings_release import parse_earnings_release


def _fake_income_statement():
    table = MagicMock()
    table.dataframe = pd.DataFrame({"Q3 2026": [1000.0]}, index=["Revenue"])
    return table


def _fake_guidance_table():
    table = MagicMock()
    df = pd.DataFrame({"Q4 2026": ["$1,200 - $1,300"]}, index=["Revenue"])
    table.scaled_dataframe = df
    table.dataframe = df
    return table


class ParseEarningsReleaseGuidanceWiringTests(unittest.TestCase):
    def _build_fake_er(self, *, guidance, has_eps_reconciliation=False):
        er = MagicMock()
        er.income_statement = _fake_income_statement()
        er.eps_reconciliation = MagicMock() if has_eps_reconciliation else None
        er.guidance = guidance
        return er

    @patch("edgar.earnings._parse_period_header", return_value={
        "fiscal_year": 2026, "fiscal_period": "Q3", "period_end": None,
    })
    @patch("edgar.earnings.EarningsRelease")
    def test_guidance_rows_emitted_when_table_present(self, mock_cls, _mock_header) -> None:
        er = self._build_fake_er(guidance=_fake_guidance_table())
        er.get_key_metrics.return_value = {
            "period": "Q3 2026", "revenue": 1000.0, "net_income": 100.0, "eps_diluted": 1.0,
        }
        mock_cls.return_value = er

        result = parse_earnings_release(
            "0000320193-26-000042", "<html>fake</html>", "8-K", 320193,
            filing_date="2026-07-20",
        )

        self.assertEqual(len(result["sec_earnings_release"]), 1)
        self.assertTrue(result["sec_earnings_release"][0]["has_guidance"])
        self.assertEqual(len(result["sec_guidance_fact"]), 1)
        row = result["sec_guidance_fact"][0]
        self.assertEqual(row["accession_number"], "0000320193-26-000042")
        self.assertEqual(row["metric"], "revenue")
        self.assertEqual(row["source_system"], "sec_8k")
        self.assertEqual(result["sec_guidance_fact_reject"], [])

    @patch("edgar.earnings._parse_period_header", return_value={
        "fiscal_year": 2026, "fiscal_period": "Q3", "period_end": None,
    })
    @patch("edgar.earnings.EarningsRelease")
    def test_no_guidance_table_yields_empty_guidance_rows(self, mock_cls, _mock_header) -> None:
        er = self._build_fake_er(guidance=None)
        er.get_key_metrics.return_value = {
            "period": "Q3 2026", "revenue": 1000.0, "net_income": 100.0, "eps_diluted": 1.0,
        }
        mock_cls.return_value = er

        result = parse_earnings_release(
            "0000320193-26-000043", "<html>fake</html>", "8-K", 320193,
            filing_date="2026-07-20",
        )

        self.assertFalse(result["sec_earnings_release"][0]["has_guidance"])
        self.assertEqual(result["sec_guidance_fact"], [])
        self.assertEqual(result["sec_guidance_fact_reject"], [])

    def test_empty_content_yields_no_guidance_keys(self) -> None:
        result = parse_earnings_release("acc-1", "", "8-K", 1, filing_date="2026-01-01")
        self.assertEqual(result, {"sec_earnings_release": []})

    @patch("edgar.earnings._parse_period_header", return_value={
        "fiscal_year": 2026, "fiscal_period": "Q3", "period_end": None,
    })
    @patch("edgar.earnings.EarningsRelease")
    def test_guidance_probe_exception_is_quarantined_not_treated_as_absent(
        self, mock_cls, _mock_header,
    ) -> None:
        # Regression guard for the GUIDANCE_FACTS promotion-checklist blocking
        # prerequisite: an exception while probing er.guidance must not look
        # identical to a confirmed "no guidance issued" -- it has to show up
        # somewhere so the extraction-yield criterion (ticket 04) can tell
        # the two apart.
        er = MagicMock()
        er.income_statement = _fake_income_statement()
        er.eps_reconciliation = None
        er.get_key_metrics.return_value = {
            "period": "Q3 2026", "revenue": 1000.0, "net_income": 100.0, "eps_diluted": 1.0,
        }
        type(er).guidance = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        mock_cls.return_value = er

        result = parse_earnings_release(
            "0000320193-26-000044", "<html>fake</html>", "8-K", 320193,
            filing_date="2026-07-20",
        )

        self.assertFalse(result["sec_earnings_release"][0]["has_guidance"])
        self.assertEqual(result["sec_guidance_fact"], [])
        self.assertEqual(len(result["sec_guidance_fact_reject"]), 1)
        reject = result["sec_guidance_fact_reject"][0]
        self.assertTrue(reject["reject_reason"].startswith("guidance_probe_exception:"))
        self.assertIsNone(reject["metric"])
        self.assertEqual(reject["accession_number"], "0000320193-26-000044")

    @patch("edgar.earnings._parse_period_header", return_value={
        "fiscal_year": 2026, "fiscal_period": "Q3", "period_end": None,
    })
    @patch("edgar.earnings.EarningsRelease")
    def test_guidance_extraction_exception_is_quarantined(self, mock_cls, _mock_header) -> None:
        table = MagicMock()
        type(table).scaled_dataframe = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("scaled boom"))
        )
        type(table).dataframe = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("plain boom"))
        )
        er = self._build_fake_er(guidance=table)
        er.get_key_metrics.return_value = {
            "period": "Q3 2026", "revenue": 1000.0, "net_income": 100.0, "eps_diluted": 1.0,
        }
        mock_cls.return_value = er

        result = parse_earnings_release(
            "0000320193-26-000045", "<html>fake</html>", "8-K", 320193,
            filing_date="2026-07-20",
        )

        # Presence probe succeeded (table exists) -- only extraction failed.
        self.assertTrue(result["sec_earnings_release"][0]["has_guidance"])
        self.assertEqual(result["sec_guidance_fact"], [])
        self.assertEqual(len(result["sec_guidance_fact_reject"]), 1)
        reject = result["sec_guidance_fact_reject"][0]
        self.assertTrue(reject["reject_reason"].startswith("guidance_extraction_exception:"))


if __name__ == "__main__":
    unittest.main()
