"""Infrastructure service wrappers for artifact and text workflows."""

from __future__ import annotations

from typing import Any

from edgar_warehouse.artifacts import fetch_filing_artifacts
from edgar_warehouse.text_extraction import extract_text_for_accession


def refresh_filing_artifacts(*, context: Any, db: Any, accession_number: str, sync_run_id: str, download_bytes, force: bool) -> dict[str, Any]:
    return fetch_filing_artifacts(
        context=context,
        db=db,
        accession_number=accession_number,
        sync_run_id=sync_run_id,
        download_bytes=download_bytes,
        force=force,
    )


def extract_filing_text(*, context: Any, db: Any, accession_number: str, text_version: str = "generic_text_v1") -> dict[str, Any]:
    return extract_text_for_accession(
        context=context,
        db=db,
        accession_number=accession_number,
        text_version=text_version,
    )
