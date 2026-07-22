"""Filing artifact fetch and attachment registration helpers.

Ticket 06 (phase 1): filing documents/attachments use an edgartools-only
network gateway. Silver/cache skip still wins before network. Parallel
sec_client download_bytes is not used for this object class.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import sys
import time
from datetime import UTC, datetime
from typing import Any, Final

import edgar

from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory

# Ticket 06 architecture marker — architecture tests assert this contract.
FILING_DOCUMENT_NETWORK_GATEWAY: Final = "edgartools"


def _emit_artifact_event(event: str, **payload: Any) -> None:
    """Debug visibility for each individual SEC/artifact call this module makes.

    Matches sec_client.py's _emit_sec_pull_event JSON-line shape. Distinct
    from the aggregate network_fetches counter returned by
    fetch_filing_artifacts -- that counter answers "how many", these events
    answer "which accession/document, cache hit or real fetch, how long".
    """
    document = {
        "event": event,
        "emitted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        **payload,
    }
    print(json.dumps(document, sort_keys=True), file=sys.stderr, flush=True)


def _elapsed_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


class TransientFilingContentError(RuntimeError):
    """SEC returned unexpected content in place of a filing's structured attachments.

    edgartools degrades to a single "complete submission text file" pseudo-attachment
    (no document_type) when its SGML fetch gets back HTML/XML instead of the expected
    SGML bundle, without raising -- so this is only detectable after the fact, not as
    a network exception. Observed to be a transient SEC-side hiccup (a retry moments
    later returns the properly parsed per-document attachments), so it is raised here
    to be picked up by the artifact-fetch retry loop's transient-error classifier
    rather than reaching `merge_filing_attachments`'s required-field check as a fatal,
    non-retryable ValueError.
    """


class ParallelSecDownloadForbidden(RuntimeError):
    """Raised if filing-document capture would fall back to a non-edgartools client.

    Ticket 06: filing documents/attachments must not use a parallel raw SEC
    download path. Missing edgartools content is a hard failure, not a silent
    sec_client fallback.
    """


def fetch_filing_artifacts(
    *,
    context: Any,
    db: Any,
    accession_number: str,
    sync_run_id: str,
    download_bytes=None,
    get_filing=edgar.get_by_accession_number,
    force: bool = False,
    operator: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Fetch and register filing documents/attachments for one accession.

    ``download_bytes`` is accepted for call-site compatibility (orchestrator /
    service still pass it) but must not be used for this object class. Network
    content comes only from edgartools ``get_filing`` + attachment.content.
    """
    del download_bytes  # ticket 06: unused; kept for signature compatibility

    filing = db.get_filing(accession_number)
    if filing is None:
        raise ValueError(f"Unknown accession_number {accession_number}")

    cik = int(filing["cik"])
    capture_specs = default_capture_spec_factory()
    # Count real SEC network fetches so the orchestrator can skip its per-accession
    # rate-limit sleep on the idempotent cache-hit path (immutable, already-captured
    # artifacts). See CLAUDE.md artifact-throttle 5-whys.
    network_fetches = 0
    existing_rows = db.get_filing_attachments(accession_number)
    # Snapshot prior raw-object state per document *before* any force-driven
    # refetch, so a repair overwrite can be audited (prior vs. replacement
    # hash/version) even though force bypasses the ordinary cache-hit lookup
    # below (freshly-discovered attachment_rows carry no raw_object_id yet).
    prior_raw_by_document: dict[str, dict[str, Any]] = {}
    for row in existing_rows:
        raw_object_id = row.get("raw_object_id")
        if not raw_object_id:
            continue
        raw_object = db.get_raw_object(str(raw_object_id))
        if raw_object is not None:
            prior_raw_by_document[row["document_name"]] = raw_object
    repair_audit: list[dict[str, Any]] = []

    if existing_rows and not force:
        hydrated_rows, cached_records, missing_rows = _split_existing_attachment_rows(
            db, existing_rows
        )
        if not missing_rows:
            _emit_artifact_event(
                "accession_cache_hit",
                accession_number=accession_number,
                attachment_count=len(hydrated_rows),
            )
            return {
                "accession_number": accession_number,
                "attachment_count": len(hydrated_rows),
                "raw_writes": cached_records,
                "network_fetches": 0,
                "network_gateway": FILING_DOCUMENT_NETWORK_GATEWAY,
            }

    # Ticket 06: cold / partial / force always discover via edgartools — no
    # primary_document URL + sec_client download_bytes fast path.
    _started_at = time.monotonic()
    _emit_artifact_event(
        "sec_call_started", accession_number=accession_number, call="get_filing"
    )
    try:
        filing_obj = get_filing(accession_number)
    except Exception as exc:
        _emit_artifact_event(
            "sec_call_failed",
            accession_number=accession_number,
            call="get_filing",
            duration_ms=_elapsed_ms(_started_at),
            error=exc.__class__.__name__,
        )
        raise
    network_fetches += 1
    if filing_obj is None:
        _emit_artifact_event(
            "sec_call_failed",
            accession_number=accession_number,
            call="get_filing",
            duration_ms=_elapsed_ms(_started_at),
            error="filing_not_resolved",
        )
        raise ValueError(f"edgartools could not resolve filing for accession {accession_number}")
    _emit_artifact_event(
        "sec_call_completed",
        accession_number=accession_number,
        call="get_filing",
        duration_ms=_elapsed_ms(_started_at),
    )
    attachment_rows = _map_edgartools_attachments(filing_obj, accession_number)
    if not attachment_rows:
        raise ValueError(f"edgartools found no attachments for accession {accession_number}")

    raw_writes: list[dict[str, Any]] = []
    hydrated_rows: list[dict[str, Any]] = []
    for row in attachment_rows:
        document_name = row["document_name"]
        document_url = row["document_url"]
        prior_raw = prior_raw_by_document.get(document_name)
        existing_raw = None
        if row.get("raw_object_id"):
            existing_raw = db.get_raw_object(str(row["raw_object_id"]))
        if existing_raw is None and prior_raw is not None:
            existing_raw = prior_raw
        already_downloaded = (not force) and existing_raw is not None
        if already_downloaded:
            _emit_artifact_event(
                "artifact_storage_cache_hit",
                accession_number=accession_number,
                document_name=document_name,
            )
            hydrated = {key: value for key, value in row.items() if key != "content_bytes"}
            hydrated["raw_object_id"] = existing_raw.get("raw_object_id")
            hydrated_rows.append(hydrated)
            raw_writes.append(_cached_raw_record(existing_raw))
            continue

        payload = row.get("content_bytes")
        if payload is None:
            raise ParallelSecDownloadForbidden(
                f"accession {accession_number} document {document_name!r} has no "
                f"edgartools content; {FILING_DOCUMENT_NETWORK_GATEWAY}-only gateway "
                "refuses parallel sec_client download for filing documents"
            )
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        artifact_spec = capture_specs.filing_document(
            cik=cik,
            accession_number=accession_number,
            document_name=document_name,
            is_primary=bool(row.get("is_primary")),
        )
        raw_record = _write_raw_artifact(
            context=context,
            db=db,
            payload=payload,
            relative_path=artifact_spec.relative_path,
            source_type="filing_document" if row.get("is_primary") else "attachment",
            source_url=document_url,
            cik=cik,
            accession_number=accession_number,
            form=filing.get("form"),
        )
        raw_writes.append(raw_record)
        hydrated = {key: value for key, value in row.items() if key != "content_bytes"}
        hydrated["raw_object_id"] = raw_record["raw_object_id"]
        hydrated_rows.append(hydrated)

        if force and prior_raw is not None:
            repair_audit.append(
                {
                    "accession_number": accession_number,
                    "document_name": document_name,
                    "prior_object_hash": prior_raw.get("sha256"),
                    "prior_object_version": prior_raw.get("storage_path"),
                    "replacement_object_hash": raw_record["raw_object_id"],
                    "replacement_object_version": raw_record["path"],
                    "operator": operator,
                    "reason": reason,
                }
            )

    db.merge_filing_attachments(hydrated_rows, sync_run_id)
    result: dict[str, Any] = {
        "accession_number": accession_number,
        "attachment_count": len(hydrated_rows),
        "raw_writes": raw_writes,
        "network_fetches": network_fetches,
        "network_gateway": FILING_DOCUMENT_NETWORK_GATEWAY,
    }
    if repair_audit:
        result["repair_audit"] = repair_audit
    return result


def _split_existing_attachment_rows(
    db: Any, rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    hydrated_rows: list[dict[str, Any]] = []
    cached_records: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    for row in rows:
        raw_object_id = row.get("raw_object_id")
        raw_object = db.get_raw_object(str(raw_object_id)) if raw_object_id else None
        if raw_object is None:
            missing_rows.append(row)
            continue
        hydrated_rows.append(row)
        cached_records.append(_cached_raw_record(raw_object))
    return hydrated_rows, cached_records, missing_rows


def _cached_raw_record(raw_object: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw_object_id": raw_object.get("raw_object_id"),
        "path": raw_object.get("storage_path"),
        "source_url": raw_object.get("source_url"),
        "source_type": raw_object.get("source_type"),
        "cached": True,
    }


def _write_raw_artifact(
    *,
    context: Any,
    db: Any,
    payload: bytes,
    relative_path: str,
    source_type: str,
    source_url: str,
    cik: int,
    accession_number: str,
    form: str | None,
) -> dict[str, Any]:
    destination = context.bronze_root.write_bytes(relative_path, payload)
    sha256 = hashlib.sha256(payload).hexdigest()
    content_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
    fetched_at = datetime.now(UTC)
    db.upsert_raw_object(
        {
            "raw_object_id": sha256,
            "source_type": source_type,
            "cik": cik,
            "accession_number": accession_number,
            "form": form,
            "source_url": source_url,
            "storage_path": destination,
            "content_type": content_type,
            "byte_size": len(payload),
            "sha256": sha256,
            "fetched_at": fetched_at,
            "http_status": 200,
        }
    )
    return {
        "raw_object_id": sha256,
        "path": destination,
        "relative_path": relative_path,
        "source_url": source_url,
        "source_type": source_type,
    }


def _map_edgartools_attachments(filing_obj: Any, accession_number: str) -> list[dict[str, Any]]:
    """Map an edgartools Filing's attachments onto this module's attachment_rows
    shape, pre-fetching content bytes to avoid a second HTTP round-trip in the
    caller's write loop.

    is_primary is derived via membership in attachments.primary_documents rather
    than string-matching a primary_document name — more general, since a filing
    can have an unusual primary document that isn't html/xml.
    """
    primary_documents = list(filing_obj.attachments.primary_documents)
    rows: list[dict[str, Any]] = []
    for attachment in filing_obj.attachments:
        _started_at = time.monotonic()
        _emit_artifact_event(
            "artifact_call_started",
            accession_number=accession_number,
            document_name=attachment.document,
        )
        try:
            content = attachment.content
        except Exception as exc:
            _emit_artifact_event(
                "artifact_call_failed",
                accession_number=accession_number,
                document_name=attachment.document,
                duration_ms=_elapsed_ms(_started_at),
                error=exc.__class__.__name__,
            )
            raise
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content
        _emit_artifact_event(
            "artifact_call_completed",
            accession_number=accession_number,
            document_name=attachment.document,
            bytes=len(content_bytes) if content_bytes else 0,
            duration_ms=_elapsed_ms(_started_at),
        )
        if not attachment.document_type:
            raise TransientFilingContentError(
                f"accession {accession_number} document {attachment.document!r} has no "
                "document_type -- SEC likely returned unexpected content in place of the "
                "expected SGML filing data"
            )
        rows.append(
            {
                "accession_number": accession_number,
                "sequence_number": attachment.sequence_number,
                "document_name": attachment.document,
                "document_type": attachment.document_type,
                "document_description": attachment.description,
                "document_url": attachment.url,
                "is_primary": attachment in primary_documents,
                "content_bytes": content_bytes,
            }
        )
    return rows
