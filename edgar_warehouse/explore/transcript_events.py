"""ERDP-04 transcript MVP — Gold Explore pointer product.

A durable **pointer** (+ optional platform-held copy) for one earnings call
or investor day event -- not full NLP extraction of transcript content, and
not a replacement for the separate SEC filing text projection.

Pilot sources:
- ``ir_website`` (pointer-only to the official IR HTTPS URL; primary)
- ``firm_manual`` (ops uploads a ``.txt`` and the platform stores a copy)

Pilot universe (D6, locked): a small explicit CIK list, **not** the full SEC
universe and **not** a bulk third-party scrape -- see ``PILOT_CIKS``.

Docs: ``docs/er-transcript-events.md``
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

_FACT_TRANSCRIPT_EVENT_SCHEMA = GOLD_SCHEMAS["_FACT_TRANSCRIPT_EVENT_SCHEMA"]

EVENT_TYPES = frozenset({"earnings_call", "investor_day", "other"})
SOURCE_SYSTEMS = frozenset({"ir_website", "firm_manual", "fmp", "other"})

# ERDP-04 pilot universe lock (2026-07-27): Apple only. Chosen because it is
# already the example CIK used throughout this platform's docs/tests
# (guidance facts, earnings calendar). Expanding this list is a deliberate
# decision, not a default -- D6 explicitly rules out full-universe free
# scraping as the default ingest path for transcripts.
PILOT_CIKS = frozenset({320193})

GRADE_EXPLORE = "explore"


class TranscriptRowError(ValueError):
    """Invalid transcript event row after normalization attempts."""


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
        raise TranscriptRowError("cik is required")
    digits = "".join(ch for ch in str(cik).strip() if ch.isdigit())
    if not digits:
        raise TranscriptRowError(f"invalid cik: {cik!r}")
    return int(digits)


def transcript_event_key(cik: int, event_id: str, source_system: str) -> int:
    """Deterministic surrogate key for the natural key (cik, event_id, source_system).

    Unlike ERDP-01/02/03, ``as_of`` is not part of the natural key here (§4.2
    of the spec) -- a pointer is revalidated in place (``as_of`` bumped on
    the same row), it does not create a new historical version.
    """
    payload = f"{cik}|{event_id}|{source_system}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def derive_ir_event_id(cik: int, event_date: date, event_type: str, source_url: str) -> str:
    """§4.2 IR-only event_id rule: hash(cik|event_date|event_type|url)."""
    payload = f"{cik}|{event_date.isoformat()}|{event_type}|{source_url}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def normalize_transcript_row(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a raw mapping into a TRANSCRIPT_EVENTS gold record.

    Required inputs: ``cik``, ``event_id``, ``event_type``, ``event_date``,
    ``storage_uri``, ``source_system``.
    """
    cik = _normalize_cik_int(raw.get("cik"))

    event_id = raw.get("event_id")
    if not event_id:
        raise TranscriptRowError("event_id is required")
    event_id = str(event_id).strip()

    event_type = str(raw.get("event_type") or "").strip().lower()
    if event_type not in EVENT_TYPES:
        raise TranscriptRowError(f"invalid event_type: {event_type!r}")

    event_date = _parse_date(raw.get("event_date"))
    if event_date is None:
        raise TranscriptRowError("event_date is required")

    storage_uri = raw.get("storage_uri")
    if not storage_uri or not str(storage_uri).strip():
        raise TranscriptRowError("storage_uri is required (A04 integrity rule 1)")
    storage_uri = str(storage_uri).strip()

    source_system = str(raw.get("source_system") or "").strip().lower()
    if not source_system:
        raise TranscriptRowError("source_system is required")
    if source_system not in SOURCE_SYSTEMS:
        source_system = "other"

    content_sha256 = raw.get("content_sha256")
    content_sha256 = str(content_sha256).strip() if content_sha256 not in (None, "") else None
    if storage_uri.startswith("s3://") and content_sha256 is None:
        # A04 integrity rule 2 says "should", not "must" -- pointer-only s3
        # references (e.g. re-registering an externally-uploaded object)
        # remain valid; this is a soft warning, not a hard rejection.
        logger.warning(
            "transcript event %s/%s has an s3:// storage_uri without content_sha256",
            cik, event_id,
        )

    char_count = raw.get("char_count")
    char_count = int(char_count) if char_count not in (None, "") else None

    ticker = raw.get("ticker")
    ticker = str(ticker).strip().upper() if ticker not in (None, "") else None

    company_key = raw.get("company_key")
    company_key = int(company_key) if company_key not in (None, "") else cik

    fiscal_year = raw.get("fiscal_year")
    fiscal_year = int(fiscal_year) if fiscal_year not in (None, "") else None
    fiscal_quarter = raw.get("fiscal_quarter")
    fiscal_quarter = int(fiscal_quarter) if fiscal_quarter not in (None, "") else None

    accession_number = raw.get("accession_number")
    accession_number = str(accession_number).strip() if accession_number not in (None, "") else None

    language = raw.get("language")
    language = str(language).strip() if language not in (None, "") else "en"

    source_url = raw.get("source_url")
    source_url = str(source_url).strip() if source_url not in (None, "") else None

    as_of = _parse_date(raw.get("as_of"))
    if as_of is None:
        as_of = date.today()

    ingested_at = raw.get("ingested_at")
    if ingested_at is None:
        ingested_at = datetime.now(timezone.utc)
    elif isinstance(ingested_at, str):
        ingested_at = datetime.fromisoformat(ingested_at.replace("Z", "+00:00"))
    if ingested_at.tzinfo is None:
        ingested_at = ingested_at.replace(tzinfo=timezone.utc)

    event_key = raw.get("event_key")
    if event_key is None:
        event_key = transcript_event_key(cik, event_id, source_system)
    else:
        event_key = int(event_key)

    return {
        "event_key": event_key,
        "cik": cik,
        "ticker": ticker,
        "company_key": company_key,
        "event_id": event_id,
        "event_type": event_type,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "event_date": event_date,
        "accession_number": accession_number,
        "storage_uri": storage_uri,
        "content_sha256": content_sha256,
        "char_count": char_count,
        "language": language,
        "source_system": source_system,
        "source_url": source_url,
        "as_of": as_of,
        "ingested_at": ingested_at,
    }


def validate_transcript_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize and validate a batch; raises on first hard error."""
    return [normalize_transcript_row(r) for r in rows]


def build_transcript_events_table(rows: Sequence[Mapping[str, Any]]) -> pa.Table:
    """Build gold Arrow table for ``TRANSCRIPT_EVENTS`` from raw or normalized rows."""
    records = validate_transcript_rows(rows)
    if not records:
        return pa.table(
            {field.name: pa.array([], type=field.type) for field in _FACT_TRANSCRIPT_EVENT_SCHEMA},
            schema=_FACT_TRANSCRIPT_EVENT_SCHEMA,
        )
    return pa.table(
        {
            field.name: pa.array([r.get(field.name) for r in records], type=field.type)
            for field in _FACT_TRANSCRIPT_EVENT_SCHEMA
        },
        schema=_FACT_TRANSCRIPT_EVENT_SCHEMA,
    )


def register_ir_pointer(
    *,
    cik: int | str,
    event_date: date,
    source_url: str,
    event_type: str = "earnings_call",
    ticker: str | None = None,
    fiscal_year: int | None = None,
    fiscal_quarter: int | None = None,
    accession_number: str | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """A04.6: register a pointer-only ``ir_website`` row -- no bytes stored.

    ``event_id`` is derived deterministically from (cik, event_date,
    event_type, source_url) per §4.2, so re-registering the same IR URL is
    idempotent (same event_key).
    """
    cik_int = _normalize_cik_int(cik)
    event_id = derive_ir_event_id(cik_int, event_date, event_type, source_url)
    return normalize_transcript_row({
        "cik": cik_int,
        "ticker": ticker,
        "event_id": event_id,
        "event_type": event_type,
        "event_date": event_date,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "accession_number": accession_number,
        "storage_uri": source_url,
        "source_system": "ir_website",
        "source_url": source_url,
        "as_of": as_of,
    })


def store_transcript_text(
    *,
    cik: int | str,
    event_date: date,
    text: str,
    storage_root: Any,
    event_type: str = "earnings_call",
    event_id: str | None = None,
    source_system: str = "firm_manual",
    ticker: str | None = None,
    fiscal_year: int | None = None,
    fiscal_quarter: int | None = None,
    accession_number: str | None = None,
    source_url: str | None = None,
    language: str = "en",
    as_of: date | None = None,
) -> dict[str, Any]:
    """A04.5: write ``text`` to the object store and return the gold pointer row.

    ``storage_root`` is a
    :class:`edgar_warehouse.infrastructure.object_storage.StorageLocation`
    (or any object exposing ``write_text(relative_path, payload) -> str``).
    Computes ``content_sha256``/``char_count`` per the integrity rules.
    """
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver

    cik_int = _normalize_cik_int(cik)
    if event_id is None:
        event_id = f"{event_type}-{event_date.isoformat()}"

    relative_path = default_path_resolver().transcript_text_path(cik=cik_int, event_id=event_id)
    storage_uri = storage_root.write_text(relative_path, text)

    return normalize_transcript_row({
        "cik": cik_int,
        "ticker": ticker,
        "event_id": event_id,
        "event_type": event_type,
        "event_date": event_date,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "accession_number": accession_number,
        "storage_uri": storage_uri,
        "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "char_count": len(text),
        "language": language,
        "source_system": source_system,
        "source_url": source_url,
        "as_of": as_of,
    })


def load_firm_manual_records(
    records: Sequence[Mapping[str, Any]],
    *,
    default_as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Load firm_manual metadata rows pointing at an already-uploaded object.

    Use when ops has already dropped a ``.txt`` to S3 out-of-band and only
    needs to publish the gold pointer row (``storage_uri`` supplied
    directly); for uploading text through this module, use
    :func:`store_transcript_text` instead.
    """
    as_of = default_as_of or date.today()
    out: list[dict[str, Any]] = []
    for rec in records:
        payload = dict(rec)
        payload.setdefault("source_system", "firm_manual")
        payload.setdefault("as_of", as_of)
        out.append(normalize_transcript_row(payload))
    return out


def load_firm_manual_csv(
    path_or_text: str | Path,
    *,
    default_as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Load firm_manual transcript pointer metadata from CSV path or text.

    Required columns: ``cik``, ``event_id``, ``event_type``, ``event_date``,
    ``storage_uri``. Optional: ``ticker``, ``fiscal_year``, ``fiscal_quarter``,
    ``accession_number``, ``content_sha256``, ``char_count``, ``language``,
    ``source_url``, ``as_of``.
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
