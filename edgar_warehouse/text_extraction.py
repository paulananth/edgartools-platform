"""Normalized text extraction helpers for filing primary documents."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


def extract_text_for_accession(
    *,
    context: Any,
    db: Any,
    accession_number: str,
    text_version: str = "generic_text_v1",
) -> dict[str, Any]:
    filing = db.get_filing(accession_number)
    if filing is None:
        raise ValueError(f"Unknown accession_number {accession_number}")
    attachments = db.get_filing_attachments(accession_number)
    primary = next((row for row in attachments if row.get("is_primary")), None)
    source_document_name = filing.get("primary_document")
    storage_path = None
    if primary and primary.get("raw_object_id"):
        raw_object = db.get_raw_object(primary["raw_object_id"])
        if raw_object is not None:
            storage_path = raw_object["storage_path"]
            source_document_name = primary["document_name"]
    if storage_path is None:
        raise ValueError(f"No primary raw artifact registered for {accession_number}")

    payload = _read_bytes(storage_path)
    normalized_text = _normalize_text(payload=payload, source_document_name=source_document_name or "")
    cik = int(filing["cik"])
    relative_path = f"text/sec/cik={cik}/accession={accession_number}/{text_version}.txt"
    destination = context.storage_root.write_text(relative_path, normalized_text)
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


def _read_bytes(storage_path: str) -> bytes:
    if "://" in storage_path:
        protocol = storage_path.split("://", 1)[0]
        import fsspec

        fs = fsspec.filesystem(protocol)
        with fs.open(storage_path, "rb") as handle:
            return handle.read()
    return Path(storage_path).read_bytes()


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
