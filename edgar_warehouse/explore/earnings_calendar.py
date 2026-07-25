"""ERDP-03 earnings calendar — Gold Explore product.

Forward-looking expected report dates (date, session, status).  Not a
substitute for reactive ``EARNINGS_RELEASES.filing_date``.

Pilot sources:
- ``finnhub`` (primary automated)
- ``yahoo`` / ``firm_manual`` (fallback)

Docs: ``docs/er-earnings-calendar.md``
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pyarrow as pa

from edgar_warehouse.serving.gold_schema_registry import GOLD_SCHEMAS

logger = logging.getLogger(__name__)

_FACT_EARNINGS_CALENDAR_SCHEMA = GOLD_SCHEMAS["_FACT_EARNINGS_CALENDAR_SCHEMA"]

SESSIONS = frozenset({"pre_market", "after_close", "during_session", "unknown"})
STATUSES = frozenset({"estimated", "confirmed", "reported", "cancelled"})
SOURCE_SYSTEMS = frozenset(
    {"finnhub", "yahoo", "fmp", "firm_manual", "other"}
)

# Vendor hour / label → canonical session
_SESSION_ALIASES: dict[str, str] = {
    "bmo": "pre_market",
    "before market": "pre_market",
    "before-market": "pre_market",
    "before_market": "pre_market",
    "pre-market": "pre_market",
    "premarket": "pre_market",
    "pre_market": "pre_market",
    "amc": "after_close",
    "after market": "after_close",
    "after-market": "after_close",
    "after_market": "after_close",
    "after close": "after_close",
    "after-close": "after_close",
    "after_close": "after_close",
    "dmh": "during_session",
    "dma": "during_session",
    "during": "during_session",
    "during market": "during_session",
    "during_session": "during_session",
    "tas": "unknown",  # time not supplied
    "tns": "unknown",
    "unknown": "unknown",
    "": "unknown",
}

GRADE_EXPLORE = "explore"


class CalendarRowError(ValueError):
    """Invalid calendar row after normalization attempts."""


def map_session(raw: str | None) -> str:
    """Map vendor session/hour label to canonical ``session`` vocabulary."""
    if raw is None:
        return "unknown"
    key = str(raw).strip().lower()
    if not key:
        return "unknown"
    if key in _SESSION_ALIASES:
        return _SESSION_ALIASES[key]
    return _SESSION_ALIASES.get(key.replace(" ", "_"), "unknown")


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()[:10]
    return date.fromisoformat(text)


def _parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _normalize_cik_int(cik: Any) -> int:
    if cik is None or cik == "":
        raise CalendarRowError("cik is required")
    digits = "".join(ch for ch in str(cik).strip() if ch.isdigit())
    if not digits:
        raise CalendarRowError(f"invalid cik: {cik!r}")
    return int(digits)


def calendar_fact_key(
    cik: int,
    fiscal_year: int,
    fiscal_quarter: int,
    source_system: str,
    as_of: date,
) -> int:
    """Deterministic surrogate key for natural key + as_of revision."""
    payload = f"{cik}|{fiscal_year}|{fiscal_quarter}|{source_system}|{as_of.isoformat()}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def normalize_calendar_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a raw mapping into an EARNINGS_CALENDAR gold record.

    Required inputs: ``cik``, ``fiscal_year``, ``fiscal_quarter``,
    ``expected_date``, ``source_system``, ``as_of``.
    """
    cik = _normalize_cik_int(raw.get("cik"))
    fiscal_year = _parse_int(raw.get("fiscal_year"))
    fiscal_quarter = _parse_int(raw.get("fiscal_quarter"))
    if fiscal_year is None:
        raise CalendarRowError("fiscal_year is required")
    if fiscal_quarter is None or not (1 <= fiscal_quarter <= 4):
        raise CalendarRowError(f"fiscal_quarter must be 1–4; got {raw.get('fiscal_quarter')!r}")

    expected_date = _parse_date(raw.get("expected_date"))
    if expected_date is None:
        raise CalendarRowError("expected_date is required")

    as_of = _parse_date(raw.get("as_of"))
    if as_of is None:
        as_of = date.today()

    source_system = str(raw.get("source_system") or "").strip().lower()
    if not source_system:
        raise CalendarRowError("source_system is required")
    if source_system not in SOURCE_SYSTEMS:
        source_system = "other"

    # Prefer explicit session; else map hour/session_raw
    session_raw = raw.get("session")
    if session_raw is None or str(session_raw).strip() == "":
        session_raw = raw.get("hour") or raw.get("session_raw")
    session = map_session(session_raw if isinstance(session_raw, str) or session_raw is None else str(session_raw))
    if session not in SESSIONS:
        session = "unknown"

    status = str(raw.get("status") or "estimated").strip().lower()
    if status not in STATUSES:
        raise CalendarRowError(f"invalid status: {status!r}")

    # A03.2: confirmed should not use unknown session
    if status == "confirmed" and session == "unknown":
        raise CalendarRowError(
            "status=confirmed requires session in {pre_market, after_close, during_session}"
        )

    expected_time = raw.get("expected_time")
    if expected_time is not None:
        expected_time = str(expected_time).strip() or None

    timezone_name = raw.get("timezone")
    if timezone_name is not None:
        timezone_name = str(timezone_name).strip() or None

    ticker = raw.get("ticker")
    if ticker is not None:
        ticker = str(ticker).strip().upper() or None

    company_key = raw.get("company_key")
    if company_key is None:
        company_key = cik
    else:
        company_key = int(company_key)

    period_end = _parse_date(raw.get("period_end"))
    accession_number = raw.get("accession_number")
    if accession_number is not None:
        accession_number = str(accession_number).strip() or None

    source_ref = raw.get("source_ref")
    if source_ref is not None:
        source_ref = str(source_ref).strip() or None

    ingested_at = raw.get("ingested_at")
    if ingested_at is None:
        ingested_at = datetime.now(timezone.utc)
    elif isinstance(ingested_at, str):
        ingested_at = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
    if ingested_at.tzinfo is None:
        ingested_at = ingested_at.replace(tzinfo=timezone.utc)

    fact_key = raw.get("fact_key")
    if fact_key is None:
        fact_key = calendar_fact_key(cik, fiscal_year, fiscal_quarter, source_system, as_of)
    else:
        fact_key = int(fact_key)

    return {
        "fact_key": fact_key,
        "cik": cik,
        "ticker": ticker,
        "company_key": company_key,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "expected_date": expected_date,
        "expected_time": expected_time,
        "timezone": timezone_name,
        "session": session,
        "status": status,
        "period_end": period_end,
        "accession_number": accession_number,
        "source_system": source_system,
        "source_ref": source_ref,
        "as_of": as_of,
        "ingested_at": ingested_at,
    }


def validate_calendar_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize and validate a batch; raises on first hard error."""
    return [normalize_calendar_row(r) for r in rows]


def build_earnings_calendar_table(rows: Sequence[Mapping[str, Any]]) -> pa.Table:
    """Build gold Arrow table for ``EARNINGS_CALENDAR`` from raw or normalized rows."""
    records = validate_calendar_rows(rows)
    if not records:
        return pa.table(
            {field.name: pa.array([], type=field.type) for field in _FACT_EARNINGS_CALENDAR_SCHEMA},
            schema=_FACT_EARNINGS_CALENDAR_SCHEMA,
        )
    return pa.table(
        {
            field.name: pa.array([r.get(field.name) for r in records], type=field.type)
            for field in _FACT_EARNINGS_CALENDAR_SCHEMA
        },
        schema=_FACT_EARNINGS_CALENDAR_SCHEMA,
    )


def current_calendar_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Keep latest ``as_of`` (then ``ingested_at``) per natural base key.

    Base key: ``(cik, fiscal_year, fiscal_quarter, source_system)``.
    """
    normalized = validate_calendar_rows(rows)
    best: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in normalized:
        key = (row["cik"], row["fiscal_year"], row["fiscal_quarter"], row["source_system"])
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
        # firm_manual rows with an explicit session default to confirmed (A03.2)
        if payload.get("session") and not payload.get("status"):
            payload["status"] = "confirmed"
        else:
            payload.setdefault("status", "estimated")
        out.append(normalize_calendar_row(payload))
    return out


def load_firm_manual_csv(
    path_or_text: str | Path,
    *,
    default_as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Load firm_manual calendar from CSV path or CSV text string.

    Required columns: ``cik``, ``fiscal_year``, ``fiscal_quarter``, ``expected_date``.
    Optional: ``ticker``, ``session``, ``status``, ``expected_time``, ``timezone``,
    ``period_end``, ``source_ref``, ``as_of``, ``accession_number``.
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


def parse_finnhub_earnings_calendar(
    payload: Mapping[str, Any],
    *,
    ticker_to_cik: Mapping[str, int | str] | None = None,
    as_of: date | None = None,
    default_status: str = "estimated",
) -> list[dict[str, Any]]:
    """Parse Finnhub ``/calendar/earnings`` JSON into normalized calendar rows.

    Finnhub fields: ``symbol``, ``date``, ``hour`` (bmo|amc|dmh), ``quarter``,
    ``year``.  Rows whose ticker cannot be mapped to a CIK are skipped when
    ``ticker_to_cik`` is provided; if omitted, ``cik`` must already be present
    on each item or the row is skipped.
    """
    as_of_d = as_of or date.today()
    items = payload.get("earningsCalendar") or payload.get("earnings_calendar") or []
    if not isinstance(items, list):
        raise CalendarRowError("finnhub payload missing earningsCalendar list")

    mapping = {str(k).upper(): v for k, v in (ticker_to_cik or {}).items()}
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        symbol = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
        cik_val = item.get("cik")
        if cik_val is None and symbol:
            cik_val = mapping.get(symbol)
        if cik_val is None:
            logger.debug("skip finnhub row without CIK mapping: %s", symbol or item)
            continue

        year = item.get("year") or item.get("fiscal_year")
        quarter = item.get("quarter") or item.get("fiscal_quarter")
        exp_date = item.get("date") or item.get("expected_date")
        if year is None or quarter is None or not exp_date:
            continue

        hour = item.get("hour") or item.get("session")
        raw = {
            "cik": cik_val,
            "ticker": symbol or None,
            "fiscal_year": year,
            "fiscal_quarter": quarter,
            "expected_date": exp_date,
            "hour": hour,
            "status": item.get("status") or default_status,
            "source_system": "finnhub",
            "source_ref": f"finnhub:calendar/earnings:{symbol}:{year}:Q{quarter}",
            "as_of": as_of_d,
            "period_end": item.get("period_end"),
        }
        try:
            rows.append(normalize_calendar_row(raw))
        except CalendarRowError as exc:
            logger.debug("skip invalid finnhub row %s: %s", symbol, exc)
            continue
    return rows


def fetch_finnhub_earnings_calendar(
    *,
    from_date: str | date,
    to_date: str | date,
    api_key: str | None = None,
    ticker_to_cik: Mapping[str, int | str] | None = None,
    as_of: date | None = None,
    timeout_s: float = 30.0,
) -> list[dict[str, Any]]:
    """HTTP fetch Finnhub earnings calendar and normalize rows.

    Requires ``FINNHUB_API_KEY`` env var or ``api_key=``.  Free-tier license
    must be verified before commercial gold load (REQUIREMENTS ERDP-03-07).
    """
    token = api_key or os.environ.get("FINNHUB_API_KEY")
    if not token:
        raise CalendarRowError("FINNHUB_API_KEY not set")

    from_s = from_date if isinstance(from_date, str) else from_date.isoformat()
    to_s = to_date if isinstance(to_date, str) else to_date.isoformat()
    url = "https://finnhub.io/api/v1/calendar/earnings"

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover
        raise CalendarRowError("httpx required for finnhub fetch") from exc

    resp = httpx.get(
        url,
        params={"from": from_s, "to": to_s, "token": token},
        timeout=timeout_s,
    )
    resp.raise_for_status()
    return parse_finnhub_earnings_calendar(
        resp.json(),
        ticker_to_cik=ticker_to_cik,
        as_of=as_of,
    )


def mark_reported(
    calendar_rows: Sequence[Mapping[str, Any]],
    earnings_releases: Sequence[Mapping[str, Any]],
    *,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Transition matching calendar rows to ``status=reported`` when a release exists.

    Match on ``(cik, fiscal_year, fiscal_quarter)``.  Emits **new** revision
    rows (new ``as_of``) with ``accession_number`` set when available; does not
    mutate inputs.
    """
    as_of_d = as_of or date.today()
    release_index: dict[tuple[int, int, int], Mapping[str, Any]] = {}
    for rel in earnings_releases:
        try:
            cik = _normalize_cik_int(rel.get("cik"))
            fy = _parse_int(rel.get("fiscal_year"))
            fq = _parse_int(rel.get("fiscal_quarter"))
        except (CalendarRowError, TypeError, ValueError):
            continue
        if fy is None or fq is None:
            continue
        release_index[(cik, fy, fq)] = rel

    out: list[dict[str, Any]] = []
    for row in validate_calendar_rows(calendar_rows):
        key = (row["cik"], row["fiscal_year"], row["fiscal_quarter"])
        rel = release_index.get(key)
        if rel is None or row["status"] in {"reported", "cancelled"}:
            out.append(row)
            continue
        updated = dict(row)
        updated["status"] = "reported"
        updated["as_of"] = as_of_d
        acc = rel.get("accession_number")
        if acc:
            updated["accession_number"] = str(acc)
        updated["fact_key"] = calendar_fact_key(
            updated["cik"],
            updated["fiscal_year"],
            updated["fiscal_quarter"],
            updated["source_system"],
            as_of_d,
        )
        updated["ingested_at"] = datetime.now(timezone.utc)
        out.append(normalize_calendar_row(updated))
    return out


def coverage_for_universe(
    calendar_rows: Sequence[Mapping[str, Any]],
    universe_ciks: Iterable[int | str],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """A03.1 helper: fraction of universe CIKs with forward or just-reported row.

    A CIK is covered if any **current** row has:
    - ``expected_date >= today`` and status in estimated/confirmed, or
    - ``status == reported`` for a recent quarter (any reported row counts for pilot).
    """
    today_d = today or date.today()
    current = current_calendar_rows(calendar_rows)
    by_cik: dict[int, list[dict[str, Any]]] = {}
    for row in current:
        by_cik.setdefault(int(row["cik"]), []).append(row)

    universe = [_normalize_cik_int(c) for c in universe_ciks]
    covered: list[int] = []
    missing: list[int] = []
    for cik in universe:
        rows = by_cik.get(cik, [])
        ok = False
        for r in rows:
            if r["status"] == "reported":
                ok = True
                break
            if r["status"] in {"estimated", "confirmed"} and r["expected_date"] >= today_d:
                ok = True
                break
        if ok:
            covered.append(cik)
        else:
            missing.append(cik)

    n = len(universe)
    rate = (len(covered) / n) if n else 0.0
    return {
        "universe_size": n,
        "covered": len(covered),
        "missing_ciks": missing,
        "coverage_rate": rate,
        "meets_a03_1": rate >= 0.80 if n >= 10 else None,
    }


def next_n_days(
    calendar_rows: Sequence[Mapping[str, Any]],
    *,
    days: int = 14,
    today: date | None = None,
    ciks: Sequence[int | str] | None = None,
) -> list[dict[str, Any]]:
    """A03.3 helper: catalyst-calendar next-N-days list from current rows."""
    today_d = today or date.today()
    end = date.fromordinal(today_d.toordinal() + days)
    cik_filter = None
    if ciks is not None:
        cik_filter = {_normalize_cik_int(c) for c in ciks}

    out: list[dict[str, Any]] = []
    for row in current_calendar_rows(calendar_rows):
        if row["status"] not in {"estimated", "confirmed"}:
            continue
        if not (today_d <= row["expected_date"] <= end):
            continue
        if cik_filter is not None and row["cik"] not in cik_filter:
            continue
        out.append(row)
    out.sort(key=lambda r: (r["expected_date"], r["session"], r["cik"]))
    return out
