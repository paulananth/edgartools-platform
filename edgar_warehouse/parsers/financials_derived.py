"""Derived financial metrics parser — computes sec_financial_derived from sec_financial_fact rows.

# WHY-CUSTOM: derived second-derivative metrics (EBITDA, FCF, gross/EBITDA/net
# margins, ROIC/ROE/ROA) computed from us-gaap concept facts.  These are
# computations *over* extracted facts, not extractions of them — edgartools
# (correctly) does not provide pre-computed derivatives because they are
# downstream of fact selection (which concept counts as "revenue" varies per
# company), and the derivation choices are research decisions.

Architecture note
-----------------
This parser is NOT in the per-filing dispatch (``get_parser()``).  The orchestrator
calls ``compute_derived_for_accession()`` once per (cik, accession_number) after all
raw facts for that accession have been written to sec_financial_fact.

Concept mapping
---------------
The SEC XBRL taxonomy uses hundreds of overlapping concept names.  This module
resolves a canonical set of ~20 financial statement line items by checking an
ordered preference list for each metric.  First non-null value wins.

Forensic scores
---------------
Beneish M / Altman Z / Piotroski F live exclusively on sec_accounting_flag,
computed by ``accounting_flags.backfill_accounting_flags`` after the full
fiscal-year history is loaded.  They are NOT denormalised to per-quarter rows
here because they are annual constructs.
"""

from __future__ import annotations

from typing import Any

PARSER_NAME = "financials_derived_v1"
PARSER_VERSION = "1"

# ---------------------------------------------------------------------------
# Concept priority maps — first matching concept with a non-null value wins
# ---------------------------------------------------------------------------

_REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomer",
    "Revenues",
    "TotalRevenues",
]

_GROSS_PROFIT_CONCEPTS = [
    "GrossProfit",
]

_OPERATING_INCOME_CONCEPTS = [
    "OperatingIncomeLoss",
]

_NET_INCOME_CONCEPTS = [
    "NetIncomeLoss",
    "ProfitLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
]

_EPS_DILUTED_CONCEPTS = [
    "EarningsPerShareDiluted",
    "IncomeLossFromContinuingOperationsPerDilutedShare",
]

_TOTAL_ASSETS_CONCEPTS = [
    "Assets",
]

_TOTAL_LIABILITIES_CONCEPTS = [
    "Liabilities",
    "LiabilitiesAndStockholdersEquity",  # fallback only if Liabilities absent
]

_TOTAL_EQUITY_CONCEPTS = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "PartnersCapital",
]

_CASH_CONCEPTS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsAndShortTermInvestments",
    "Cash",
]

_TOTAL_DEBT_LONG_CONCEPTS = [
    "LongTermDebtNoncurrent",
    "LongTermDebt",
    "LongTermNotesPayable",
]

_TOTAL_DEBT_SHORT_CONCEPTS = [
    "ShortTermBorrowings",
    "NotesPayableCurrent",
    "CurrentPortionOfLongTermDebt",
    "LineOfCreditFacilityRemainingBorrowingCapacity",
]

_DA_CONCEPTS = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "Depreciation",
]

_OCF_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
]

_CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "CapitalExpenditureDiscontinuedOperations",
    "PaymentsForCapitalImprovements",
]

_RETAINED_EARNINGS_CONCEPTS = [
    "RetainedEarningsAccumulatedDeficit",
]

_CURRENT_ASSETS_CONCEPTS = [
    "AssetsCurrent",
]

_CURRENT_LIABILITIES_CONCEPTS = [
    "LiabilitiesCurrent",
]

_RECEIVABLES_CONCEPTS = [
    "AccountsReceivableNetCurrent",
    "ReceivablesNetCurrent",
]

_INVENTORY_CONCEPTS = [
    "InventoryNet",
    "Inventories",
]

_SGA_CONCEPTS = [
    "SellingGeneralAndAdministrativeExpense",
    "GeneralAndAdministrativeExpense",
]

_PPE_NET_CONCEPTS = [
    "PropertyPlantAndEquipmentNet",
    "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
    "PropertyPlantAndEquipmentIncludingFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
]

_SHARES_OUTSTANDING_CONCEPTS = [
    "CommonStockSharesOutstanding",
    "CommonStockSharesIssued",
]


def _pick(fact_map: dict[str, float | None], concepts: list[str]) -> float | None:
    """Return the first non-None value from the ordered concept preference list."""
    for concept in concepts:
        val = fact_map.get(concept)
        if val is not None:
            return val
    return None


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def compute_derived_for_accession(
    cik: int,
    accession_number: str,
    fiscal_year: int | None,
    fiscal_period: str,
    period_end: str | None,
    form_type: str,
    fact_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Compute derived financial metrics for one (cik, accession, fiscal_period).

    Parameters
    ----------
    cik:
        Company CIK.
    accession_number:
        Accession number for the filing.
    fiscal_year:
        Fiscal year (e.g. 2023).
    fiscal_period:
        FY / Q1 / Q2 / Q3 / Q4.
    period_end:
        Period end date string (YYYY-MM-DD).
    form_type:
        10-K / 10-Q / 20-F / etc.
    fact_rows:
        List of sec_financial_fact rows for this (cik, accession, fiscal_period).
        Each row must have at least ``concept`` and ``value`` keys.

    Returns
    -------
    dict with key ``"sec_financial_derived"`` → list containing zero or one row dict.
    Returns empty list if no facts can be mapped.
    """
    if not fact_rows:
        return {"sec_financial_derived": []}

    # Build concept → value map (unit=USD preferred, then shares, then pure).
    # A single (accn, fiscal_period, period_end) group can contain BOTH a QTD
    # and a YTD row for the same duration concept (e.g. "3 months ended" vs.
    # "6 months ended", both ending on the same date) -- sec_financial_fact's
    # Stage 2 PK (silver_store.py) retains both. For a per-fiscal_period
    # derived row, prefer the QTD (incremental) value: the row with the LATEST
    # period_start, i.e. the shortest duration. Instant facts and Q1/FY rows
    # have a single period_start, so this is a no-op for them.
    fact_map: dict[str, float | None] = {}
    fact_map_starts: dict[str, str] = {}
    for row in fact_rows:
        concept = row.get("concept")
        value = row.get("value")
        start = row.get("period_start") or ""
        if concept and value is not None:
            if concept not in fact_map or start > fact_map_starts.get(concept, ""):
                fact_map[concept] = value
                fact_map_starts[concept] = start

    # ── Income statement ─────────────────────────────────────────────────────
    revenue        = _pick(fact_map, _REVENUE_CONCEPTS)
    gross_profit   = _pick(fact_map, _GROSS_PROFIT_CONCEPTS)
    ebit           = _pick(fact_map, _OPERATING_INCOME_CONCEPTS)
    da             = _pick(fact_map, _DA_CONCEPTS)
    net_income     = _pick(fact_map, _NET_INCOME_CONCEPTS)
    eps_diluted    = _pick(fact_map, _EPS_DILUTED_CONCEPTS)
    sga            = _pick(fact_map, _SGA_CONCEPTS)

    # EBITDA = EBIT + D&A  (both must be present)
    ebitda = (ebit + da) if (ebit is not None and da is not None) else None

    # ── Balance sheet ─────────────────────────────────────────────────────────
    total_assets       = _pick(fact_map, _TOTAL_ASSETS_CONCEPTS)
    total_liabilities  = _pick(fact_map, _TOTAL_LIABILITIES_CONCEPTS)
    total_equity       = _pick(fact_map, _TOTAL_EQUITY_CONCEPTS)
    cash               = _pick(fact_map, _CASH_CONCEPTS)
    lt_debt            = _pick(fact_map, _TOTAL_DEBT_LONG_CONCEPTS)
    st_debt            = _pick(fact_map, _TOTAL_DEBT_SHORT_CONCEPTS)
    total_debt: float | None = None
    if lt_debt is not None or st_debt is not None:
        total_debt = (lt_debt or 0.0) + (st_debt or 0.0)
    retained_earnings  = _pick(fact_map, _RETAINED_EARNINGS_CONCEPTS)
    current_assets     = _pick(fact_map, _CURRENT_ASSETS_CONCEPTS)
    current_liabilities = _pick(fact_map, _CURRENT_LIABILITIES_CONCEPTS)
    receivables        = _pick(fact_map, _RECEIVABLES_CONCEPTS)
    inventory          = _pick(fact_map, _INVENTORY_CONCEPTS)
    property_plant_equipment_net = _pick(fact_map, _PPE_NET_CONCEPTS)
    shares_outstanding = _pick(fact_map, _SHARES_OUTSTANDING_CONCEPTS)

    # ── Cash flow ─────────────────────────────────────────────────────────────
    ocf   = _pick(fact_map, _OCF_CONCEPTS)
    capex = _pick(fact_map, _CAPEX_CONCEPTS)
    # Capex in XBRL is typically reported as a positive outflow; FCF = OCF - |capex|
    free_cash_flow: float | None = None
    if ocf is not None and capex is not None:
        free_cash_flow = ocf - abs(capex)

    # ── Margin ratios ─────────────────────────────────────────────────────────
    gross_margin  = _safe_div(gross_profit, revenue)
    ebitda_margin = _safe_div(ebitda, revenue)
    net_margin    = _safe_div(net_income, revenue)

    # ── Return ratios ─────────────────────────────────────────────────────────
    # ROA = Net Income / Avg Assets — single-period approx uses ending assets
    roa  = _safe_div(net_income, total_assets)
    # ROE = Net Income / Total Equity
    roe  = _safe_div(net_income, total_equity)
    # ROIC = EBIT×(1-tax) / Invested Capital — simplified: EBIT / (Equity + Debt)
    invested_capital: float | None = None
    if total_equity is not None and total_debt is not None:
        invested_capital = total_equity + total_debt
    roic = _safe_div(ebit, invested_capital)

    # Forensic scores (Beneish M / Altman Z / Piotroski F) live ONLY on
    # sec_accounting_flag — they are annual constructs computed cross-period in
    # accounting_flags.backfill_accounting_flags.  Not denormalised here.

    # If no derived values could be computed, omit the row (no point writing a null row)
    non_null_count = sum(
        1 for v in [revenue, gross_profit, ebitda, net_income, total_assets]
        if v is not None
    )
    if non_null_count == 0:
        return {"sec_financial_derived": []}

    row = {
        "cik":                int(cik),
        "accession_number":   accession_number,
        "fiscal_year":        fiscal_year,
        "fiscal_period":      fiscal_period,
        "period_end":         period_end,
        "form_type":          form_type,
        "revenue":            revenue,
        "gross_profit":       gross_profit,
        "ebitda":             ebitda,
        "ebit":               ebit,
        "net_income":         net_income,
        "eps_diluted":        eps_diluted,
        "total_assets":       total_assets,
        "total_liabilities":  total_liabilities,
        "total_equity":       total_equity,
        "cash_and_equivalents": cash,
        "total_debt":         total_debt,
        "current_assets":     current_assets,
        "current_liabilities": current_liabilities,
        "accounts_receivable": receivables,
        "inventory":          inventory,
        "selling_general_admin_expense": sga,
        "retained_earnings":  retained_earnings,
        "depreciation_amortization": da,
        "property_plant_equipment_net": property_plant_equipment_net,
        "shares_outstanding": shares_outstanding,
        "operating_cash_flow": ocf,
        "capex":              capex,
        "free_cash_flow":     free_cash_flow,
        "gross_margin":       gross_margin,
        "ebitda_margin":      ebitda_margin,
        "net_margin":         net_margin,
        "roic":               roic,
        "roe":                roe,
        "roa":                roa,
        "parser_version":     PARSER_VERSION,
    }
    return {"sec_financial_derived": [row]}

