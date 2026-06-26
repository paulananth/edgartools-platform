"""Accounting flags post-processor — back-fills Beneish/Altman/Piotroski
scores into sec_accounting_flag from sec_financial_derived.

# WHY-CUSTOM: cross-period forensic scoring (Beneish M, Altman Z, Piotroski F)
# and auditor-change detection.  These are CIK-level computations across
# multiple fiscal years; edgartools (correctly) has no equivalent because the
# scoring formulas require value selection (TATA, AQI, SGI etc.) over already-
# extracted us-gaap facts.  This module is the single source of truth for
# forensic scores in the warehouse — sec_financial_derived intentionally does
# NOT carry them.

Architecture note
-----------------
This module does NOT go through the standard ``get_parser()`` per-filing dispatch.
It is a CIK-level post-processor called *after* both sec_financial_fact and
sec_financial_derived have been populated for a company.

It reads sec_financial_derived rows and sec_accounting_flag rows for a given CIK,
computes cross-period forensic scores, and writes back to sec_accounting_flag.

The cross-period Beneish model uses consecutive (FY-1, FY) fact pairs.
Altman and Piotroski improvements over single-period versions use prior-year deltas.

Usage (called by bootstrap_fundamentals orchestrator after entity-facts parse):
    from edgar_warehouse.parsers.accounting_flags import backfill_accounting_flags

    updated = backfill_accounting_flags(cik=320193, silver=db)
    # returns number of sec_accounting_flag rows updated
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

PARSER_NAME = "accounting_flags_v1"
PARSER_VERSION = "1"

if TYPE_CHECKING:
    from edgar_warehouse.silver_store import SilverDatabase


def backfill_accounting_flags(cik: int, silver: "SilverDatabase") -> int:
    """Back-fill forensic scores for all annual filings of one company.

    Reads sec_financial_derived FY rows for the CIK ordered by fiscal_year,
    then computes cross-period Beneish, Altman (with prior-year deltas), and
    full Piotroski F-score (9 signals) and upserts into sec_accounting_flag.

    Returns the number of sec_accounting_flag rows updated.
    """
    derived_rows: list[dict[str, Any]] = silver.fetch(
        """
        SELECT accession_number, fiscal_year, period_end, form_type,
               revenue, gross_profit, ebitda, ebit, net_income, eps_diluted,
               total_assets, total_liabilities, total_equity, cash_and_equivalents,
               total_debt, current_assets, current_liabilities, accounts_receivable,
               inventory, selling_general_admin_expense, retained_earnings,
               depreciation_amortization, property_plant_equipment_net,
               shares_outstanding, operating_cash_flow, capex, free_cash_flow,
               gross_margin, ebitda_margin, net_margin, roic, roe, roa
        FROM sec_financial_derived
        WHERE cik = ? AND fiscal_period = 'FY'
        ORDER BY fiscal_year
        """,
        [int(cik)],
    )

    if not derived_rows:
        return 0

    updated = 0
    prev: dict[str, Any] | None = None

    for row in derived_rows:
        accession = row["accession_number"]
        fiscal_year = row["fiscal_year"]

        # ── Cross-period Beneish (uses current + prior year) ─────────────────
        beneish = _beneish_cross_period(row, prev)

        # ── Enhanced Altman with prior-year delta signals ─────────────────────
        altman = _altman_enhanced(row, prev)

        # ── Full Piotroski (9 signals with prior-year deltas) ─────────────────
        piotroski = _piotroski_full(row, prev)

        # ── Auditor change detection ──────────────────────────────────────────
        # (auditor_changed is already set by the financials.py parser via DEI facts;
        # we don't overwrite it here — only set forensic scores)

        # update_accounting_flag_scores COALESCEs None against the existing
        # sec_accounting_flag value, so a None here (e.g. no prior year for
        # Beneish on the earliest fiscal year) leaves any previously-computed
        # score untouched rather than clobbering it.
        try:
            silver.update_accounting_flag_scores(
                cik=int(cik),
                accession_number=accession,
                beneish_m_score=beneish,
                altman_z_score=altman,
                piotroski_f_score=piotroski,
            )
            updated += 1
        except Exception:
            pass  # Row may not exist yet; orchestrator writes it after entity-facts parse

        prev = row

    return updated


# ---------------------------------------------------------------------------
# Cross-period score computations
# ---------------------------------------------------------------------------

def _safe_div(num: float | None, denom: float | None) -> float | None:
    if num is None or denom is None or denom == 0:
        return None
    return num / denom


def _beneish_cross_period(
    curr: dict[str, Any],
    prev: dict[str, Any] | None,
) -> float | None:
    """Full 8-variable Beneish M-score (requires two consecutive fiscal years).

    Returns None if prior year is unavailable (falls back to single-period in caller).
    """
    if prev is None:
        return None

    def g(row: dict, k: str) -> float | None:
        return row.get(k)

    rev_c  = g(curr, "revenue");      rev_p  = g(prev, "revenue")
    gp_c   = g(curr, "gross_profit"); gp_p   = g(prev, "gross_profit")
    ta_c   = g(curr, "total_assets"); ta_p   = g(prev, "total_assets")
    ni_c   = g(curr, "net_income");   ocf_c  = g(curr, "operating_cash_flow")
    ar_c   = g(curr, "accounts_receivable"); ar_p = g(prev, "accounts_receivable")
    sga_c  = g(curr, "selling_general_admin_expense"); sga_p = g(prev, "selling_general_admin_expense")
    da_c   = g(curr, "depreciation_amortization"); da_p = g(prev, "depreciation_amortization")
    ca_c   = g(curr, "current_assets"); ca_p = g(prev, "current_assets")
    ppe_c  = g(curr, "property_plant_equipment_net"); ppe_p = g(prev, "property_plant_equipment_net")

    # DSRI = (Receivables_t / Revenue_t) / (Receivables_t-1 / Revenue_t-1)
    dsri = _safe_div(_safe_div(ar_c, rev_c), _safe_div(ar_p, rev_p))

    # GMI = Gross Margin t-1 / Gross Margin t
    gm_c = _safe_div(gp_c, rev_c)
    gm_p = _safe_div(gp_p, rev_p)
    gmi  = _safe_div(gm_p, gm_c)

    # AQI = [1 - (CurrentAssets_t + PPE_t) / TA_t] /
    #       [1 - (CurrentAssets_t-1 + PPE_t-1) / TA_t-1]
    asset_quality_c: float | None = None
    asset_quality_p: float | None = None
    if ca_c is not None and ppe_c is not None:
        current_ppe_to_assets_c = _safe_div(ca_c + ppe_c, ta_c)
        if current_ppe_to_assets_c is not None:
            asset_quality_c = 1 - current_ppe_to_assets_c
    if ca_p is not None and ppe_p is not None:
        current_ppe_to_assets_p = _safe_div(ca_p + ppe_p, ta_p)
        if current_ppe_to_assets_p is not None:
            asset_quality_p = 1 - current_ppe_to_assets_p
    aqi = _safe_div(asset_quality_c, asset_quality_p)

    # SGI = Revenue_t / Revenue_t-1
    sgi = _safe_div(rev_c, rev_p)

    # DEPI = [Dep_t-1 / (Dep_t-1 + PPE_t-1)] / [Dep_t / (Dep_t + PPE_t)]
    depi = _safe_div(
        _safe_div(da_p, (da_p + ppe_p) if da_p is not None and ppe_p is not None else None),
        _safe_div(da_c, (da_c + ppe_c) if da_c is not None and ppe_c is not None else None),
    )

    # SGAI = (SGA_t / Revenue_t) / (SGA_t-1 / Revenue_t-1)
    sgai = _safe_div(_safe_div(sga_c, rev_c), _safe_div(sga_p, rev_p))

    # LVGI = (LT_Debt_t / TA_t) / (LT_Debt_t-1 / TA_t-1)
    ltd_c = g(curr, "total_debt"); ltd_p = g(prev, "total_debt")
    lev_c = _safe_div(ltd_c, ta_c); lev_p = _safe_div(ltd_p, ta_p)
    lvgi  = _safe_div(lev_c, lev_p)

    # TATA = (Net Income - CFO) / Total Assets
    tata: float | None = None
    if ni_c is not None and ocf_c is not None:
        tata = _safe_div(ni_c - ocf_c, ta_c)

    available = sum(1 for v in [dsri, gmi, aqi, sgi, depi, sgai, lvgi, tata] if v is not None)
    if available < 2:
        return None

    m = -4.84
    if dsri  is not None: m += 0.920 * dsri
    if gmi   is not None: m += 0.528 * gmi
    if aqi   is not None: m += 0.404 * aqi
    if sgi   is not None: m += 0.892 * sgi
    if depi  is not None: m += 0.115 * depi
    if sgai  is not None: m -= 0.172 * sgai
    if lvgi  is not None: m -= 0.327 * lvgi
    if tata  is not None: m += 4.679 * tata

    return round(m, 4)


def _altman_enhanced(
    curr: dict[str, Any],
    prev: dict[str, Any] | None,
) -> float | None:
    """Altman Z-score (same formula as single-period; using updated book equity)."""
    ta = curr.get("total_assets")
    if not ta:
        return None

    def x(k: str) -> float | None:
        return curr.get(k)

    rev = x("revenue")
    current_assets = x("current_assets")
    current_liabilities = x("current_liabilities")
    re  = x("retained_earnings")
    ebit = x("ebit")
    eq  = x("total_equity")
    tl  = x("total_liabilities")

    working_capital: float | None = None
    if current_assets is not None and current_liabilities is not None:
        working_capital = current_assets - current_liabilities
    x1 = _safe_div(working_capital, ta)
    x2 = _safe_div(re, ta)
    x3 = _safe_div(ebit, ta)
    x4 = _safe_div(eq, tl) if tl else None
    x5 = _safe_div(rev, ta)

    available = sum(1 for v in [x1, x2, x3, x4, x5] if v is not None)
    if available < 2:
        return None

    z = 0.0
    if x1 is not None: z += 1.2 * x1
    if x2 is not None: z += 1.4 * x2
    if x3 is not None: z += 3.3 * x3
    if x4 is not None: z += 0.6 * x4
    if x5 is not None: z += 1.0 * x5

    return round(z, 4)


def _piotroski_full(
    curr: dict[str, Any],
    prev: dict[str, Any] | None,
) -> int | None:
    """Piotroski F-score with cross-period signals where prior year available."""
    ta_c = curr.get("total_assets")
    ni_c = curr.get("net_income")
    ocf_c = curr.get("operating_cash_flow")
    ltd_c = curr.get("total_debt")
    gm_c = curr.get("gross_margin")
    rev_c = curr.get("revenue")
    current_assets_c = curr.get("current_assets")
    current_liabilities_c = curr.get("current_liabilities")
    shares_c = curr.get("shares_outstanding")

    signals: list[int] = []

    # F1: ROA > 0
    if ni_c is not None and ta_c:
        signals.append(1 if ni_c / ta_c > 0 else 0)

    # F2: CFO > 0
    if ocf_c is not None:
        signals.append(1 if ocf_c > 0 else 0)

    # F3: ΔROA > 0 (requires prior year)
    if prev is not None:
        roa_c = _safe_div(ni_c, ta_c)
        roa_p = _safe_div(prev.get("net_income"), prev.get("total_assets"))
        if roa_c is not None and roa_p is not None:
            signals.append(1 if roa_c > roa_p else 0)

    # F4: CFO > Net Income
    if ocf_c is not None and ni_c is not None:
        signals.append(1 if ocf_c > ni_c else 0)

    # F5: ΔLeverage < 0 (requires prior year)
    if prev is not None and ta_c:
        lev_c = _safe_div(ltd_c, ta_c)
        lev_p = _safe_div(prev.get("total_debt"), prev.get("total_assets"))
        if lev_c is not None and lev_p is not None:
            signals.append(1 if lev_c < lev_p else 0)

    # F6: ΔLiquidity (current ratio) > 0 (requires prior year)
    if prev is not None:
        cr_c = _safe_div(current_assets_c, current_liabilities_c)
        cr_p = _safe_div(prev.get("current_assets"), prev.get("current_liabilities"))
        if cr_c is not None and cr_p is not None:
            signals.append(1 if cr_c > cr_p else 0)

    # F7: No new shares (shares outstanding did not increase)
    if prev is not None:
        shares_p = prev.get("shares_outstanding")
        if shares_c is not None and shares_p is not None:
            signals.append(1 if shares_c <= shares_p else 0)

    # F8: ΔGross Margin > 0 (requires prior year)
    if prev is not None:
        gm_p = prev.get("gross_margin")
        if gm_c is not None and gm_p is not None:
            signals.append(1 if gm_c > gm_p else 0)

    # F9: ΔAsset Turnover > 0 (requires prior year)
    if prev is not None and ta_c:
        at_c = _safe_div(rev_c, ta_c)
        at_p = _safe_div(prev.get("revenue"), prev.get("total_assets"))
        if at_c is not None and at_p is not None:
            signals.append(1 if at_c > at_p else 0)

    if not signals:
        return None
    return sum(signals)
