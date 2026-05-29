"""Weighted Average Cost of Capital (WACC) computation.

Implements the standard textbook WACC formula:

  WACC = (E/V) × Ke + (D/V) × Kd × (1 - t)

Where:
  E    = market value of equity  (market cap from price_provider)
  D    = book value of debt      (total_debt from sec_financial_fact)
  V    = E + D
  Ke   = cost of equity         (CAPM: Rf + β × ERP)
  Kd   = cost of debt           (interest_expense / total_debt)
  t    = effective tax rate      (income_tax_expense / pretax_income)

Data sources
------------
  E    ← PriceProvider.get_market_cap(ticker, period_end)
  β    ← PriceProvider.get_beta(ticker)
  Rf   ← PriceProvider.get_risk_free_rate(period_end)
  ERP  ← PriceProvider.get_equity_risk_premium(sic_code)
  D, Kd, t ← sec_financial_derived row (gold layer inputs)

Usage
-----
from edgar_warehouse.market.wacc import compute_wacc, WaccInputs

inputs = WaccInputs(
    ticker="AAPL",
    period_end="2023-12-31",
    sic_code="7372",
    total_debt=120_000_000_000,
    interest_expense=3_900_000_000,
    income_tax_expense=29_749_000_000,
    pretax_income=113_736_000_000,
)
result = compute_wacc(inputs, price_provider=pp)
print(result)  # {"wacc": 0.0893, ...}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WaccInputs:
    """All inputs needed to compute WACC for a single company-period."""

    ticker: str
    period_end: str           # ISO date "YYYY-MM-DD"
    sic_code: str | None = None

    # From sec_financial_derived / sec_financial_fact
    total_debt: float | None = None         # interest-bearing debt (USD)
    interest_expense: float | None = None   # USD, absolute value
    income_tax_expense: float | None = None # USD
    pretax_income: float | None = None      # USD (before tax, before interest)

    # Optional override: skip PriceProvider calls
    market_cap_override: float | None = None
    beta_override: float | None = None
    risk_free_rate_override: float | None = None
    erp_override: float | None = None


@dataclass
class WaccResult:
    """Output of ``compute_wacc``."""

    wacc: float | None = None              # decimal (e.g. 0.089 for 8.9%)
    cost_of_equity: float | None = None    # Ke
    cost_of_debt: float | None = None      # Kd (pre-tax)
    cost_of_debt_aftertax: float | None = None  # Kd × (1-t)
    equity_weight: float | None = None     # E/V
    debt_weight: float | None = None       # D/V
    beta: float | None = None
    risk_free_rate: float | None = None
    equity_risk_premium: float | None = None
    effective_tax_rate: float | None = None
    market_cap: float | None = None
    total_debt_used: float | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "wacc": self.wacc,
            "cost_of_equity": self.cost_of_equity,
            "cost_of_debt_aftertax": self.cost_of_debt_aftertax,
            "equity_weight": self.equity_weight,
            "debt_weight": self.debt_weight,
            "beta": self.beta,
            "risk_free_rate": self.risk_free_rate,
            "equity_risk_premium": self.equity_risk_premium,
            "effective_tax_rate": self.effective_tax_rate,
            "market_cap": self.market_cap,
        }
        if self.warnings:
            d["warnings"] = self.warnings
        return d


def compute_wacc(inputs: WaccInputs, price_provider: Any = None) -> WaccResult:
    """Compute WACC for one company-period.

    Parameters
    ----------
    inputs:
        All financial and market data inputs (see ``WaccInputs``).
    price_provider:
        An instance of ``edgar_warehouse.market.price_provider.PriceProvider``.
        If None, only override values are used (all market data becomes None).

    Returns
    -------
    WaccResult with computed WACC and component breakdowns.  Individual
    components may be None when data is unavailable; ``wacc`` is None if
    equity weight cannot be determined.
    """
    result = WaccResult()

    # ── 1. Market cap (E) ───────────────────────────────────────────────────
    if inputs.market_cap_override is not None:
        result.market_cap = inputs.market_cap_override
    elif price_provider is not None:
        result.market_cap = price_provider.get_market_cap(inputs.ticker, inputs.period_end)

    if result.market_cap is None or result.market_cap <= 0:
        result.warnings.append("market_cap unavailable — wacc cannot be computed")
        return result

    # ── 2. Total debt (D) ───────────────────────────────────────────────────
    result.total_debt_used = inputs.total_debt if inputs.total_debt is not None else 0.0

    # ── 3. Weights ──────────────────────────────────────────────────────────
    E = result.market_cap
    D = result.total_debt_used
    V = E + D
    if V <= 0:
        result.warnings.append("V = E + D = 0 — cannot compute weights")
        return result

    result.equity_weight = E / V
    result.debt_weight = D / V

    # ── 4. Beta ─────────────────────────────────────────────────────────────
    if inputs.beta_override is not None:
        result.beta = inputs.beta_override
    elif price_provider is not None:
        result.beta = price_provider.get_beta(inputs.ticker)

    if result.beta is None:
        result.beta = 1.0  # unlevered market beta fallback
        result.warnings.append("beta unavailable — using 1.0 (market beta)")

    # ── 5. Risk-free rate ───────────────────────────────────────────────────
    if inputs.risk_free_rate_override is not None:
        result.risk_free_rate = inputs.risk_free_rate_override
    elif price_provider is not None:
        result.risk_free_rate = price_provider.get_risk_free_rate(inputs.period_end)

    if result.risk_free_rate is None:
        result.risk_free_rate = 0.04  # 4% fallback (long-run average)
        result.warnings.append("risk_free_rate unavailable — using 4.0% fallback")

    # ── 6. Equity risk premium ──────────────────────────────────────────────
    if inputs.erp_override is not None:
        result.equity_risk_premium = inputs.erp_override
    elif price_provider is not None:
        result.equity_risk_premium = price_provider.get_equity_risk_premium(inputs.sic_code)
    else:
        result.equity_risk_premium = 0.057  # Damodaran 2025 default

    # ── 7. Cost of equity (CAPM) ────────────────────────────────────────────
    result.cost_of_equity = (
        result.risk_free_rate + result.beta * result.equity_risk_premium
    )

    # ── 8. Cost of debt ─────────────────────────────────────────────────────
    if (
        inputs.interest_expense is not None
        and inputs.total_debt is not None
        and inputs.total_debt > 0
    ):
        result.cost_of_debt = abs(inputs.interest_expense) / inputs.total_debt
    else:
        result.cost_of_debt = None

    # ── 9. Effective tax rate ───────────────────────────────────────────────
    if (
        inputs.income_tax_expense is not None
        and inputs.pretax_income is not None
        and inputs.pretax_income > 0
    ):
        result.effective_tax_rate = min(
            inputs.income_tax_expense / inputs.pretax_income, 0.40
        )
    else:
        result.effective_tax_rate = 0.21  # US federal statutory rate fallback
        if D > 0:
            result.warnings.append("effective_tax_rate unavailable — using 21% statutory")

    # ── 10. After-tax cost of debt ──────────────────────────────────────────
    if result.cost_of_debt is not None:
        result.cost_of_debt_aftertax = result.cost_of_debt * (1.0 - result.effective_tax_rate)
    else:
        result.cost_of_debt_aftertax = None

    # ── 11. WACC ────────────────────────────────────────────────────────────
    wacc = result.equity_weight * result.cost_of_equity
    if result.cost_of_debt_aftertax is not None and result.debt_weight and result.debt_weight > 0:
        wacc += result.debt_weight * result.cost_of_debt_aftertax

    result.wacc = round(wacc, 6)
    return result
