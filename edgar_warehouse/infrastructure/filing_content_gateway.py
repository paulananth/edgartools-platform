"""Byte-preserving SEC content gateway for immutable filing artifacts.

edgartools remains the source of filing and attachment metadata.  This
adapter deliberately uses the repository-owned client for document bodies so
bronze stores the exact archival response, not a library-normalized value.
"""

from __future__ import annotations

from typing import Final

from edgar_warehouse.infrastructure.sec_client import download_sec_bytes

FILING_DOCUMENT_CONTENT_GATEWAY: Final = "raw_sec_http"


def download_filing_content_bytes(url: str, identity: str) -> bytes:
    """Return the exact bytes served by the canonical SEC archival URL."""
    return download_sec_bytes(url, identity)
