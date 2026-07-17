"""Filing artifact fetch and attachment registration helpers."""

from __future__ import annotations

import hashlib
import mimetypes
from datetime import UTC, datetime
from typing import Any

import edgar

from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory
from edgar_warehouse.infrastructure.object_storage import read_bytes

# Forms whose substantive data lives in a SEPARATE (non-primary) attachment
# rather than the primary/cover document itself. The primary_document fast
# path below (EDGE-11 5-whys, 06-04) only ever registers the primary
# document — it never discovers secondary attachments. For 13F-HR/13F-HR-A,
# the primary document is just the cover page XML; holdings live in a
# distinct "INFORMATION TABLE" attachment that the fast path silently drops,
# so `run_bootstrap_thirteenf` never finds an infotable attachment to parse
# and every 13F-HR filing was skipped (sec_thirteenf_holding stayed empty
# despite the bronze filing record and cover-page document being present).
# These forms must always take the full edgartools attachment-discovery
# fallback path so every attachment (not just the primary one) is fetched
# and registered in sec_filing_attachment.
_MULTI_ATTACHMENT_FORMS = frozenset({"13F-HR", "13F-HR/A"})


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


def fetch_filing_artifacts(
    *,
    context: Any,
    db: Any,
    accession_number: str,
    sync_run_id: str,
    download_bytes,
    get_filing=edgar.get_by_accession_number,
    force: bool = False,
    operator: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
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
        hydrated_rows, cached_records, missing_rows = _split_existing_attachment_rows(db, existing_rows)
        if not missing_rows:
            return {
                "accession_number": accession_number,
                "attachment_count": len(hydrated_rows),
                "raw_writes": cached_records,
                "network_fetches": 0,
            }
        attachment_rows = hydrated_rows + missing_rows
        index_record = None
    else:
        # Fast path: if primary_document is known, skip the -index.html fetch.
        # The index page (www.sec.gov/Archives/.../{acc}-index.html) is rate-limited
        # and returns 503 under load, while direct document URLs return 200.
        # For SEC ownership filings the primary_document is often stored as
        # "xslXXX/filename.xml" — strip the XSLT subdirectory prefix to get the
        # raw XML that contains <ownershipDocument>.
        primary_doc = filing.get("primary_document") or ""
        raw_doc_name = _resolve_raw_document_name(primary_doc)
        index_record = None
        form_type = filing.get("form")

        if (
            raw_doc_name
            and not force
            and not _read_cached_index(db, accession_number)
            and form_type not in _MULTI_ATTACHMENT_FORMS
        ):
            doc_spec = capture_specs.filing_document(
                cik=cik,
                accession_number=accession_number,
                document_name=raw_doc_name,
                is_primary=True,
            )
            attachment_rows = [
                {
                    "accession_number": accession_number,
                    "document_name": raw_doc_name,
                    "document_type": filing.get("form"),
                    "document_url": doc_spec.source_url,
                    "is_primary": True,
                }
            ]
        else:
            # Fall back to edgartools when primary_document is unknown. edgartools
            # fetches the full SGML submission bundle in one request (rather than a
            # separate -index.html fetch plus N per-document fetches), and its own
            # retry budget survives the 503s that sec_client.py's fixed 3-attempt
            # retry does not — see docs/runbook.md smoke-test 503 investigation.
            filing_obj = get_filing(accession_number)
            network_fetches += 1
            if filing_obj is None:
                raise ValueError(f"edgartools could not resolve filing for accession {accession_number}")
            attachment_rows = _map_edgartools_attachments(filing_obj, accession_number)
            if not attachment_rows:
                raise ValueError(f"edgartools found no attachments for accession {accession_number}")

    raw_writes = [index_record] if index_record is not None else []
    hydrated_rows: list[dict[str, Any]] = []
    for row in attachment_rows:
        existing_raw = db.get_raw_object(str(row["raw_object_id"])) if row.get("raw_object_id") else None
        already_downloaded = (not force) and existing_raw is not None
        if already_downloaded:
            hydrated_rows.append(row)
            raw_writes.append(_cached_raw_record(existing_raw))
            continue
        document_url = row["document_url"]
        document_name = row["document_name"]
        artifact_spec = capture_specs.filing_document(
            cik=cik,
            accession_number=accession_number,
            document_name=document_name,
            is_primary=bool(row.get("is_primary")),
        )
        # edgartools fetches attachment content as part of resolving the filing
        # (see _map_edgartools_attachments); reuse it instead of a second HTTP
        # round-trip. The fast path (raw_doc_name known) has no pre-fetched
        # content and still fetches via download_bytes.
        payload = row.get("content_bytes")
        if payload is None:
            payload = download_bytes(document_url, context.identity)
            network_fetches += 1
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

        prior_raw = prior_raw_by_document.get(document_name)
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
    }
    if repair_audit:
        result["repair_audit"] = repair_audit
    return result


def _resolve_raw_document_name(primary_document: str) -> str:
    """Strip XSLT renderer subdirectory to get the raw filing XML name.

    SEC submissions list ownership docs as 'xslF345X06/primary_doc.xml'.
    The XSLT prefix is a rendering stylesheet; the actual <ownershipDocument>
    XML is the filename part at the root of the accession directory.
    Stripping the prefix lets us skip the -index.html fetch (which 503s under
    load) and go directly to the document URL.

    Returns the raw filename, or empty string if the pattern doesn't apply.
    """
    if not primary_document:
        return ""
    parts = primary_document.replace("\\", "/").split("/")
    if len(parts) >= 2 and parts[0].lower().startswith("xsl"):
        return "/".join(parts[1:])
    # No XSLT prefix — use as-is (already a raw document name)
    return primary_document


def _split_existing_attachment_rows(db: Any, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
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


def _read_cached_index(db: Any, accession_number: str) -> dict[str, Any] | None:
    for raw_object in db.get_raw_objects_for_accession(accession_number, "filing_index"):
        storage_path = raw_object.get("storage_path")
        if not storage_path:
            continue
        try:
            payload = read_bytes(str(storage_path))
        except Exception:
            continue
        return {
            "payload": payload,
            "write_record": _cached_raw_record(raw_object),
        }
    return None


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
        content = attachment.content
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content
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
