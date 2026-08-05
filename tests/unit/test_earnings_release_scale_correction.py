"""Regression tests for Ticket 42's edgartools row-classification scale-mismatch fix.

Confirmed live 2026-08-05 against real cached bytes (Avery Dennison, CIK 8818,
accession 0000008818-26-000075): edgartools 5.30.0's EarningsRelease correctly
detects the table's scale (MILLIONS) but misclassifies the revenue ("Net
sales") row's RowType as PERCENTAGE instead of AMOUNT, so get_key_metrics()
skips scaling it while an adjacent AMOUNT-classified row (net income) in the
same table scales correctly. parse_earnings_release() now reverses this by
reapplying the table's own already-detected scale to any GAAP value that is
implausibly smaller than that scale's unit.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
from edgar.earnings import Scale

from edgar_warehouse.parsers.earnings_release import parse_earnings_release


def _fake_income_statement():
    table = MagicMock()
    table.dataframe = pd.DataFrame({"Q1 2026": [2298.5]}, index=["Net sales"])
    return table


class EarningsReleaseScaleCorrectionTests(unittest.TestCase):
    def _build_fake_er(self, *, metrics):
        er = MagicMock()
        er.income_statement = _fake_income_statement()
        er.eps_reconciliation = None
        er.guidance = None
        er.get_key_metrics.return_value = metrics
        return er

    @patch("edgar.earnings._parse_period_header", return_value={
        "fiscal_year": 2026, "fiscal_period": "Q1", "period_end": None,
    })
    @patch("edgar.earnings.EarningsRelease")
    def test_unscaled_revenue_is_corrected_when_sibling_row_scaled_fine(
        self, mock_cls, _mock_header,
    ) -> None:
        # Exact live shape: revenue left unscaled by the upstream row-type bug,
        # net_income scaled correctly in the same row/table.
        er = self._build_fake_er(metrics={
            "period": "Q1 2026", "revenue": 2298.5, "net_income": 168100000.0,
            "eps_diluted": None, "scale": Scale.MILLIONS,
        })
        mock_cls.return_value = er

        result = parse_earnings_release(
            "0000008818-26-000075", "<html>fake</html>", "8-K", 8818,
            filing_date="2026-04-28",
        )

        row = result["sec_earnings_release"][0]
        self.assertEqual(row["revenue_gaap"], 2298.5 * 1_000_000)
        self.assertEqual(row["net_income_gaap"], 168100000.0)

    @patch("edgar.earnings._parse_period_header", return_value={
        "fiscal_year": 2026, "fiscal_period": "Q1", "period_end": None,
    })
    @patch("edgar.earnings.EarningsRelease")
    def test_already_scaled_values_are_left_untouched(
        self, mock_cls, _mock_header,
    ) -> None:
        er = self._build_fake_er(metrics={
            "period": "Q1 2026", "revenue": 2298500000.0, "net_income": 168100000.0,
            "eps_diluted": 1.0, "scale": Scale.MILLIONS,
        })
        mock_cls.return_value = er

        result = parse_earnings_release(
            "0000008818-26-000075", "<html>fake</html>", "8-K", 8818,
            filing_date="2026-04-28",
        )

        row = result["sec_earnings_release"][0]
        self.assertEqual(row["revenue_gaap"], 2298500000.0)
        self.assertEqual(row["net_income_gaap"], 168100000.0)

    @patch("edgar.earnings._parse_period_header", return_value={
        "fiscal_year": 2026, "fiscal_period": "Q1", "period_end": None,
    })
    @patch("edgar.earnings.EarningsRelease")
    def test_undetected_scale_is_not_guessed_at(self, mock_cls, _mock_header) -> None:
        # Separate, unhandled upstream defect (scale-detection-miss, e.g. LPX/
        # CIK 60519 in the same investigation): scale itself is UNITS/unknown,
        # so there is no reliable signal to correct from -- values pass through
        # unchanged rather than being guessed at.
        er = self._build_fake_er(metrics={
            "period": "Q1 2026", "revenue": 658.0, "net_income": 59.0,
            "eps_diluted": 0.81, "scale": Scale.UNITS,
        })
        mock_cls.return_value = er

        result = parse_earnings_release(
            "0001628280-24-004559", "<html>fake</html>", "8-K", 60519,
            filing_date="2024-02-14",
        )

        row = result["sec_earnings_release"][0]
        self.assertEqual(row["revenue_gaap"], 658.0)
        self.assertEqual(row["net_income_gaap"], 59.0)

    @patch("edgar.earnings._parse_period_header", return_value={
        "fiscal_year": 2026, "fiscal_period": "Q1", "period_end": None,
    })
    @patch("edgar.earnings.EarningsRelease")
    def test_missing_scale_key_is_backward_compatible(self, mock_cls, _mock_header) -> None:
        # Older/mocked metrics dicts (e.g. this repo's own guidance-wiring
        # tests) omit the 'scale' key entirely -- must not raise or alter
        # values.
        er = self._build_fake_er(metrics={
            "period": "Q1 2026", "revenue": 1000.0, "net_income": 100.0, "eps_diluted": 1.0,
        })
        mock_cls.return_value = er

        result = parse_earnings_release(
            "0000320193-26-000042", "<html>fake</html>", "8-K", 320193,
            filing_date="2026-07-20",
        )

        row = result["sec_earnings_release"][0]
        self.assertEqual(row["revenue_gaap"], 1000.0)
        self.assertEqual(row["net_income_gaap"], 100.0)


if __name__ == "__main__":
    unittest.main()
