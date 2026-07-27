"""ERDP-01 consensus estimates — Gold Explore product.

Street (or proxy) consensus for revenue, EPS, and related metrics, keyed by
issuer, fiscal period, and an ``as_of`` snapshot date, so ER skills can build
pre-print previews and compute beat/miss against actuals at query time.

Pilot sources:
- ``yahoo`` (primary automated, via yfinance)
- ``firm_manual`` (fallback)
- ``fmp`` (optional, not implemented in the pilot loader)

Does **not** store beat/miss — that is computed at query time by joining to
``EARNINGS_RELEASES`` / ``FINANCIAL_DERIVED`` on ``as_of <= print_date``.

Docs: ``docs/er-consensus-estimates.md``
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pyarrow as pa

from edgar_warehouse.serving.gold_schema_registry import GOLD_SCHEMAS

logger = logging.getLogger(__name__)

_FACT_CONSENSUS_ESTIMATE_SCHEMA = GOLD_SCHEMAS["_FACT_CONSENSUS_ESTIMATE_SCHEMA"]

PERIOD_TYPES = frozenset({"annual", "quarterly", "ntm", "ltm", "other"})
STATISTICS = frozenset({"mean", "median", "high", "low", "stdev", "n_analysts"})
SOURCE_SYSTEMS = frozenset(
    {"yahoo", "fmp", "finnhub", "estimize", "factset", "bloomberg", "cap_iq", "firm_manual", "other"}
)
# Phase-1 metric minimum (ERDP-01-06): revenue, eps_diluted must be accepted;
# should-have metrics also whitelisted so a real vendor payload isn't rejected.
METRICS = frozenset(
    {"revenue", "eps_diluted", "ebitda", "net_income", "eps_basic", "gross_profit"}
)

GRADE_EXPLORE = "explore"


class ConsensusRowError(ValueError):
    """Invalid consensus row after normalization attempts."""


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()[:10]
    return date.fromisoformat(text)


def _normalize_cik_int(cik: Any) -> int:
    if cik is None or cik == "":
        raise ConsensusRowError("cik is required")
    digits = "".join(ch for ch in str(cik).strip() if ch.isdigit())
    if not digits:
        raise ConsensusRowError(f"invalid cik: {cik!r}")
    return int(digits)


def consensus_fact_key(
    cik: int,
    metric: str,
    period_type: str,
    fiscal_year: int | None,
    fiscal_quarter: int | None,
    statistic: str,
    as_of: date,
    source_system: str,
) -> int:
    """Deterministic surrogate key for the natural key + as_of revision."""
    payload = (
        f"{cik}|{metric}|{period_type}|{fiscal_year}|{fiscal_quarter}|"
        f"{statistic}|{as_of.isoformat()}|{source_system}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def normalize_consensus_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a raw mapping into a CONSENSUS_ESTIMATES gold record.

    Required inputs: ``cik``, ``metric``, ``period_type``, ``estimate_value``,
    ``statistic``, ``as_of``, ``source_system``.  ``fiscal_year``/
    ``fiscal_quarter`` are required for ``annual``/``quarterly`` period types
    (D2: ``fiscal_quarter=0`` for annual); both may be null for ``ntm``/``ltm``.
    """
    cik = _normalize_cik_int(raw.get("cik"))

    metric = str(raw.get("metric") or "").strip().lower()
    if not metric:
        raise ConsensusRowError("metric is required")
    if metric not in METRICS:
        raise ConsensusRowError(f"unknown metric: {metric!r}")

    period_type = str(raw.get("period_type") or "").strip().lower()
    if period_type not in PERIOD_TYPES:
        raise ConsensusRowError(f"invalid period_type: {period_type!r}")

    fiscal_year = raw.get("fiscal_year")
    fiscal_year = int(fiscal_year) if fiscal_year not in (None, "") else None
    fiscal_quarter = raw.get("fiscal_quarter")
    fiscal_quarter = int(fiscal_quarter) if fiscal_quarter not in (None, "") else None

    if period_type == "annual":
        fiscal_quarter = 0
        if fiscal_year is None:
            raise ConsensusRowError("fiscal_year is required for period_type=annual")
    elif period_type == "quarterly":
        if fiscal_year is None:
            raise ConsensusRowError("fiscal_year is required for period_type=quarterly")
        if fiscal_quarter is None or not (1 <= fiscal_quarter <= 4):
            raise ConsensusRowError(
                f"fiscal_quarter must be 1-4 for period_type=quarterly; got {fiscal_quarter!r}"
            )

    estimate_value = raw.get("estimate_value")
    if estimate_value is None:
        raise ConsensusRowError("estimate_value is required")
    estimate_value = float(estimate_value)

    statistic = str(raw.get("statistic") or "").strip().lower()
    if statistic not in STATISTICS:
        raise ConsensusRowError(f"invalid statistic: {statistic!r}")
    if statistic == "n_analysts" and estimate_value < 0:
        raise ConsensusRowError("n_analysts estimate_value must be non-negative")

    as_of = _parse_date(raw.get("as_of"))
    if as_of is None:
        raise ConsensusRowError("as_of is required")

    source_system = str(raw.get("source_system") or "").strip().lower()
    if not source_system:
        raise ConsensusRowError("source_system is required")
    if source_system not in SOURCE_SYSTEMS:
        source_system = "other"

    unit = raw.get("unit")
    unit = str(unit).strip() if unit not in (None, "") else ("per_share" if metric.startswith("eps") else "USD")

    currency = raw.get("currency")
    currency = str(currency).strip().upper() if currency not in (None, "") else None

    ticker = raw.get("ticker")
    ticker = str(ticker).strip().upper() if ticker not in (None, "") else None

    company_key = raw.get("company_key")
    company_key = int(company_key) if company_key not in (None, "") else cik

    period_end = _parse_date(raw.get("period_end"))

    source_ref = raw.get("source_ref")
    source_ref = str(source_ref).strip() if source_ref not in (None, "") else None

    ingested_at = raw.get("ingested_at")
    if ingested_at is None:
        ingested_at = datetime.now(timezone.utc)
    elif isinstance(ingested_at, str):
        ingested_at = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
    if ingested_at.tzinfo is None:
        ingested_at = ingested_at.replace(tzinfo=timezone.utc)

    fact_key = raw.get("fact_key")
    if fact_key is None:
        fact_key = consensus_fact_key(
            cik, metric, period_type, fiscal_year, fiscal_quarter, statistic, as_of, source_system
        )
    else:
        fact_key = int(fact_key)

    return {
        "fact_key": fact_key,
        "cik": cik,
        "ticker": ticker,
        "company_key": company_key,
        "metric": metric,
        "period_type": period_type,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "period_end": period_end,
        "estimate_value": estimate_value,
        "unit": unit,
        "currency": currency,
        "statistic": statistic,
        "as_of": as_of,
        "source_system": source_system,
        "source_ref": source_ref,
        "ingested_at": ingested_at,
    }


def validate_consensus_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize and validate a batch; raises on first hard error."""
    return [normalize_consensus_row(r) for r in rows]


def build_consensus_estimates_table(rows: Sequence[Mapping[str, Any]]) -> pa.Table:
    """Build gold Arrow table for ``CONSENSUS_ESTIMATES`` from raw or normalized rows."""
    records = validate_consensus_rows(rows)
    if not records:
        return pa.table(
            {field.name: pa.array([], type=field.type) for field in _FACT_CONSENSUS_ESTIMATE_SCHEMA},
            schema=_FACT_CONSENSUS_ESTIMATE_SCHEMA,
        )
    return pa.table(
        {
            field.name: pa.array([r.get(field.name) for r in records], type=field.type)
            for field in _FACT_CONSENSUS_ESTIMATE_SCHEMA
        },
        schema=_FACT_CONSENSUS_ESTIMATE_SCHEMA,
    )


def current_consensus_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Keep latest ``as_of`` (then ``ingested_at``) per natural base key.

    Base key: ``(cik, metric, period_type, fiscal_year, fiscal_quarter,
    statistic, source_system)`` -- i.e. every column except ``as_of``
    (A01.2: history across ``as_of`` is retained upstream; this is a
    read-time "current" projection, not a filter applied before publish).
    """
    normalized = validate_consensus_rows(rows)
    best: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in normalized:
        key = (
            row["cik"], row["metric"], row["period_type"], row["fiscal_year"],
            row["fiscal_quarter"], row["statistic"], row["source_system"],
        )
        prev = best.get(key)
        if prev is None:
            best[key] = row
            continue
        if row["as_of"] > prev["as_of"]:
            best[key] = row
        elif row["as_of"] == prev["as_of"] and row["ingested_at"] >= prev["ingested_at"]:
            best[key] = row
    return list(best.values())


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
        payload.setdefault("statistic", "mean")
        out.append(normalize_consensus_row(payload))
    return out


def load_firm_manual_csv(
    path_or_text: str | Path,
    *,
    default_as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Load firm_manual consensus from CSV path or CSV text string.

    Required columns: ``cik``, ``metric``, ``period_type``, ``estimate_value``.
    Optional: ``ticker``, ``fiscal_year``, ``fiscal_quarter``, ``statistic``,
    ``unit``, ``currency``, ``period_end``, ``source_ref``, ``as_of``.
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


# yfinance period-label → canonical (period_type, fiscal_quarter offset)
# convention: '0q'/'+1q' are the current/next fiscal quarter; '0y'/'+1y' are
# the current/next fiscal year. yfinance does not expose an absolute
# fiscal_year/fiscal_quarter for these labels, so the caller must resolve
# them (e.g. from FILING_ACTIVITY / COMPANY fiscal calendar) and pass the
# resolved period for each label via `period_resolution`.
_YAHOO_PERIOD_LABELS = frozenset({"0q", "+1q", "0y", "+1y"})
_YAHOO_STAT_COLUMNS = {"avg": "mean", "low": "low", "high": "high", "numberOfAnalysts": "n_analysts"}


def parse_yahoo_consensus_estimate(
    *,
    cik: int | str,
    ticker: str,
    metric: str,
    estimate_frame: Mapping[str, Mapping[str, Any]],
    period_resolution: Mapping[str, Mapping[str, Any]],
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Parse a yfinance earnings/revenue estimate frame into normalized rows.

    ``estimate_frame`` is ``{period_label: {"avg": ..., "low": ..., "high":
    ..., "numberOfAnalysts": ...}}`` -- the row-oriented shape of
    ``yf.Ticker(ticker).get_earnings_estimate()`` / ``.get_revenue_estimate()``
    (``DataFrame.to_dict(orient="index")``) for labels in ``0q``/``+1q``/
    ``0y``/``+1y``.

    ``period_resolution`` maps each label present in ``estimate_frame`` to
    ``{"period_type": ..., "fiscal_year": ..., "fiscal_quarter": ...}`` --
    the caller's resolution of yfinance's relative offsets to an absolute
    fiscal period (see module docstring on ``_YAHOO_PERIOD_LABELS``).
    """
    as_of_d = as_of or date.today()
    cik_int = _normalize_cik_int(cik)
    rows: list[dict[str, Any]] = []
    for label, stats in estimate_frame.items():
        if label not in _YAHOO_PERIOD_LABELS:
            continue
        resolution = period_resolution.get(label)
        if resolution is None:
            logger.debug("skip yahoo estimate label %s: no period_resolution supplied", label)
            continue
        for raw_col, statistic in _YAHOO_STAT_COLUMNS.items():
            value = stats.get(raw_col) if isinstance(stats, Mapping) else None
            if value is None:
                continue
            raw = {
                "cik": cik_int,
                "ticker": ticker,
                "metric": metric,
                "period_type": resolution.get("period_type"),
                "fiscal_year": resolution.get("fiscal_year"),
                "fiscal_quarter": resolution.get("fiscal_quarter"),
                "estimate_value": value,
                "statistic": statistic,
                "as_of": as_of_d,
                "source_system": "yahoo",
                "source_ref": f"yahoo:{ticker}:{label}:{raw_col}",
            }
            try:
                rows.append(normalize_consensus_row(raw))
            except ConsensusRowError as exc:
                logger.debug("skip invalid yahoo estimate row %s/%s: %s", label, raw_col, exc)
                continue
    return rows


def fetch_yahoo_consensus_estimates(
    *,
    cik: int | str,
    ticker: str,
    period_resolution: Mapping[str, Mapping[str, Any]],
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Fetch and normalize Yahoo (yfinance) consensus estimates for one ticker.

    Requires the optional ``[market]`` extra (``yfinance``). Free/unofficial
    API -- ToS must be confirmed before a commercial gold load (A01.7,
    ERDP-01-08).
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ConsensusRowError("yfinance not installed (pip install edgartools-platform[market])") from exc

    handle = yf.Ticker(ticker)
    rows: list[dict[str, Any]] = []
    try:
        earnings_est = handle.get_earnings_estimate()
        if earnings_est is not None and not earnings_est.empty:
            rows.extend(
                parse_yahoo_consensus_estimate(
                    cik=cik, ticker=ticker, metric="eps_diluted",
                    estimate_frame=earnings_est.to_dict(orient="index"),
                    period_resolution=period_resolution, as_of=as_of,
                )
            )
    except Exception as exc:
        logger.debug("yahoo earnings estimate fetch failed for %s: %s", ticker, exc)

    try:
        revenue_est = handle.get_revenue_estimate()
        if revenue_est is not None and not revenue_est.empty:
            rows.extend(
                parse_yahoo_consensus_estimate(
                    cik=cik, ticker=ticker, metric="revenue",
                    estimate_frame=revenue_est.to_dict(orient="index"),
                    period_resolution=period_resolution, as_of=as_of,
                )
            )
    except Exception as exc:
        logger.debug("yahoo revenue estimate fetch failed for %s: %s", ticker, exc)

    return rows
