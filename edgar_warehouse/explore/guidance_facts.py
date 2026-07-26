"""ERDP-02 guidance facts — Gold Explore product.

Structured guidance values (low/mid/high) linked to identity (CIK) and,
where SEC-sourced, to the originating accession. Two source paths:

- SEC (preferred): extracted from the earnings-release guidance table
  (``EarningsRelease.guidance``, an edgartools ``FinancialTable``) already
  parsed off cached bronze HTML by ``edgar_warehouse.parsers.earnings_release``.
  No re-fetch — this module only transforms a table edgartools already parsed.
- ``firm_manual``: CSV/Parquet override or supplement, coexisting with SEC
  rows via ``source_system`` in the natural key (ERDP-02-05).

Docs: ``docs/er-guidance-facts.md``
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pyarrow as pa

from edgar_warehouse.serving.gold_schema_registry import GOLD_SCHEMAS

_FACT_GUIDANCE_SCHEMA = GOLD_SCHEMAS["_FACT_GUIDANCE_SCHEMA"]

GRADE_EXPLORE = "explore"

# Phase-1 metric vocabulary (ERDP-02-07): revenue/eps_diluted are the
# required minimum; the rest are best-effort.
METRICS = frozenset({
    "revenue", "eps_diluted", "eps_basic", "ebitda", "ebit", "net_income",
    "gross_profit", "operating_margin", "free_cash_flow", "capex", "other",
})
REQUIRED_METRICS = frozenset({"revenue", "eps_diluted"})

PERIOD_TYPES = frozenset({"annual", "quarterly", "range_fy", "other"})
SOURCE_SYSTEMS = frozenset({"sec_8k", "sec_10q", "sec_10k", "firm_manual", "other"})
CONFIDENCES = frozenset({"high", "medium", "low"})

_MAX_EXCERPT_LEN = 500


class GuidanceRowError(ValueError):
    """Invalid guidance row after normalization attempts (candidate for quarantine)."""


# ---------------------------------------------------------------------------
# Row-label -> metric classification (D2: table heuristics first)
# ---------------------------------------------------------------------------

# Order matters: more specific labels (e.g. "adjusted ebitda") must be
# checked before shorter substrings they contain (e.g. "ebit" inside
# "ebitda"), so this is a list of (patterns, metric) checked in order.
_METRIC_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("diluted eps", "diluted earnings per share", "eps - diluted", "eps, diluted",
      "earnings per diluted share"), "eps_diluted"),
    (("basic eps", "basic earnings per share", "eps - basic", "eps, basic",
      "earnings per basic share"), "eps_basic"),
    (("ebitda",), "ebitda"),
    (("ebit",), "ebit"),
    (("free cash flow", "fcf"), "free_cash_flow"),
    (("capital expenditure", "capex"), "capex"),
    (("gross profit",), "gross_profit"),
    (("operating margin",), "operating_margin"),
    (("net income", "net earnings"), "net_income"),
    (("revenue", "net sales", "total sales", "net revenue"), "revenue"),
]

_NON_GAAP_MARKERS = ("non-gaap", "non gaap", "adjusted", "as adjusted")

_PER_SHARE_METRICS = frozenset({"eps_diluted", "eps_basic"})
_PERCENT_METRICS = frozenset({"operating_margin"})


def _infer_unit(metric: str) -> str:
    """Infer ``unit`` for SEC-extracted rows.

    ``EarningsRelease.guidance.scaled_dataframe`` already multiplies AMOUNT
    rows by the table's detected scale factor (thousands/millions/billions),
    per-share/percentage rows are left unscaled (see ``FinancialTable.
    scaled_dataframe`` docstring) -- so post-scaling, amount metrics are
    already in raw USD, not the as-reported thousands/millions unit.
    """
    if metric in _PER_SHARE_METRICS:
        return "per_share"
    if metric in _PERCENT_METRICS:
        return "percent"
    return "USD"


def map_metric(label: str | None) -> tuple[str, bool]:
    """Classify a guidance-table row label into (metric, is_non_gaap).

    Unrecognized labels map to ``("other", False)`` rather than raising —
    callers decide whether "other" rows are worth keeping.
    """
    if not label:
        return "other", False
    key = str(label).strip().lower()
    is_non_gaap = any(marker in key for marker in _NON_GAAP_MARKERS)
    for patterns, metric in _METRIC_PATTERNS:
        if any(p in key for p in patterns):
            return metric, is_non_gaap
    return "other", is_non_gaap


# ---------------------------------------------------------------------------
# Cell value parsing: point value or "$X - $Y" / "$X to $Y" range
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(r"-?\$?\s*([\d,]+\.?\d*)")
_RANGE_SEP_RE = re.compile(r"\s+(?:-|to|–|—)\s+")


def parse_value_cell(raw: Any) -> tuple[float | None, float | None, float | None]:
    """Parse a guidance-table cell into (low, mid, high).

    Handles a bare number (point guidance: low=mid=high), a "$X - $Y" /
    "$X to $Y" range (mid = average), or an already-numeric low/high pair
    supplied as a 2-tuple. Returns ``(None, None, None)`` when nothing
    numeric can be extracted (e.g. "N/A", blank cell).
    """
    if raw is None:
        return None, None, None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val, val, val
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        low = _to_float(raw[0])
        high = _to_float(raw[1])
        if low is None and high is None:
            return None, None, None
        if low is not None and high is not None:
            return low, (low + high) / 2.0, high
        only = low if low is not None else high
        return only, only, only

    text = str(raw).strip()
    if not text or text.upper() in {"N/A", "NA", "-", "--"}:
        return None, None, None

    parts = _RANGE_SEP_RE.split(text)
    if len(parts) == 2:
        low = _extract_number(parts[0])
        high = _extract_number(parts[1])
        if low is not None and high is not None:
            if low > high:
                low, high = high, low
            return low, (low + high) / 2.0, high
        # Fall through to single-number extraction if range parse partially failed.

    value = _extract_number(text)
    if value is None:
        return None, None, None
    return value, value, value


def _extract_number(text: str) -> float | None:
    match = _NUMERIC_RE.search(text)
    if not match:
        return None
    digits = match.group(1).replace(",", "")
    if not digits or digits == ".":
        return None
    try:
        value = float(digits)
    except ValueError:
        return None
    if text.strip().startswith("-") or text.strip().startswith("($"):
        value = -abs(value)
    return value


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return _extract_number(str(value))


def _excerpt(text: str | None) -> str | None:
    if not text:
        return None
    text = str(text).strip()
    if not text:
        return None
    return text[:_MAX_EXCERPT_LEN]


# ---------------------------------------------------------------------------
# Normalization / fact_key / validation
# ---------------------------------------------------------------------------

def guidance_fact_key(
    cik: int,
    metric: str,
    fiscal_year: int,
    fiscal_quarter: int,
    as_of: date,
    accession_number: str,
    is_non_gaap: bool,
    source_system: str,
) -> int:
    """Deterministic surrogate key over the full natural key."""
    payload = (
        f"{cik}|{metric}|{fiscal_year}|{fiscal_quarter}|{as_of.isoformat()}|"
        f"{accession_number}|{is_non_gaap}|{source_system}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _normalize_cik_int(cik: Any) -> int:
    if cik is None or cik == "":
        raise GuidanceRowError("cik is required")
    digits = "".join(ch for ch in str(cik).strip() if ch.isdigit())
    if not digits:
        raise GuidanceRowError(f"invalid cik: {cik!r}")
    return int(digits)


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()[:10]
    return date.fromisoformat(text)


def normalize_guidance_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a raw mapping into a ``sec_guidance_fact`` / GUIDANCE_FACTS row.

    Required inputs: ``cik``, ``metric``, ``fiscal_year``, ``fiscal_quarter``,
    ``as_of``, ``source_system``, and at least one of ``value_low`` /
    ``value_mid`` / ``value_high``.

    Raises ``GuidanceRowError`` (candidate for quarantine, §5.3) on any
    constraint violation.
    """
    cik = _normalize_cik_int(raw.get("cik"))

    metric = str(raw.get("metric") or "").strip().lower()
    if not metric:
        raise GuidanceRowError("metric is required")
    if metric not in METRICS:
        metric = "other"

    fiscal_year = raw.get("fiscal_year")
    if fiscal_year is None:
        raise GuidanceRowError("fiscal_year is required")
    fiscal_year = int(fiscal_year)

    fiscal_quarter = raw.get("fiscal_quarter")
    if fiscal_quarter is None:
        raise GuidanceRowError("fiscal_quarter is required")
    fiscal_quarter = int(fiscal_quarter)
    if not (0 <= fiscal_quarter <= 4):
        raise GuidanceRowError(f"fiscal_quarter must be 0-4 (0=annual); got {fiscal_quarter!r}")

    period_type = str(raw.get("period_type") or "").strip().lower()
    if not period_type:
        period_type = "annual" if fiscal_quarter == 0 else "quarterly"
    if period_type not in PERIOD_TYPES:
        raise GuidanceRowError(f"invalid period_type: {period_type!r}")

    value_low = _to_float(raw.get("value_low"))
    value_mid = _to_float(raw.get("value_mid"))
    value_high = _to_float(raw.get("value_high"))
    if value_low is None and value_mid is None and value_high is None:
        raise GuidanceRowError("at least one of value_low/value_mid/value_high is required")
    if value_low is not None and value_high is not None and value_low > value_high:
        raise GuidanceRowError(f"value_low ({value_low}) must be <= value_high ({value_high})")
    if value_mid is not None:
        if value_low is not None and value_mid < value_low:
            raise GuidanceRowError(f"value_mid ({value_mid}) must be >= value_low ({value_low})")
        if value_high is not None and value_mid > value_high:
            raise GuidanceRowError(f"value_mid ({value_mid}) must be <= value_high ({value_high})")

    as_of = _parse_date(raw.get("as_of"))
    if as_of is None:
        raise GuidanceRowError("as_of is required")

    source_system = str(raw.get("source_system") or "").strip().lower()
    if not source_system:
        raise GuidanceRowError("source_system is required")
    if source_system not in SOURCE_SYSTEMS:
        source_system = "other"

    accession_number = raw.get("accession_number")
    accession_number = str(accession_number).strip() if accession_number else ""
    if source_system.startswith("sec_") and not accession_number:
        raise GuidanceRowError(f"source_system={source_system} requires accession_number")

    is_non_gaap = bool(raw.get("is_non_gaap", False))

    confidence = str(raw.get("confidence") or "medium").strip().lower()
    if confidence not in CONFIDENCES:
        confidence = "medium"

    ticker = raw.get("ticker")
    ticker = str(ticker).strip().upper() if ticker else None

    company_key = raw.get("company_key")
    company_key = int(company_key) if company_key is not None else cik

    period_end = _parse_date(raw.get("period_end"))
    unit = raw.get("unit")
    unit = str(unit).strip() if unit else None
    currency = raw.get("currency")
    currency = str(currency).strip().upper() if currency else None
    source_ref = raw.get("source_ref")
    source_ref = str(source_ref).strip() if source_ref else None
    excerpt = _excerpt(raw.get("excerpt"))
    parser_version = raw.get("parser_version")

    ingested_at = raw.get("ingested_at")
    if ingested_at is None:
        ingested_at = datetime.now(timezone.utc)
    elif isinstance(ingested_at, str):
        ingested_at = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
    if ingested_at.tzinfo is None:
        ingested_at = ingested_at.replace(tzinfo=timezone.utc)

    fact_key = raw.get("fact_key")
    if fact_key is None:
        fact_key = guidance_fact_key(
            cik, metric, fiscal_year, fiscal_quarter, as_of,
            accession_number, is_non_gaap, source_system,
        )
    else:
        fact_key = int(fact_key)

    return {
        "fact_key": fact_key,
        "cik": cik,
        "ticker": ticker,
        "company_key": company_key,
        "accession_number": accession_number or None,
        "metric": metric,
        "period_type": period_type,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "period_end": period_end,
        "value_low": value_low,
        "value_mid": value_mid,
        "value_high": value_high,
        "unit": unit,
        "currency": currency,
        "is_non_gaap": is_non_gaap,
        "as_of": as_of,
        "source_system": source_system,
        "source_ref": source_ref,
        "excerpt": excerpt,
        "confidence": confidence,
        "parser_version": parser_version,
        "ingested_at": ingested_at,
    }


def validate_guidance_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize a batch; returns (accepted, rejected) rather than raising.

    Rejected entries carry ``reject_reason`` for the D6 quarantine table
    (``sec_guidance_fact_reject``).
    """
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in rows:
        try:
            accepted.append(normalize_guidance_row(raw))
        except GuidanceRowError as exc:
            rejected.append({
                "cik": raw.get("cik"),
                "accession_number": raw.get("accession_number"),
                "metric": raw.get("metric"),
                "reject_reason": str(exc),
                "parser_version": raw.get("parser_version"),
            })
    return accepted, rejected


def build_guidance_facts_table(rows: Sequence[Mapping[str, Any]]) -> pa.Table:
    """Build gold Arrow table for ``GUIDANCE_FACTS`` from raw or normalized rows.

    Rows that fail validation are silently dropped (callers doing bulk
    ingest should use ``validate_guidance_rows`` first to capture rejects).
    """
    accepted, _ = validate_guidance_rows(rows)
    if not accepted:
        return pa.table(
            {field.name: pa.array([], type=field.type) for field in _FACT_GUIDANCE_SCHEMA},
            schema=_FACT_GUIDANCE_SCHEMA,
        )
    return pa.table(
        {
            field.name: pa.array([r.get(field.name) for r in accepted], type=field.type)
            for field in _FACT_GUIDANCE_SCHEMA
        },
        schema=_FACT_GUIDANCE_SCHEMA,
    )


def current_guidance_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Keep latest ``as_of`` (then ``ingested_at``) per full natural key.

    Unlike ERDP-03's calendar (which collapses to one row per base key),
    GUIDANCE_FACTS' natural key already includes ``as_of`` -- multiple
    ``as_of`` snapshots are all published (needed for A02.3's
    guide-in-force-before-print recipe). This helper answers "what's the
    latest guide" for callers who explicitly want the current view.
    """
    accepted, _ = validate_guidance_rows(rows)
    best: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in accepted:
        key = (row["cik"], row["metric"], row["fiscal_year"], row["fiscal_quarter"],
               row["accession_number"], row["is_non_gaap"], row["source_system"])
        prev = best.get(key)
        if prev is None:
            best[key] = row
            continue
        if row["as_of"] > prev["as_of"]:
            best[key] = row
        elif row["as_of"] == prev["as_of"] and row["ingested_at"] >= prev["ingested_at"]:
            best[key] = row
    return list(best.values())


# ---------------------------------------------------------------------------
# firm_manual CSV loader (ERDP-02-A02.7)
# ---------------------------------------------------------------------------

def load_firm_manual_records(
    records: Sequence[Mapping[str, Any]],
    *,
    default_as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Load firm_manual rows; force ``source_system=firm_manual`` when missing."""
    as_of = default_as_of or date.today()
    out: list[dict[str, Any]] = []
    for rec in records:
        payload = dict(rec)
        payload.setdefault("source_system", "firm_manual")
        payload.setdefault("as_of", as_of)
        payload.setdefault("confidence", "high")  # firm-provided values are trusted
        out.append(normalize_guidance_row(payload))
    return out


def load_firm_manual_csv(
    path_or_text: str | Path,
    *,
    default_as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Load firm_manual guidance from CSV path or CSV text string.

    Required columns: ``cik``, ``metric``, ``fiscal_year``, ``fiscal_quarter``,
    and at least one of ``value_low``/``value_mid``/``value_high``.
    Optional: ``ticker``, ``period_type``, ``period_end``, ``unit``,
    ``currency``, ``is_non_gaap``, ``as_of``, ``source_ref``, ``excerpt``.
    """
    if isinstance(path_or_text, Path) or (
        isinstance(path_or_text, str)
        and "\n" not in path_or_text
        and Path(path_or_text).is_file()
    ):
        text = Path(path_or_text).read_text(encoding="utf-8")
    else:
        text = str(path_or_text)

    reader = csv.DictReader(io.StringIO(text))
    return load_firm_manual_records(list(reader), default_as_of=default_as_of)


# ---------------------------------------------------------------------------
# SEC extractor (ERDP-02-A02.1/A02.2): walks EarningsRelease.guidance
# ---------------------------------------------------------------------------

def extract_guidance_from_table(
    *,
    dataframe: Any,
    row_types: Any = None,
    cik: int,
    accession_number: str,
    filing_date: str | None,
    fiscal_year: int | None,
    fiscal_quarter: int | None,
    source_system: str = "sec_8k",
    parser_version: str | None = None,
) -> list[dict[str, Any]]:
    """Extract candidate guidance rows from a parsed guidance table.

    ``dataframe`` is the guidance ``FinancialTable``'s (scaled) dataframe:
    index = row labels, columns = period labels, cells = point values or
    range strings. Duck-typed on purpose (accepts a real edgartools
    ``FinancialTable.scaled_dataframe`` or any pandas-like object with the
    same ``.index``/``.columns``/``.loc`` shape) so tests can supply
    synthetic fixtures without constructing a full ``EarningsRelease``.

    Returns unvalidated candidates -- caller (``validate_guidance_rows``)
    applies §5.3 constraints and routes rejects to quarantine.
    """
    as_of = _parse_date(filing_date) or date.today()
    fy = fiscal_year if fiscal_year is not None else as_of.year
    fq = fiscal_quarter if fiscal_quarter is not None else 0

    candidates: list[dict[str, Any]] = []
    for row_label in dataframe.index:
        metric, is_non_gaap = map_metric(str(row_label))
        if metric == "other":
            continue  # phase-1: only keep rows we can classify (D2 heuristics)

        row = dataframe.loc[row_label]
        # A row may span multiple period columns (e.g. Q1 and FY guidance
        # given together); take the first non-empty cell as phase-1 scope
        # (documented limitation -- see docs/er-guidance-facts.md).
        cell = None
        try:
            values = row.tolist() if hasattr(row, "tolist") else list(row)
        except TypeError:
            values = [row]
        for v in values:
            if v is not None and str(v).strip() not in ("", "nan", "None"):
                cell = v
                break
        if cell is None:
            continue

        low, mid, high = parse_value_cell(cell)
        if low is None and mid is None and high is None:
            continue

        candidates.append({
            "cik": cik,
            "accession_number": accession_number,
            "metric": metric,
            "fiscal_year": fy,
            "fiscal_quarter": fq,
            "value_low": low,
            "value_mid": mid,
            "value_high": high,
            "unit": _infer_unit(metric),
            "is_non_gaap": is_non_gaap,
            "as_of": as_of,
            "source_system": source_system,
            "source_ref": f"{source_system}:{accession_number}:guidance:{row_label}",
            "excerpt": _excerpt(f"{row_label}: {cell}"),
            "confidence": "medium",
            "parser_version": parser_version,
        })
    return candidates


def extract_guidance_from_earnings_release(
    er: Any,
    *,
    cik: int,
    accession_number: str,
    filing_date: str | None,
    fiscal_year: int | None = None,
    fiscal_quarter: int | None = None,
    source_system: str = "sec_8k",
    parser_version: str | None = None,
) -> list[dict[str, Any]]:
    """Extract candidate guidance rows from an ``edgartools`` ``EarningsRelease``.

    Returns ``[]`` when the release has no guidance table (``.guidance is
    None``) or extraction fails -- absence is not an error (mirrors
    ``has_guidance`` presence-only detection already in
    ``edgar_warehouse.parsers.earnings_release``).
    """
    try:
        table = er.guidance
    except Exception:
        return []
    if table is None:
        return []
    try:
        dataframe = table.scaled_dataframe
    except Exception:
        try:
            dataframe = table.dataframe
        except Exception:
            return []
    if dataframe is None or dataframe.empty:
        return []

    return extract_guidance_from_table(
        dataframe=dataframe,
        cik=cik,
        accession_number=accession_number,
        filing_date=filing_date,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        source_system=source_system,
        parser_version=parser_version,
    )
