"""Filing artifact fetch and attachment registration helpers."""

from __future__ import annotations

import hashlib
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def fetch_filing_artifacts(
    *,
    context: Any,
    db: Any,
    accession_number: str,
    sync_run_id: str,
    download_bytes,
    force: bool = False,
) -> dict[str, Any]:
    filing = db.get_filing(accession_number)
    if filing is None:
        raise ValueError(f"Unknown accession_number {accession_number}")

    cik = int(filing["cik"])
    accession_digits = accession_number.replace("-", "")
    index_url = _build_filing_index_url(cik, accession_digits)
    index_file_name = f"{accession_digits}-index.html"
    index_relative_path = (
        f"filings/sec/cik={cik}/accession={accession_number}/index/{index_file_name}"
    )
    index_bytes = download_bytes(index_url, context.identity)
    index_record = _write_raw_artifact(
        context=context,
        db=db,
        payload=index_bytes,
        relative_path=index_relative_path,
        source_type="filing_index",
        source_url=index_url,
        cik=cik,
        accession_number=accession_number,
        form=filing.get("form"),
    )

    attachment_rows = _extract_attachment_rows(
        index_html=index_bytes.decode("utf-8", errors="replace"),
        base_url=index_url,
        accession_number=accession_number,
        primary_document=filing.get("primary_document"),
    )
    if not attachment_rows and filing.get("primary_document"):
        attachment_rows = [
            {
                "accession_number": accession_number,
                "document_name": filing["primary_document"],
                "document_type": filing.get("form"),
                "document_url": _build_filing_document_url(cik, accession_digits, filing["primary_document"]),
                "is_primary": True,
            }
        ]

    raw_writes = [index_record]
    hydrated_rows: list[dict[str, Any]] = []
    for row in attachment_rows:
        already_downloaded = (not force) and row.get("raw_object_id")
        if already_downloaded:
            hydrated_rows.append(row)
            continue
        document_url = row["document_url"]
        document_name = row["document_name"]
        relative_path = _artifact_relative_path(
            cik=cik,
            accession_number=accession_number,
            document_name=document_name,
            is_primary=bool(row.get("is_primary")),
        )
        payload = download_bytes(document_url, context.identity)
        raw_record = _write_raw_artifact(
            context=context,
            db=db,
            payload=payload,
            relative_path=relative_path,
            source_type="filing_document" if row.get("is_primary") else "attachment",
            source_url=document_url,
            cik=cik,
            accession_number=accession_number,
            form=filing.get("form"),
        )
        raw_writes.append(raw_record)
        hydrated = dict(row)
        hydrated["raw_object_id"] = raw_record["raw_object_id"]
        hydrated_rows.append(hydrated)

    db.merge_filing_attachments(hydrated_rows, sync_run_id)
    return {
        "accession_number": accession_number,
        "attachment_count": len(hydrated_rows),
        "raw_writes": raw_writes,
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


def _extract_attachment_rows(
    *,
    index_html: str,
    base_url: str,
    accession_number: str,
    primary_document: str | None,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(index_html, "html.parser")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for table_row in soup.find_all("tr"):
        cells = table_row.find_all("td")
        if len(cells) < 3:
            continue
        links = table_row.find_all("a")
        if not links:
            continue
        link = links[0]
        href = link.get("href")
        if not href:
            continue
        document_url = urljoin(base_url, href)
        document_name = Path(href).name
        if not document_name or document_name in seen:
            continue
        seen.add(document_name)
        sequence_number = cells[0].get_text(" ", strip=True) if cells else None
        document_type = cells[3].get_text(" ", strip=True) if len(cells) > 3 else None
        description = cells[1].get_text(" ", strip=True) if len(cells) > 1 else None
        rows.append(
            {
                "accession_number": accession_number,
                "sequence_number": sequence_number or None,
                "document_name": document_name,
                "document_type": document_type or Path(document_name).suffix.lstrip(".").upper() or "DOCUMENT",
                "document_description": description or None,
                "document_url": document_url,
                "is_primary": document_name == primary_document,
            }
        )

    return rows


def _artifact_relative_path(
    *,
    cik: int,
    accession_number: str,
    document_name: str,
    is_primary: bool,
) -> str:
    section = "primary" if is_primary else "attachments"
    return f"filings/sec/cik={cik}/accession={accession_number}/{section}/{document_name}"


def _build_filing_index_url(cik: int, accession_digits: str) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik}/{accession_digits}/{accession_digits}-index.html"
    )


def _build_filing_document_url(cik: int, accession_digits: str, document_name: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_digits}/{document_name}"
