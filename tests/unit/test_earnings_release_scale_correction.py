"""Regression tests for Ticket 42's edgartools scale-mismatch quarantine.

Ticket 42 (2026-08-05) confirmed two DISTINCT, independent upstream edgartools
defects that both produce the same "scale says millions, but the value is
small" symptom in EarningsRelease.get_key_metrics():

1. Row-classification defect (Avery Dennison, CIK 8818): the value is the
   real headline figure, just never scaled because the row's RowType was
   misclassified.
2. Row-*selection* defect (Oxford Industries, CIK 75288): in a table with
   duplicate/near-duplicate row labels (e.g. "Net earnings" vs "Adjustment to
   net earnings(9)"), edgartools grabs the value from the WRONG row -- a
   value that's already correctly scaled for *its actual row*, not the
   headline figure.

Both look identical from get_key_metrics()'s return value alone -- there is
no way to tell them apart without knowing which row a value came from, which
isn't exposed. An earlier version of parse_earnings_release() guessed case 1
and multiplied unconditionally; deployed to prod, it reproduced case 2 live
(a real $500,000 figure "corrected" to $500,000,000,000) before any bad value
reached canonical silver (saved only by an unrelated merge-conflict
protection that would not apply to a brand-new accession). This module now
nulls the suspect value instead of guessing a correction -- these tests lock
that in.
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
    def test_unscaled_looking_revenue_is_nulled_not_guessed(
        self, mock_cls, _mock_header,
    ) -> None:
        # Exact live shape from the row-classification defect (Avery
        # Dennison): revenue looks unscaled, net_income scaled fine in the
        # same row. Cannot be told apart from the row-selection defect
        # (Oxford Industries) using only this metrics dict, so it's nulled
        # rather than "corrected".
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
        self.assertIsNone(row["revenue_gaap"])
        self.assertEqual(row["net_income_gaap"], 168100000.0)

    @patch("edgar.earnings._parse_period_header", return_value={
        "fiscal_year": 2026, "fiscal_period": "Q1", "period_end": None,
    })
    @patch("edgar.earnings.EarningsRelease")
    def test_row_selection_defect_is_nulled_not_corrupted(
        self, mock_cls, _mock_header,
    ) -> None:
        # Exact live shape from the row-selection defect (Oxford Industries,
        # accession 0001171843-19-008069): net_income=500000.0 is the real,
        # already-correctly-scaled value for a non-headline adjustment row
        # that edgartools grabbed by mistake. The OLD (multiply-based)
        # implementation "corrected" this to 500000000000.0 -- a real
        # regression caught before it reached canonical silver. Must be
        # nulled, not multiplied.
        er = self._build_fake_er(metrics={
            "period": "Third Quarter - Fiscal 2019", "revenue": 123100000.0,
            "net_income": 500000.0, "eps_diluted": 0.14, "scale": Scale.MILLIONS,
        })
        mock_cls.return_value = er

        result = parse_earnings_release(
            "0001171843-19-008069", "<html>fake</html>", "8-K", 75288,
            filing_date="2019-12-11",
        )

        row = result["sec_earnings_release"][0]
        self.assertEqual(row["revenue_gaap"], 123100000.0)
        self.assertIsNone(row["net_income_gaap"])

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
        # so there is no reliable signal to act on at all -- values pass
        # through unchanged (neither corrected nor nulled).
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
