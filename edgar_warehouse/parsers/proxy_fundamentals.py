"""DEF 14A proxy parser adapter — extracts executive compensation records.

Backed by edgartools' ``extract_summary_compensation`` DOM-based extractor.
Writes to ``sec_executive_record`` in the fundamentals silver namespace.

Architecture note
-----------------
This parser fits the standard per-filing dispatch via ``get_parser()``.
The ``content`` argument is the raw HTML of the primary DEF 14A document.

Person identity and tenure are NOT written to silver — they are computed
downstream by MDM's ``_derive_employed_by`` and stored on the EMPLOYED_BY
relationship instance, not denormalised to silver.
"""

from __future__ import annotations

from typing import Any

PARSER_NAME = "proxy_fundamentals_v1"
PARSER_VERSION = "1"

# Standardised role codes inferred from raw title strings
_ROLE_MAP = {
    "chief executive officer": "CEO",
    "president and chief executive officer": "CEO",
    "co-chief executive officer": "Co-CEO",
    "chief financial officer": "CFO",
    "chief operating officer": "COO",
    "chief technology officer": "CTO",
    "chief legal officer": "CLO",
    "chief accounting officer": "CAO",
    "general counsel": "General Counsel",
    "executive vice president": "EVP",
    "senior vice president": "SVP",
    "vice president": "VP",
    "principal executive officer": "PEO",
    "principal financial officer": "PFO",
    "executive chairman": "Executive Chairman",
    "chairman": "Chairman",
    "president": "President",
}


def _infer_role(title: str | None) -> str | None:
    """Map a raw proxy title string to a standardised role code."""
    if not title:
        return None
    lower = title.lower().strip()
    for phrase, code in _ROLE_MAP.items():
        if phrase in lower:
            return code
    return None


def parse_proxy_fundamentals(
    accession_number: str,
    content: str,
    form_type: str,
    cik: int,
) -> dict[str, list[dict[str, Any]]]:
    """Parse a DEF 14A HTML document into ``sec_executive_record`` rows.

    Parameters
    ----------
    accession_number:
        Accession number of the DEF 14A filing.
    content:
        Raw HTML string of the primary DEF 14A document.
    form_type:
        Form type (DEF 14A, DEF 14A/A, etc.) — stored for audit trail.
    cik:
        CIK of the issuer company.

    Returns
    -------
    dict with key ``"sec_executive_record"`` → list of row dicts.
    Returns ``{"sec_executive_record": []}`` when no SCT is found.
    """
    try:
        from lxml import html as lxml_html
        from edgar.proxy.html_extractor import extract_summary_compensation
    except ImportError:
        return {"sec_executive_record": []}

    # Parse HTML — suppress lxml noise from malformed proxy HTML
    try:
        tree = lxml_html.fromstring(content.encode("utf-8", errors="replace"))
    except Exception:
        return {"sec_executive_record": []}

    try:
        entries = extract_summary_compensation(tree)
    except Exception:
        return {"sec_executive_record": []}

    if not entries:
        return {"sec_executive_record": []}

    rows: list[dict[str, Any]] = []
    for entry in entries:
        raw_title = getattr(entry, "title", None) or ""
        rows.append(
            {
                "cik": int(cik),
                "accession_number": accession_number,
                "fiscal_year": int(entry.year) if entry.year else None,
                "exec_name": str(entry.name).strip() if entry.name else None,
                "exec_role": _infer_role(raw_title) or (raw_title[:200] if raw_title else None),
                "total_comp": _int_to_float(entry.total),
                "base_salary": _int_to_float(entry.salary),
                "bonus": _int_to_float(entry.bonus),
                "stock_awards": _int_to_float(entry.stock_awards),
                "option_awards": _int_to_float(entry.option_awards),
                "non_equity_incentive": _int_to_float(entry.non_equity_incentive),
                "parser_version": PARSER_VERSION,
            }
        )

    return {"sec_executive_record": rows}


def _int_to_float(value: int | None) -> float | None:
    """Convert an Optional[int] compensation value to Optional[float]."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
