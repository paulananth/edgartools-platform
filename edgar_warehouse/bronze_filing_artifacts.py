"""Filing artifact fetch and attachment registration helpers.

edgartools supplies filing/attachment discovery metadata. Immutable bronze
content is fetched separately as the exact SEC archival response.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any, Final

import edgar
from edgar_warehouse.infrastructure.dataset_path_catalog import (
    default_capture_spec_factory,
)
from edgar_warehouse.infrastructure.object_storage import object_exists

# Ticket 96: edgar.get_by_accession_number's whole-market quarterly-index scan
# inherits httpx's bare 5s default timeout (edgartools' shared HTTP_MGR client
# sets no timeout of its own), compounded by two nested 5x retry decorators
# inside edgartools -- producing ~83s-per-call failures under degraded SEC
# connectivity instead of a fast, clean error. edgartools already defines a
# more generous BULK_TIMEOUT for exactly this "large SEC file, congested
# connection" scenario but wires it into an unrelated async path only. This
# raises the floor for every edgartools HTTP call this module makes.
edgar.configure_http(timeout=60.0)

# Ticket 56 architecture marker — architecture tests assert this contract.
FILING_DOCUMENT_NETWORK_GATEWAY: Final = "raw_sec_http"

# Ticket 77 (pipeline-throughput-architecture ticket 03): bounded worker pool
# for the per-document artifact-fetch loop below. Matches the existing
# BOOTSTRAP_BATCH_CONCURRENCY 2-5 recommended range; pyrate_limiter's
# thread-safe Limiter (source-verified internal RLock) remains the real
# throughput ceiling regardless of pool size.
_DEFAULT_ARTIFACT_FETCH_CONCURRENCY: Final = 5


def _artifact_fetch_concurrency() -> int:
    raw = os.environ.get(
        "WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY", str(_DEFAULT_ARTIFACT_FETCH_CONCURRENCY)
    )
    return max(1, int(raw))


# Ticket 70 — raster-image exhibits (investor-presentation slides etc.) that no
# parser in this repo reads. Narrowest rule from the operator decision: image
# extensions only, never PDFs/zips/XBRL. Never applied to the primary document
# regardless of its extension (see _is_excluded_binary_attachment).
_EXCLUDED_BINARY_EXTENSIONS: Final = frozenset({".jpg", ".jpeg", ".png", ".gif"})


def _is_excluded_binary_attachment(document_name: str, *, is_primary: bool) -> bool:
    """Ticket 70: skip fetching/storing raster-image exhibits by default.

    Live-evidenced motivation: one filing (0000719220-26-000090) attached 24
    investor-presentation JPGs alongside its 5 real documents -- ~83% of that
    filing's fetch time for content none of this repo's parsers (ownership
    XML, ADV, Item 5.02 8-K, XBRL) read. The primary document is never
    excluded, regardless of its extension -- this only trims secondary
    binary exhibits.
    """
    if is_primary:
        return False
    if "." not in document_name:
        return False
    extension = "." + document_name.rsplit(".", 1)[1].lower()
    return extension in _EXCLUDED_BINARY_EXTENSIONS


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


def _raw_object_still_present(storage_path: str | None, *, existing_bronze_keys: set[str]) -> bool:
    """Confirm a raw_object's S3 content is actually present -- Ticket 88, corrected scope.

    ``existing_bronze_keys`` is a per-accession glob (cheap, one LIST call,
    same cost regardless of attachment count) and covers the common case: a
    document captured under its own accession's prefix. But sec_raw_object
    intentionally deduplicates identical content across *different*
    accessions (silver_protection.py's provenance_columns design -- shared
    boilerplate like report.css/Show.js is the dominant case, confirmed live
    to affect ~17% of all sec_filing_attachment rows). A storage_path that
    legitimately lives under a sibling accession's prefix will never appear
    in this accession's own glob result, so falling back to a direct,
    single-object existence check (not another LIST) is required before
    concluding the object is actually missing and paying for a full,
    unnecessary SEC re-fetch.
    """
    if not storage_path:
        return False
    if storage_path in existing_bronze_keys:
        return True
    return object_exists(storage_path)


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


def get_filing_by_cik_and_accession(cik: int, accession_number: str) -> Any | None:
    """CIK-scoped filing lookup -- ticket 96's replacement for edgar.get_by_accession_number.

    edgar.get_by_accession_number resolves an accession by scanning SEC's
    whole-market quarterly filing index (every registrant's filings that
    quarter), starting at Q1 every time, cached only 8-deep. Under a batch
    spanning many CIKs/years that cache thrashes, forcing repeated large
    index downloads on a too-short timeout (see module-level configure_http
    call above). This instead searches only the known CIK's own submissions
    data via edgar.Company, which this call site already has resolved.

    No fallback to the whole-market path on a miss -- an accession genuinely
    absent from its own CIK's submissions is a data-quality signal worth
    surfacing, not something to paper over by resurrecting the expensive scan.
    """
    filings = edgar.Company(cik).get_filings(accession_number=accession_number)
    if filings is None or filings.empty:
        return None
    return filings.get(accession_number)


def fetch_filing_artifacts(
    *,
    context: Any,
    db: Any,
    accession_number: str,
    sync_run_id: str,
    download_bytes=None,
    get_filing=None,
    force: bool = False,
    operator: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Fetch and register filing documents/attachments for one accession.

    ``get_filing`` supplies metadata only. ``download_bytes`` must fetch the
    canonical attachment URL through the repository-owned raw SEC gateway;
    its bytes are persisted unchanged.
    """
    if download_bytes is None:
        from edgar_warehouse.infrastructure.filing_content_gateway import (
            download_filing_content_bytes,
        )

        download_bytes = download_filing_content_bytes

    filing = db.get_filing(accession_number)
    if filing is None:
        raise ValueError(f"Unknown accession_number {accession_number}")

    cik = int(filing["cik"])
    if get_filing is None:
        get_filing = lambda accession: get_filing_by_cik_and_accession(cik, accession)  # noqa: E731
    capture_specs = default_capture_spec_factory()
    # Count real SEC network fetches so the orchestrator can skip its per-accession
    # rate-limit sleep on the idempotent cache-hit path (immutable, already-captured
    # artifacts). See CLAUDE.md artifact-throttle 5-whys.
    network_fetches = 0
    existing_rows = db.get_filing_attachments(accession_number)
    # Ticket 88: a sec_raw_object DB row is not proof the S3 object it points at
    # still exists (confirmed live: 494 of Apple's 1,044 rows pointed at objects
    # that were never durably present). One LIST per accession (not a HEAD per
    # attachment, matching ticket 75's precedent) so trusting a cache hit costs
    # the same regardless of attachment count. Only meaningful when there is a
    # cache to verify -- under force, or with no existing rows, no DB row is
    # ever trusted as a cache hit anyway, so skip the LIST entirely (a cold
    # load_history accession must not pay it -- see the artifact-throttle 5-whys
    # this same file already documents).
    existing_bronze_keys: set[str] = set()
    if existing_rows and not force:
        existing_bronze_keys = set(
            context.bronze_root.find_existing(
                capture_specs.filing_document_glob(cik=cik, accession_number=accession_number)
            )
        )
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
            db, existing_rows, existing_bronze_keys=existing_bronze_keys
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

    # Always discover the complete attachment set through edgartools. Content
    # bytes are fetched below, one canonical document URL at a time.
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

    excluded_binary_rows = [
        row
        for row in attachment_rows
        if _is_excluded_binary_attachment(row["document_name"], is_primary=bool(row.get("is_primary")))
    ]
    if excluded_binary_rows:
        attachment_rows = [row for row in attachment_rows if row not in excluded_binary_rows]
        _emit_artifact_event(
            "binary_attachments_excluded",
            accession_number=accession_number,
            document_names=[row["document_name"] for row in excluded_binary_rows],
            count=len(excluded_binary_rows),
        )

    # Ticket 77: cache-hit resolution stays sequential (cheap DB reads, no
    # network) so it runs first and determines which documents actually need
    # a real fetch. Only the real fetches — the loop's dominant cost — go
    # through the worker pool below.
    cache_hit_by_index: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    pending: list[dict[str, Any]] = []
    for index, row in enumerate(attachment_rows):
        document_name = row["document_name"]
        document_url = row["document_url"]
        prior_raw = prior_raw_by_document.get(document_name)
        existing_raw = None
        if row.get("raw_object_id"):
            existing_raw = db.get_raw_object(str(row["raw_object_id"]))
        if existing_raw is None and prior_raw is not None:
            existing_raw = prior_raw
        if (
            not force
            and existing_raw is not None
            and not _raw_object_still_present(
                existing_raw.get("storage_path"), existing_bronze_keys=existing_bronze_keys
            )
        ):
            # Ticket 88: DB row present but its S3 object isn't -- treat as a
            # real miss so the pending-fetch path below re-downloads it,
            # rather than trusting a dangling pointer. Gated on `not force`:
            # already_downloaded is unconditionally False under force anyway,
            # so there's no reason to pay for (or risk) the presence check
            # when its result will be discarded.
            existing_raw = None
        already_downloaded = (not force) and existing_raw is not None
        if already_downloaded:
            _emit_artifact_event(
                "artifact_storage_cache_hit",
                accession_number=accession_number,
                document_name=document_name,
            )
            hydrated = {key: value for key, value in row.items() if key != "content_bytes"}
            hydrated["raw_object_id"] = existing_raw.get("raw_object_id")
            cache_hit_by_index[index] = (hydrated, _cached_raw_record(existing_raw))
            continue

        artifact_spec = capture_specs.filing_document(
            cik=cik,
            accession_number=accession_number,
            document_name=document_name,
            is_primary=bool(row.get("is_primary")),
        )
        pending.append(
            {
                "index": index,
                "row": row,
                "document_url": document_url,
                "relative_path": artifact_spec.relative_path,
                "source_type": "filing_document" if row.get("is_primary") else "attachment",
            }
        )

    # Real fetches run concurrently. Each worker does network I/O + the
    # immutable S3 write only — no DuckDB access, since a single
    # SilverDatabase connection is not safe for concurrent use (ticket 03).
    # Results are collected here and every db.upsert_raw_object call happens
    # back on this thread, in the loop below.
    fetch_results: dict[int, dict[str, Any]] = {}
    fetch_errors: dict[int, BaseException] = {}
    if pending:
        worker_count = min(len(pending), _artifact_fetch_concurrency())
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_task = {
                executor.submit(
                    _fetch_and_store_attachment,
                    context=context,
                    download_bytes=download_bytes,
                    accession_number=accession_number,
                    document_name=task["row"]["document_name"],
                    document_url=task["document_url"],
                    relative_path=task["relative_path"],
                    source_type=task["source_type"],
                    cik=cik,
                    form=filing.get("form"),
                ): task
                for task in pending
            }
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    fetch_results[task["index"]] = future.result()
                except BaseException as exc:  # noqa: BLE001 — re-raised below, want the original type
                    fetch_errors[task["index"]] = exc

    network_fetches += len(fetch_results)
    applied_by_index: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for task in pending:
        index = task["index"]
        storage_record = fetch_results.get(index)
        if storage_record is None:
            continue
        row = task["row"]
        document_name = row["document_name"]
        prior_raw = prior_raw_by_document.get(document_name)
        db.upsert_raw_object(
            {key: value for key, value in storage_record.items() if key != "relative_path"}
        )
        raw_record = {
            "raw_object_id": storage_record["raw_object_id"],
            "path": storage_record["storage_path"],
            "relative_path": storage_record["relative_path"],
            "source_url": storage_record["source_url"],
            "source_type": storage_record["source_type"],
        }
        hydrated = dict(row)
        hydrated["raw_object_id"] = raw_record["raw_object_id"]
        applied_by_index[index] = (hydrated, raw_record)

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

    if fetch_errors:
        # Fail closed exactly as the sequential loop did: no partial merge.
        # Raise the original exception for the earliest-in-order failing
        # document so orchestrator error classification (transient / immutable
        # conflict) is unaffected by which order concurrent fetches finished in.
        first_failed_index = min(fetch_errors)
        raise fetch_errors[first_failed_index]

    raw_writes: list[dict[str, Any]] = []
    hydrated_rows: list[dict[str, Any]] = []
    for index in range(len(attachment_rows)):
        if index in cache_hit_by_index:
            hydrated, raw_record = cache_hit_by_index[index]
        else:
            hydrated, raw_record = applied_by_index[index]
        hydrated_rows.append(hydrated)
        raw_writes.append(raw_record)

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
    db: Any, rows: list[dict[str, Any]], *, existing_bronze_keys: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    hydrated_rows: list[dict[str, Any]] = []
    cached_records: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    for row in rows:
        raw_object_id = row.get("raw_object_id")
        raw_object = db.get_raw_object(str(raw_object_id)) if raw_object_id else None
        # Ticket 88: a DB row referencing an S3 key that isn't actually present
        # is functionally the same as no row at all -- both need a real fetch.
        if raw_object is not None and not _raw_object_still_present(
            raw_object.get("storage_path"), existing_bronze_keys=existing_bronze_keys
        ):
            raw_object = None
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


def _fetch_and_store_attachment(
    *,
    context: Any,
    download_bytes: Any,
    accession_number: str,
    document_name: str,
    document_url: str,
    relative_path: str,
    source_type: str,
    cik: int,
    form: str | None,
) -> dict[str, Any]:
    """Network fetch + immutable storage write for one attachment.

    Ticket 77: this is the unit of work each artifact-fetch pool thread runs.
    Deliberately does not touch ``db`` — a single SilverDatabase DuckDB
    connection is not safe for concurrent access, so every db.* call stays on
    the main thread (see the caller in ``fetch_filing_artifacts``).
    """
    started_at = time.monotonic()
    _emit_artifact_event(
        "artifact_content_fetch_started",
        accession_number=accession_number,
        document_name=document_name,
        url=document_url,
    )
    try:
        payload = download_bytes(document_url, context.identity)
    except Exception as exc:
        _emit_artifact_event(
            "artifact_content_fetch_failed",
            accession_number=accession_number,
            document_name=document_name,
            duration_ms=_elapsed_ms(started_at),
            error=exc.__class__.__name__,
        )
        raise
    if not isinstance(payload, bytes):
        raise TypeError(
            f"filing content gateway returned {type(payload).__name__}; expected bytes"
        )
    _emit_artifact_event(
        "artifact_content_fetch_completed",
        accession_number=accession_number,
        document_name=document_name,
        bytes=len(payload),
        duration_ms=_elapsed_ms(started_at),
    )
    return _store_raw_artifact_bytes(
        context=context,
        payload=payload,
        relative_path=relative_path,
        source_type=source_type,
        source_url=document_url,
        cik=cik,
        accession_number=accession_number,
        form=form,
    )


def _store_raw_artifact_bytes(
    *,
    context: Any,
    payload: bytes,
    relative_path: str,
    source_type: str,
    source_url: str,
    cik: int,
    accession_number: str,
    form: str | None,
) -> dict[str, Any]:
    """Write immutable content to storage and compute its record fields.

    Storage-only — no DuckDB access — safe to call from a worker thread.
    ``write_immutable_bytes`` is itself idempotent for byte-identical content
    (create-once, verify-and-reuse on conflict), so a retried accession that
    re-runs this for an already-written document is safe.
    """
    destination = context.bronze_root.write_immutable_bytes(relative_path, payload)
    sha256 = hashlib.sha256(payload).hexdigest()
    content_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
    fetched_at = datetime.now(UTC)
    return {
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
        "relative_path": relative_path,
    }


def _map_edgartools_attachments(filing_obj: Any, accession_number: str) -> list[dict[str, Any]]:
    """Map edgartools filing metadata onto this module's attachment rows.

    is_primary is derived via membership in attachments.primary_documents rather
    than string-matching a primary_document name — more general, since a filing
    can have an unusual primary document that isn't html/xml.
    """
    primary_documents = list(filing_obj.attachments.primary_documents)
    rows: list[dict[str, Any]] = []
    for attachment in filing_obj.attachments:
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
            }
        )
    return rows
