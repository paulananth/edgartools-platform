"""Normalized text extraction helpers for filing primary documents."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from edgar_warehouse.infrastructure.dataset_path_catalog import default_capture_spec_factory
from edgar_warehouse.infrastructure.object_storage import object_exists, read_bytes


def _resolve_primary_storage_path(
    *, context: Any, db: Any, cik: int, accession_number: str
) -> tuple[str | None, str | None]:
    """Return (storage_path, document_name) for the accession's primary document.

    A raw_object DB row is not proof the S3 object it points at still exists
    (release-readiness ticket 88 -- confirmed live for a real accession).
    Verifies via one S3 LIST of the accession's document prefix before
    trusting the row, same guard `fetch_filing_artifacts` applies -- falling
    back to a direct existence check on the row's own storage_path when it
    isn't in that LIST, since sec_raw_object legitimately deduplicates
    identical content across different accessions' prefixes (see
    bronze_filing_artifacts.py's _raw_object_still_present).
    """
    attachments = db.get_filing_attachments(accession_number)
    primary = next((row for row in attachments if row.get("is_primary")), None)
    if not primary or not primary.get("raw_object_id"):
        return None, None
    raw_object = db.get_raw_object(primary["raw_object_id"])
    if raw_object is None:
        return None, None
    existing_keys = set(
        context.bronze_root.find_existing(
            default_capture_spec_factory().filing_document_glob(
                cik=cik, accession_number=accession_number
            )
        )
    )
    storage_path = raw_object["storage_path"]
    if storage_path not in existing_keys and not object_exists(storage_path):
        return None, None
    return storage_path, primary["document_name"]


def extract_text_for_accession(
    *,
    context: Any,
    db: Any,
    accession_number: str,
    sync_run_id: str,
    text_version: str = "generic_text_v1",
) -> dict[str, Any]:
    filing = db.get_filing(accession_number)
    if filing is None:
        raise ValueError(f"Unknown accession_number {accession_number}")
    cik = int(filing["cik"])
    source_document_name = filing.get("primary_document")
    storage_path, resolved_document_name = _resolve_primary_storage_path(
        context=context, db=db, cik=cik, accession_number=accession_number
    )
    if storage_path is None:
        # Ticket 88: no row, or a row pointing at an absent S3 object -- self-heal
        # by reusing fetch_filing_artifacts's own (now S3-verified) fetch/cache
        # logic rather than duplicating it here, then re-resolve.
        from edgar_warehouse.infrastructure.filing_artifact_service import (
            refresh_filing_artifacts,
        )

        refresh_filing_artifacts(
            context=context,
            db=db,
            accession_number=accession_number,
            sync_run_id=sync_run_id,
            force=False,
        )
        storage_path, resolved_document_name = _resolve_primary_storage_path(
            context=context, db=db, cik=cik, accession_number=accession_number
        )
    if resolved_document_name is not None:
        source_document_name = resolved_document_name
    if storage_path is None:
        raise ValueError(f"No primary raw artifact registered for {accession_number}")

    payload = read_bytes(storage_path)
    normalized_text = _normalize_text(payload=payload, source_document_name=source_document_name or "")
    output_spec = default_capture_spec_factory().text_output(cik, accession_number, text_version)
    destination = context.storage_root.write_text(output_spec.relative_path, normalized_text)
    row = {
        "accession_number": accession_number,
        "text_version": text_version,
        "source_document_name": source_document_name or accession_number,
        "text_storage_path": destination,
        "text_sha256": hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        "char_count": len(normalized_text),
        "extracted_at": datetime.now(UTC),
    }
    db.upsert_filing_text(row)
    return row

def _normalize_text(*, payload: bytes, source_document_name: str) -> str:
    suffix = Path(source_document_name).suffix.lower()
    if suffix in {".htm", ".html"}:
        soup = BeautifulSoup(payload.decode("utf-8", errors="replace"), "html.parser")
        text = soup.get_text("\n")
    elif suffix == ".xml":
        soup = BeautifulSoup(payload.decode("utf-8", errors="replace"), "xml")
        text = soup.get_text("\n")
    else:
        text = payload.decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"
