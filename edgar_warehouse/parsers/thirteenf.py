"""13F-HR parser adapter — backed by edgartools' parse_infotable_xml.

Architecture note
-----------------
This parser does NOT go through the standard ``get_parser()`` per-filing dispatch.
The primary artifact for a 13F-HR filing is the *cover* XML; the holdings data
lives in a separate ``INFORMATION TABLE.xml`` attachment.  The orchestrator is
responsible for locating and passing that attachment content here as
``infotable_xml``.

Usage
-----
    from edgar_warehouse.parsers.thirteenf import parse_thirteenf

    rows = parse_thirteenf(
        infotable_xml=infotable_str,
        cik=1234567,
        accession_number="0001234567-24-000001",
        period_of_report="2024-03-31",
    )
    # rows == {"sec_thirteenf_holding": [...]}
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

PARSER_NAME = "thirteenf_v1"
PARSER_VERSION = "1"

# SEC changed 13F value units around Q4 2022:
# filings with period_of_report on or before this date report <value> in thousands.
_THOUSANDS_CUTOFF = date(2022, 9, 30)

# Security classification keyword patterns (applied to titleOfClass / security_title)
_FIXED_INCOME_RE = re.compile(
    r"\b(note|notes|bond|bonds|deb|debenture|sr\.?\s+note|senior\s+note)\b", re.I
)
_ETF_FUND_RE = re.compile(
    r"\b(etf|fund|trust|tr\s+unit|trust\s+unit|index\s+fund|spdr|ishare)\b", re.I
)
_WARRANT_RE = re.compile(r"\b(wt|warr|warrant|warrants)\b", re.I)


def _classify_security(ticker: str | None, security_title: str | None) -> str:
    """Return security_class enum value for a 13F holding row.

    Priority:
    1. ticker present (from cusip_ticker_mapping)  → 'equity'
    2. security_title matches fixed-income pattern → 'fixed_income'
    3. security_title matches ETF/fund pattern     → 'etf_fund'
    4. security_title matches warrant pattern      → 'warrant'
    5. fallback                                    → 'unknown_security'
    """
    if ticker and str(ticker).strip() not in ("", "nan", "None"):
        return "equity"
    title = security_title or ""
    if _FIXED_INCOME_RE.search(title):
        return "fixed_income"
    if _ETF_FUND_RE.search(title):
        return "etf_fund"
    if _WARRANT_RE.search(title):
        return "warrant"
    return "unknown_security"


def _parse_period(period_of_report: str) -> date:
    """Parse 'YYYY-MM-DD' or 'YYYY/MM/DD' to a date object."""
    clean = period_of_report.strip().replace("/", "-")
    return date.fromisoformat(clean[:10])


def parse_thirteenf(
    infotable_xml: str,
    cik: int,
    accession_number: str,
    period_of_report: str,
) -> dict[str, list[dict[str, Any]]]:
    """Parse a 13F-HR information table XML into ``sec_thirteenf_holding`` rows.

    Parameters
    ----------
    infotable_xml:
        Raw XML string of the INFORMATION TABLE attachment.
    cik:
        CIK of the filing manager.
    accession_number:
        Accession number of the 13F-HR filing.
    period_of_report:
        Quarter-end date string (YYYY-MM-DD).  Used both for the row value
        and to determine whether value units need ×1000 normalisation.

    Returns
    -------
    dict with key ``"sec_thirteenf_holding"`` mapping to a list of row dicts.
    Returns ``{"sec_thirteenf_holding": []}`` on parse failure.
    """
    from edgar.thirteenf.parsers.infotable_xml import parse_infotable_xml

    try:
        df = parse_infotable_xml(infotable_xml)
    except Exception:
        return {"sec_thirteenf_holding": []}

    if df is None or df.empty:
        return {"sec_thirteenf_holding": []}

    try:
        period_date = _parse_period(period_of_report)
    except (ValueError, AttributeError):
        period_date = None

    # Normalise values from thousands to dollars for pre-Q4 2022 filings
    value_multiplier = 1000 if (period_date and period_date <= _THOUSANDS_CUTOFF) else 1

    rows: list[dict[str, Any]] = []
    for holding_index, row in enumerate(df.itertuples(index=False), start=1):
        raw_value = getattr(row, "Value", None)
        market_value: float | None = None
        if raw_value is not None:
            try:
                market_value = float(raw_value) * value_multiplier
            except (TypeError, ValueError):
                market_value = None

        shares_held: float | None = None
        raw_shares = getattr(row, "SharesPrnAmount", None)
        if raw_shares is not None:
            try:
                shares_held = float(raw_shares)
            except (TypeError, ValueError):
                shares_held = None

        cusip = _str_or_none(getattr(row, "Cusip", None))
        security_title = _str_or_none(getattr(row, "Class", None))
        ticker = _str_or_none(getattr(row, "Ticker", None))

        rows.append(
            {
                "cik": int(cik),
                "accession_number": accession_number,
                "holding_index": holding_index,
                "period_of_report": str(period_date) if period_date else period_of_report,
                "cusip": cusip,
                "issuer_name": _str_or_none(getattr(row, "Issuer", None)),
                "security_title": security_title,
                "shares_held": shares_held,
                "market_value": market_value,
                "security_class": _classify_security(ticker, security_title),
                "put_call": _str_or_none(getattr(row, "PutCall", None)),
                "discretion_type": _str_or_none(getattr(row, "InvestmentDiscretion", None)),
                "voting_auth_sole": _float_or_none(getattr(row, "SoleVoting", None)),
                "voting_auth_shared": _float_or_none(getattr(row, "SharedVoting", None)),
                "voting_auth_none": _float_or_none(getattr(row, "NonVoting", None)),
                "parser_version": PARSER_VERSION,
            }
        )

    return {"sec_thirteenf_holding": rows}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s and s.lower() not in ("nan", "none", "") else None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
