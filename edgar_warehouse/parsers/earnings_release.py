"""8-K earnings release parser — backed by edgartools' EarningsRelease.

This parser delegates structured table extraction (scale detection, statement
classification, label normalisation, period-column selection) to edgartools'
``EarningsRelease`` class.  We do NOT call ``EarningsRelease.from_filing()``
because it triggers an SEC HTTP fetch via ``filing.attachments`` lookup; the
bronze-replay architecture (artifacts already cached in S3) requires we feed
the already-fetched HTML content directly.

Writes to ``sec_earnings_release`` in the fundamentals silver namespace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PARSER_NAME = "earnings_release_v2"
PARSER_VERSION = "2"


# WHY-STUB: bronze-replay architecture caches filing artifacts in S3.  Using
# EarningsRelease.from_filing(filing) would force a re-fetch via SEC HTTP for
# every 8-K (~76k cohort = ~10h of avoidable re-fetch + rate-limit risk).  We
# feed cached bytes via a minimal Attachment stub instead.  The stub exposes
# only the two fields EarningsRelease reads on the document path
# (edgar/earnings.py:976-1009): ``content`` and ``document``.
@dataclass
class _BronzeAttachment:
    """Minimal Attachment-shaped object for cached HTML bytes."""

    content: str
    document: str = "earnings-release.htm"


def parse_earnings_release(
    accession_number: str,
    content: str,
    form_type: str,
    cik: int,
    filing_date: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Parse an 8-K primary document into a ``sec_earnings_release`` row.

    Returns ``{"sec_earnings_release": []}`` when the document is not an
    earnings release (no income statement extractable from the HTML).

    Parameters
    ----------
    accession_number:
        Accession number of the 8-K filing.
    content:
        Raw HTML of the primary 8-K document (or EX-99.1 exhibit, when the
        orchestrator can isolate it).  edgartools' ``EarningsRelease`` reads
        only the HTML it is given — no further fetching occurs.
    form_type:
        Form type ("8-K" or "8-K/A").
    cik:
        CIK of the reporting company.
    filing_date:
        ISO date string (YYYY-MM-DD) used as a fiscal_year fallback when the
        document does not contain a parseable period header.
    """
    if not content:
        return {"sec_earnings_release": []}

    try:
        from edgar.earnings import EarningsRelease, _parse_period_header
    except ImportError:
        logger.warning("edgartools EarningsRelease not available; returning empty")
        return {"sec_earnings_release": []}

    try:
        er = EarningsRelease(_BronzeAttachment(content=content))
    except Exception as exc:
        logger.debug("EarningsRelease construction failed for %s: %s", accession_number, exc)
        return {"sec_earnings_release": []}

    # Probe income statement — if absent, the document is not an earnings release
    try:
        inc = er.income_statement
    except Exception as exc:
        logger.debug("income_statement access failed for %s: %s", accession_number, exc)
        return {"sec_earnings_release": []}
    if inc is None or inc.dataframe.empty:
        return {"sec_earnings_release": []}

    try:
        metrics = er.get_key_metrics(quarterly=True)
    except Exception as exc:
        logger.debug("get_key_metrics failed for %s: %s", accession_number, exc)
        return {"sec_earnings_release": []}

    period_str = metrics.get("period") or ""
    try:
        period_info = _parse_period_header(period_str) if period_str else {}
    except Exception:
        period_info = {}

    fiscal_year = period_info.get("fiscal_year")
    if fiscal_year is None and filing_date:
        try:
            fiscal_year = int(str(filing_date)[:4])
        except (ValueError, TypeError):
            pass

    # Probe optional tables — exceptions during access mean "absent", not "fatal"
    try:
        has_non_gaap = er.eps_reconciliation is not None
    except Exception:
        has_non_gaap = False
    try:
        has_guidance = er.guidance is not None
    except Exception:
        has_guidance = False

    row = {
        "cik": int(cik),
        "accession_number": accession_number,
        "filing_date": filing_date,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": _fiscal_period_to_quarter(period_info.get("fiscal_period")),
        "period_end": period_info.get("period_end"),
        "revenue_gaap": _to_float(metrics.get("revenue")),
        "net_income_gaap": _to_float(metrics.get("net_income")),
        "eps_gaap_diluted": _to_float(metrics.get("eps_diluted")),
        "has_non_gaap": has_non_gaap,
        "has_guidance": has_guidance,
        "parser_version": PARSER_VERSION,
    }

    return {"sec_earnings_release": [row]}


def _fiscal_period_to_quarter(fp: Any) -> int | None:
    """Map edgartools' fiscal_period string ('Q1'..'Q4', 'FY') to integer 1-4 or None."""
    if not fp:
        return None
    return {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(str(fp).upper())


def _to_float(value: Any) -> float | None:
    """Best-effort numeric coercion."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
