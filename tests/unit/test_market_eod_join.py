"""Unit tests for ERDP-07 market EOD join helpers and acceptance paths."""

from __future__ import annotations

import datetime
import os
import unittest
from typing import Any
from unittest.mock import MagicMock

from edgar_warehouse.market.eod_join import (
    SOURCE_SYSTEM_YAHOO,
    batch_eod_snapshots,
    enterprise_value,
    eod_snapshot,
    eod_snapshot_for_cik,
    normalize_cik,
    pick_primary_ticker,
)
from edgar_warehouse.market.wacc import WaccInputs, compute_wacc


# Sample-universe style fixtures (CIK → ticker) for A07.2 without Snowflake.
SAMPLE_TICKER_ROWS = [
    {"cik": "0000320193", "ticker": "AAPL", "exchange": "NASDAQ"},
    {"cik": "0000789019", "ticker": "MSFT", "exchange": "NASDAQ"},
    {"cik": "0001652044", "ticker": "GOOGL", "exchange": "NASDAQ"},
    {"cik": "0001018724", "ticker": "AMZN", "exchange": "NASDAQ"},
    {"cik": "0001045810", "ticker": "NVDA", "exchange": "NASDAQ"},
    {"cik": "0001318605", "ticker": "TSLA", "exchange": "NASDAQ"},
    # Multi-ticker CIK: prefer major exchange
    {"cik": "0001067983", "ticker": "BRK.B", "exchange": "NYSE"},
    {"cik": "0001067983", "ticker": "BRK.A", "exchange": "NYSE"},
]


def _mock_price_provider(
    prices: dict[str, float] | None = None,
    caps: dict[str, float] | None = None,
    betas: dict[str, float] | None = None,
) -> MagicMock:
    prices = prices or {}
    caps = caps or {}
    betas = betas or {}
    pp = MagicMock()
    pp.get_price.side_effect = lambda t, d: prices.get(str(t).upper())
    pp.get_market_cap.side_effect = lambda t, d: caps.get(str(t).upper())
    pp.get_beta.side_effect = lambda t: betas.get(str(t).upper())
    pp.get_risk_free_rate.return_value = 0.04
    pp.get_equity_risk_premium.return_value = 0.055
    return pp


class NormalizeCikTests(unittest.TestCase):
    def test_pads_and_strips(self) -> None:
        self.assertEqual(normalize_cik(320193), "0000320193")
        self.assertEqual(normalize_cik("320193"), "0000320193")
        self.assertEqual(normalize_cik("0000320193"), "0000320193")
        self.assertIsNone(normalize_cik(None))
        self.assertIsNone(normalize_cik(""))


class PickPrimaryTickerTests(unittest.TestCase):
    def test_resolves_known_cik(self) -> None:
        self.assertEqual(pick_primary_ticker(SAMPLE_TICKER_ROWS, "0000320193"), "AAPL")
        self.assertEqual(pick_primary_ticker(SAMPLE_TICKER_ROWS, 789019), "MSFT")

    def test_prefers_major_exchange(self) -> None:
        rows = [
            {"cik": "1", "ticker": "XXOTC", "exchange": "OTC"},
            {"cik": "1", "ticker": "XX", "exchange": "NYSE"},
        ]
        self.assertEqual(pick_primary_ticker(rows, "1"), "XX")

    def test_preferred_exchange_wins(self) -> None:
        rows = [
            {"cik": "1", "ticker": "AA", "exchange": "NYSE"},
            {"cik": "1", "ticker": "AB", "exchange": "NASDAQ"},
        ]
        self.assertEqual(
            pick_primary_ticker(rows, "1", preferred_exchange="NASDAQ"), "AB"
        )

    def test_missing_returns_none(self) -> None:
        self.assertIsNone(pick_primary_ticker(SAMPLE_TICKER_ROWS, "9999999999"))


class EnterpriseValueTests(unittest.TestCase):
    def test_ev_formula(self) -> None:
        # A07.7 helper: EV = mcap + debt - cash
        self.assertEqual(enterprise_value(100.0, 20.0, 5.0), 115.0)

    def test_missing_mcap(self) -> None:
        self.assertIsNone(enterprise_value(None, 1.0, 1.0))
        self.assertIsNone(enterprise_value(0.0, 1.0, 1.0))

    def test_missing_debt_cash_as_zero(self) -> None:
        self.assertEqual(enterprise_value(50.0, None, None), 50.0)


class EodSnapshotTests(unittest.TestCase):
    def test_snapshot_fields(self) -> None:
        pp = _mock_price_provider(
            prices={"AAPL": 200.0},
            caps={"AAPL": 3e12},
            betas={"AAPL": 1.2},
        )
        snap = eod_snapshot(pp, "aapl", "2024-12-31", cik="320193")
        self.assertEqual(snap.ticker, "AAPL")
        self.assertEqual(snap.close, 200.0)
        self.assertEqual(snap.market_cap, 3e12)
        self.assertEqual(snap.beta, 1.2)
        self.assertEqual(snap.source_system, SOURCE_SYSTEM_YAHOO)
        self.assertEqual(snap.grade, "explore")
        self.assertEqual(snap.cik, "0000320193")
        self.assertEqual(snap.warnings, ())

    def test_snapshot_warns_on_missing(self) -> None:
        pp = _mock_price_provider()
        snap = eod_snapshot(pp, "ZZZZ", "2024-12-31")
        self.assertIsNone(snap.close)
        self.assertIn("close unavailable", snap.warnings)

    def test_cik_path(self) -> None:
        """A07.2 unit path: CIK → ticker → price for sample universe CIKs."""
        prices = {r["ticker"]: 100.0 + i for i, r in enumerate(SAMPLE_TICKER_ROWS[:5])}
        caps = {t: 1e9 for t in prices}
        pp = _mock_price_provider(prices=prices, caps=caps, betas={t: 1.0 for t in prices})

        resolved = 0
        for row in SAMPLE_TICKER_ROWS[:5]:
            snap = eod_snapshot_for_cik(pp, SAMPLE_TICKER_ROWS, row["cik"], "2024-12-31")
            self.assertIsNotNone(snap)
            assert snap is not None
            self.assertIsNotNone(snap.close)
            resolved += 1
        self.assertGreaterEqual(resolved, 5)

    def test_batch_reuses_provider(self) -> None:
        """A07.6 — single provider instance for batch."""
        pp = _mock_price_provider(
            prices={"AAPL": 1.0, "MSFT": 2.0},
            caps={"AAPL": 1e9, "MSFT": 2e9},
        )
        snaps = batch_eod_snapshots(pp, ["AAPL", "MSFT"], "2024-12-31")
        self.assertEqual(len(snaps), 2)
        self.assertEqual(pp.get_price.call_count, 2)


class WaccAcceptanceTests(unittest.TestCase):
    def test_wacc_with_mock_provider(self) -> None:
        """A07.3 — compute_wacc succeeds with market mcap/beta + gold debt."""
        pp = _mock_price_provider(
            prices={"AAPL": 200.0},
            caps={"AAPL": 2.7e12},
            betas={"AAPL": 1.3},
        )
        result = compute_wacc(
            WaccInputs(
                ticker="AAPL",
                period_end="2023-09-30",
                sic_code="3571",
                total_debt=110_000_000_000,
                interest_expense=3_900_000_000,
                income_tax_expense=16_741_000_000,
                pretax_income=113_736_000_000,
            ),
            price_provider=pp,
        )
        self.assertIsNotNone(result.wacc)
        assert result.wacc is not None
        self.assertGreater(result.wacc, 0.05)
        self.assertLess(result.wacc, 0.25)
        self.assertEqual(result.market_cap, 2.7e12)
        self.assertEqual(result.beta, 1.3)


@unittest.skipUnless(
    os.environ.get("ERDP07_LIVE") == "1",
    "Set ERDP07_LIVE=1 to run live yfinance acceptance (network).",
)
class LiveYfinanceAcceptanceTests(unittest.TestCase):
    """A07.1 / A07.2 / A07.3 live checks — opt-in to avoid CI network flakiness."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import yfinance  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest("yfinance not installed; uv sync --extra market") from exc
        from edgar_warehouse.market.price_provider import PriceProvider

        cls.pp = PriceProvider()
        # Use a known recent weekday; if market closed, provider walks back.
        cls.as_of = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()

    def test_a07_1_five_liquid_closes(self) -> None:
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
        ok = 0
        for t in tickers:
            px = self.pp.get_price(t, self.as_of)
            if px is not None and px > 0:
                ok += 1
        self.assertGreaterEqual(ok, 5, f"expected ≥5 closes on {self.as_of}")

    def test_a07_2_cik_to_price(self) -> None:
        ok = 0
        for row in SAMPLE_TICKER_ROWS[:5]:
            snap = eod_snapshot_for_cik(
                self.pp, SAMPLE_TICKER_ROWS, row["cik"], self.as_of, include_beta=False
            )
            if snap is not None and snap.close is not None:
                ok += 1
        self.assertGreaterEqual(ok, 5)

    def test_a07_3_wacc_live_or_override(self) -> None:
        mcap = self.pp.get_market_cap("AAPL", self.as_of)
        beta = self.pp.get_beta("AAPL")
        # Gold-shaped debt inputs (illustrative); mcap/beta from live when present.
        result = compute_wacc(
            WaccInputs(
                ticker="AAPL",
                period_end=self.as_of,
                sic_code="3571",
                total_debt=110_000_000_000,
                interest_expense=3_900_000_000,
                income_tax_expense=16_741_000_000,
                pretax_income=113_736_000_000,
                market_cap_override=mcap if mcap else 2.7e12,
                beta_override=beta if beta else 1.2,
                risk_free_rate_override=0.04,
                erp_override=0.055,
            ),
            price_provider=None,
        )
        self.assertIsNotNone(result.wacc)


if __name__ == "__main__":
    unittest.main()
