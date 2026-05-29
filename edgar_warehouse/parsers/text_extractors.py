"""Text-based extraction utilities for SEC filing prose.

# WHY-CUSTOM: text-signal extraction from prose disclosures (customer
# concentration percentages, DAU/MAU and other engagement metrics, segment
# revenue mentions, employee headcount).  edgartools has no regex/NLP
# extractors for free-text disclosures — XBRL covers structured data, this
# module covers the unstructured prose that complements it.

Lightweight regex extractors for signals that cannot be derived from structured
XBRL data.  All functions operate on pre-processed plain-text strings (HTML
tags already stripped).

Extractors
----------
extract_customer_concentration  — top-customer revenue concentration disclosures
extract_user_metrics            — DAU, MAU, paid subscribers, GMV
extract_segment_revenue         — operating segment revenue breakdowns
extract_headcount               — employee headcount disclosures

These are intentionally shallow v1 extractors: correctness is served better by
accepting some nulls than by over-parsing heterogeneous 10-K prose.  The results
land in ``sec_financial_fact`` via the ``text_signal`` concept namespace so they
can coexist with structured XBRL facts.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scale(raw: str, unit: str | None) -> float | None:
    """Parse a raw number string and optional scale word → float USD or count."""
    try:
        value = float(raw.replace(",", ""))
    except (ValueError, TypeError):
        return None
    if not unit:
        return value
    u = unit.lower()
    if u in ("billion", "b"):
        return value * 1e9
    if u in ("million", "m"):
        return value * 1e6
    if u in ("thousand", "k"):
        return value * 1e3
    return value


_UNIT_GROUP = r"(billion|million|thousand|B|M|K)?"


# ---------------------------------------------------------------------------
# 1. Customer concentration
# ---------------------------------------------------------------------------
# Matches patterns like:
#   "Customer A accounted for 32% of our net revenue"
#   "one customer represented approximately 28 percent of total revenues"
#   "no customer accounted for more than 10% of net sales"

_CUSTOMER_PCT_RE = re.compile(
    r"customer\b"
    r"[\w\s,'\"-]{0,80}?"   # non-greedy gap for name / qualifiers
    r"(?:accounted\s+for|represented|comprised|was\s+responsible\s+for"
    r"|generated|made\s+up|contributed)"
    r"\s+(?:approximately\s+|about\s+|more\s+than\s+|over\s+)?"
    r"([\d]+(?:\.\d+)?)\s*(?:percent|%)",
    re.I,
)


def extract_customer_concentration(text: str) -> list[dict[str, Any]]:
    """Return list of customer concentration signals found in text.

    Each result dict has keys: ``concept`` ("customer_concentration_pct"),
    ``value`` (float percentage 0–100), ``context`` (matched substring, ≤200 chars).
    """
    results: list[dict[str, Any]] = []
    for m in _CUSTOMER_PCT_RE.finditer(text):
        try:
            pct = float(m.group(1))
        except (ValueError, TypeError):
            continue
        if pct <= 0 or pct > 100:
            continue
        start = max(0, m.start() - 30)
        end = min(len(text), m.end() + 30)
        results.append(
            {
                "concept": "customer_concentration_pct",
                "value": pct,
                "context": text[start:end].strip(),
            }
        )
    return results


# ---------------------------------------------------------------------------
# 2. User / engagement metrics (DAU, MAU, paid subscribers, GMV)
# ---------------------------------------------------------------------------

_DAU_RE = re.compile(
    r"(?:daily\s+active\s+(?:users?|accounts?)|DAUs?)\s*"
    r"(?:of|were|was|reached|totaled|averaged)?\s*"
    r"(?:approximately\s+)?"
    r"([\d,]+(?:\.\d+)?)\s*" + _UNIT_GROUP,
    re.I,
)

_MAU_RE = re.compile(
    r"(?:monthly\s+active\s+(?:users?|accounts?)|MAUs?)\s*"
    r"(?:of|were|was|reached|totaled|averaged)?\s*"
    r"(?:approximately\s+)?"
    r"([\d,]+(?:\.\d+)?)\s*" + _UNIT_GROUP,
    re.I,
)

_PAID_SUBS_RE = re.compile(
    r"(?:paid\s+(?:subscribers?|members?|customers?)|premium\s+subscribers?|paying\s+users?)\s*"
    r"(?:of|were|was|totaled|reached|numbered)?\s*"
    r"(?:approximately\s+)?"
    r"([\d,]+(?:\.\d+)?)\s*" + _UNIT_GROUP,
    re.I,
)

_GMV_RE = re.compile(
    r"(?:gross\s+merchandise\s+(?:volume|value)|GMV)\s*"
    r"(?:of|was|were|totaled|reached)?\s*"
    r"\$?\s*([\d,]+(?:\.\d+)?)\s*" + _UNIT_GROUP,
    re.I,
)


def extract_user_metrics(text: str) -> list[dict[str, Any]]:
    """Return engagement/user metric signals found in text.

    Each result dict: ``concept``, ``value`` (float), ``context`` (≤200 chars).
    """
    results: list[dict[str, Any]] = []

    def _add(pattern: re.Pattern[str], concept: str) -> None:
        m = pattern.search(text)
        if not m:
            return
        value = _scale(m.group(1), m.group(2) if m.lastindex and m.lastindex >= 2 else None)
        if value is None or value <= 0:
            return
        start = max(0, m.start() - 20)
        end = min(len(text), m.end() + 40)
        results.append(
            {"concept": concept, "value": value, "context": text[start:end].strip()}
        )

    _add(_DAU_RE, "daily_active_users")
    _add(_MAU_RE, "monthly_active_users")
    _add(_PAID_SUBS_RE, "paid_subscribers")
    _add(_GMV_RE, "gross_merchandise_volume")
    return results


# ---------------------------------------------------------------------------
# 3. Operating segment revenue
# ---------------------------------------------------------------------------
# Matches: "Segment X contributed $X.X billion in revenue"
#          "revenue from our [Segment name] segment was $X.X million"

_SEGMENT_REVENUE_RE = re.compile(
    r"(?:revenue\s+from\s+(?:our\s+)?|our\s+)?([A-Z][A-Za-z &]+?)\s+segment"
    r"(?:\s+(?:contributed|generated|was|were|totaled|accounted\s+for))?"
    r"[^$\d]{0,40}"
    r"\$\s*([\d,]+(?:\.\d+)?)\s*" + _UNIT_GROUP,
    re.I,
)


def extract_segment_revenue(text: str) -> list[dict[str, Any]]:
    """Return operating segment revenue signals found in text.

    Each result dict: ``concept`` ("segment_revenue"), ``segment_name``,
    ``value`` (float USD), ``context``.
    """
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _SEGMENT_REVENUE_RE.finditer(text):
        segment_name = m.group(1).strip()
        value = _scale(m.group(2), m.group(3) if m.lastindex and m.lastindex >= 3 else None)
        if value is None or value <= 0:
            continue
        key = f"{segment_name.lower()}:{round(value, -3)}"
        if key in seen:
            continue
        seen.add(key)
        start = max(0, m.start() - 20)
        end = min(len(text), m.end() + 40)
        results.append(
            {
                "concept": "segment_revenue",
                "segment_name": segment_name,
                "value": value,
                "context": text[start:end].strip(),
            }
        )
    return results[:20]  # cap to avoid noise from long tables


# ---------------------------------------------------------------------------
# 4. Employee headcount
# ---------------------------------------------------------------------------
# "we had approximately 45,000 full-time employees"
# "as of December 31, 2023 ... 12,500 employees"
# "employed approximately 7,200 people"

_HEADCOUNT_RE = re.compile(
    r"(?:had|employed|have|approximately)\s+"
    r"(?:approximately\s+)?"
    r"([\d,]+)\s*"
    r"(?:full[- ]time\s+)?(?:employees?|people|team\s+members?|associates?)",
    re.I,
)


def extract_headcount(text: str) -> dict[str, Any] | None:
    """Return the best headcount signal from text, or None.

    Prefers the largest value found (assumes total headcount is the biggest
    number, and departmental counts are smaller).
    """
    best: float | None = None
    best_context: str = ""
    for m in _HEADCOUNT_RE.finditer(text):
        try:
            value = float(m.group(1).replace(",", ""))
        except (ValueError, TypeError):
            continue
        if value < 1:
            continue
        if best is None or value > best:
            best = value
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 40)
            best_context = text[start:end].strip()

    if best is None:
        return None
    return {"concept": "employees", "value": best, "context": best_context}


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------

def extract_text_signals(text: str) -> list[dict[str, Any]]:
    """Run all extractors and return a combined list of signal dicts.

    Each dict has at minimum: ``concept``, ``value``.
    Optional keys: ``segment_name``, ``context``.

    Intended use: pass to ``silver.merge_financial_facts()`` under
    ``concept_namespace = "text_signal"``.
    """
    signals: list[dict[str, Any]] = []
    signals.extend(extract_customer_concentration(text))
    signals.extend(extract_user_metrics(text))
    signals.extend(extract_segment_revenue(text))
    hc = extract_headcount(text)
    if hc is not None:
        signals.append(hc)
    return signals
