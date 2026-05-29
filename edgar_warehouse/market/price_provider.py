"""Market price and benchmark data provider.

Provides closing prices, market caps, risk-free rates, and equity risk premiums
needed to compute WACC and EV/EBITDA multiples for the gold layer.

Data sources (in priority order):
  1. yfinance       — closing prices, shares outstanding, beta
  2. FRED (fredapi) — risk-free rate (DGS10 = 10-year Treasury yield)
  3. Damodaran      — industry equity risk premium (downloaded from NYU Stern)

Usage
-----
from edgar_warehouse.market.price_provider import PriceProvider

pp = PriceProvider()
px = pp.get_price("AAPL", date="2023-12-31")        # closing price
mc = pp.get_market_cap("AAPL", date="2023-12-31")   # market cap USD
rf = pp.get_risk_free_rate(date="2023-12-31")        # annualised 10-yr yield
erp = pp.get_equity_risk_premium(sic_code="7372")    # industry ERP

Caching
-------
Prices are cached in-memory for the lifetime of the PriceProvider instance.
For batch runs, create a single instance and pass it to all WACC callers.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# Damodaran ERP table URL (updated January each year)
_DAMODARAN_ERP_URL = (
    "http://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbyindustry.xlsx"
)

# FRED series for risk-free rate
_FRED_SERIES_RF = "DGS10"  # 10-year Treasury constant maturity rate


class PriceProvider:
    """Lightweight market data facade.

    Requires ``pip install edgartools-platform[market]`` (yfinance + fredapi).
    """

    def __init__(self, fred_api_key: str | None = None) -> None:
        self._fred_api_key = fred_api_key
        self._price_cache: dict[str, dict[str, float]] = {}   # {ticker: {date_str: price}}
        self._rf_cache: dict[str, float] = {}                 # {date_str: rate}
        self._erp_cache: dict[str, float] | None = None       # {sic_code: erp}
        self._beta_cache: dict[str, float] = {}               # {ticker: beta}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def get_price(self, ticker: str, date: str | date) -> float | None:
        """Return closing price for *ticker* on *date* (or most recent prior).

        Parameters
        ----------
        ticker:
            Stock ticker symbol (e.g. "AAPL").
        date:
            ISO date string "YYYY-MM-DD" or ``datetime.date`` object.

        Returns
        -------
        float closing price in USD, or None if unavailable.
        """
        date_str = _to_date_str(date)
        if ticker not in self._price_cache:
            self._price_cache[ticker] = {}
        if date_str in self._price_cache[ticker]:
            return self._price_cache[ticker][date_str]

        price = self._fetch_price_yfinance(ticker, date_str)
        self._price_cache[ticker][date_str] = price  # type: ignore[assignment]
        return price

    def get_market_cap(self, ticker: str, date: str | date) -> float | None:
        """Return market capitalisation for *ticker* on *date* in USD.

        Computed as: closing_price × shares_outstanding (basic).
        """
        price = self.get_price(ticker, date)
        if price is None:
            return None
        shares = self._fetch_shares_outstanding(ticker)
        if shares is None:
            return None
        return price * shares

    def get_beta(self, ticker: str) -> float | None:
        """Return trailing 5-year monthly beta (vs S&P 500) for *ticker*."""
        if ticker in self._beta_cache:
            return self._beta_cache[ticker]
        beta = self._fetch_beta_yfinance(ticker)
        if beta is not None:
            self._beta_cache[ticker] = beta
        return beta

    def get_risk_free_rate(self, date: str | date) -> float | None:
        """Return annualised 10-year Treasury yield on *date* (decimal form).

        E.g. returns 0.0425 for a 4.25% yield.  Requires FRED API key or
        FRED_API_KEY env var.
        """
        date_str = _to_date_str(date)
        if date_str in self._rf_cache:
            return self._rf_cache[date_str]

        rate = self._fetch_fred_rate(date_str)
        if rate is not None:
            self._rf_cache[date_str] = rate
        return rate

    def get_equity_risk_premium(self, sic_code: str | None = None) -> float:
        """Return Damodaran equity risk premium for the given SIC code.

        Falls back to the total market ERP (~5.7%) if SIC cannot be mapped.
        """
        if self._erp_cache is None:
            self._erp_cache = self._load_damodaran_erp()

        if sic_code and self._erp_cache:
            # Map SIC-2 to Damodaran industry — simplified lookup
            erp = self._erp_cache.get(sic_code[:2])
            if erp is not None:
                return erp

        # Default total-market ERP (Damodaran January 2025 estimate)
        return 0.057

    # -----------------------------------------------------------------------
    # Private fetch methods — lazy imports so yfinance/fredapi are optional
    # -----------------------------------------------------------------------

    def _fetch_price_yfinance(self, ticker: str, date_str: str) -> float | None:
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not installed — cannot fetch prices")
            return None

        try:
            # Download one extra day to handle weekends/holidays
            end_dt = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=3)
            df = yf.download(
                ticker,
                start=date_str,
                end=end_dt.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
            if df.empty:
                return None
            # Return the Close on the date closest to and ≤ date_str
            df.index = df.index.date  # type: ignore[attr-defined]
            target = datetime.strptime(date_str, "%Y-%m-%d").date()
            available = [d for d in df.index if d <= target]
            if not available:
                return None
            closest = max(available)
            close = df.loc[closest, "Close"]
            if hasattr(close, "item"):
                close = close.item()
            return float(close)
        except Exception as exc:
            logger.debug("yfinance price fetch failed for %s: %s", ticker, exc)
            return None

    def _fetch_shares_outstanding(self, ticker: str) -> float | None:
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            info = yf.Ticker(ticker).info
            shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            return float(shares) if shares else None
        except Exception:
            return None

    def _fetch_beta_yfinance(self, ticker: str) -> float | None:
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            info = yf.Ticker(ticker).info
            beta = info.get("beta")
            return float(beta) if beta is not None else None
        except Exception:
            return None

    def _fetch_fred_rate(self, date_str: str) -> float | None:
        import os
        api_key = self._fred_api_key or os.environ.get("FRED_API_KEY")
        if not api_key:
            logger.debug("FRED_API_KEY not set — cannot fetch risk-free rate")
            return None
        try:
            from fredapi import Fred
            fred = Fred(api_key=api_key)
            series = fred.get_series(
                _FRED_SERIES_RF,
                observation_start=date_str,
                observation_end=date_str,
            )
            if series.empty:
                # Try 3 days prior to handle weekends
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                start = (dt - timedelta(days=5)).strftime("%Y-%m-%d")
                series = fred.get_series(
                    _FRED_SERIES_RF,
                    observation_start=start,
                    observation_end=date_str,
                )
            if series.empty:
                return None
            rate_pct = float(series.iloc[-1])  # e.g. 4.25 (percent)
            return rate_pct / 100.0
        except ImportError:
            logger.warning("fredapi not installed — cannot fetch risk-free rate")
            return None
        except Exception as exc:
            logger.debug("FRED rate fetch failed: %s", exc)
            return None

    def _load_damodaran_erp(self) -> dict[str, float]:
        """Download Damodaran's industry ERP table and return {sic2: erp_decimal}."""
        try:
            import pandas as pd
            df = pd.read_excel(_DAMODARAN_ERP_URL, sheet_name=0, header=0)
            # Damodaran file has SIC code and ERP columns; column names vary by year
            # Best-effort: look for numeric SIC column and ERP % column
            erp_map: dict[str, float] = {}
            for col in df.columns:
                if "erp" in str(col).lower() or "equity risk" in str(col).lower():
                    erp_col = col
                    break
            else:
                return {}
            sic_col = df.columns[0]
            for _, row in df.iterrows():
                try:
                    sic = str(int(row[sic_col]))[:2]
                    erp = float(row[erp_col])
                    if erp > 1:  # stored as percent
                        erp = erp / 100.0
                    erp_map[sic] = erp
                except (ValueError, TypeError):
                    continue
            return erp_map
        except Exception as exc:
            logger.debug("Damodaran ERP load failed: %s", exc)
            return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_date_str(d: str | date) -> str:
    if isinstance(d, str):
        return d[:10]
    return d.isoformat()
