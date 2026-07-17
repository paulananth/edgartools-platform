"""Edgartools-backed SEC network gateway (tickets 06–07).

Phase-2 cutover: catalogs (tickers, submissions, daily index) and companyfacts
use edgartools HTTP (`edgar.httprequests`) rather than the parallel
``sec_client.download_sec_bytes`` stack.

Filing documents (ticket 06) are covered by ``bronze_filing_artifacts`` +
``FILING_DOCUMENT_NETWORK_GATEWAY``; they appear in the registry below so
architecture tests have one inventory of cut-over object classes.

Non-edgartools sources (IAPD ADV bulk, PCAOB bulk, operator FOIA drops) stay on
mandatory archive paths and must never be listed as edgartools-covered.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Final
from urllib.parse import urlparse

import edgar

from edgar_warehouse.application.errors import WarehouseRuntimeError

# Match sec_client host policy so the gateway does not widen allowed SEC hosts.
_ALLOWED_SEC_HOSTS: Final = frozenset({"www.sec.gov", "sec.gov", "data.sec.gov"})

# Architecture / operator contract marker (ticket 07).
CATALOG_AND_FACTS_NETWORK_GATEWAY: Final = "edgartools"

# Object classes whose SEC network I/O must go through edgartools-backed paths.
EDGARTOOLS_GATEWAY_OBJECT_CLASSES: Final = frozenset(
    {
        "filing_document",
        "filing_attachment",
        "company_tickers",
        "company_tickers_exchange",
        "submissions_main",
        "submissions_pagination",
        "daily_index",
        "companyfacts",
    }
)

# Sources edgartools cannot supply — always mandatory bronze/archive (ticket 01).
NON_EDGARTOOLS_OBJECT_CLASSES: Final = frozenset(
    {
        "iapd_adv_bulk",
        "pcaob_auditorsearch_bulk",
        "operator_foia_drop",
    }
)


def is_edgartools_gateway_class(object_class: str) -> bool:
    return str(object_class or "").strip() in EDGARTOOLS_GATEWAY_OBJECT_CLASSES


def is_non_edgartools_source(object_class: str) -> bool:
    return str(object_class or "").strip() in NON_EDGARTOOLS_OBJECT_CLASSES


def ensure_identity(identity: str) -> None:
    """Bind SEC User-Agent for edgartools HTTP (required by the library)."""
    text = (identity or "").strip()
    if not text:
        raise WarehouseRuntimeError("EDGAR identity is required for edgartools SEC gateway")
    edgar.set_identity(text)


def _validate_sec_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise WarehouseRuntimeError(f"SEC URL must use https: {url}")
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_SEC_HOSTS:
        raise WarehouseRuntimeError(f"SEC URL host not allowed: {host or url}")


def download_bytes(
    url: str,
    identity: str,
    *,
    download_file_fn: Callable[..., Any] | None = None,
) -> bytes:
    """Download SEC payload bytes via edgartools HTTP (not sec_client/httpx).

    Used by warehouse catalog paths (tickers, submissions, daily index) after
    silver/bronze skip checks fail open to network.
    """
    _validate_sec_url(url)
    ensure_identity(identity)
    from edgar.httprequests import download_file

    fetcher = download_file_fn or download_file
    try:
        content = fetcher(url)
    except WarehouseRuntimeError:
        raise
    except Exception as exc:
        raise WarehouseRuntimeError(f"SEC request failed for {url}: {exc}") from exc
    if content is None:
        raise WarehouseRuntimeError(f"SEC request returned empty body for {url}")
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    raise WarehouseRuntimeError(
        f"SEC request returned unsupported type {type(content)!r} for {url}"
    )


def download_json(
    url: str,
    identity: str,
    *,
    download_json_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Download and parse JSON via edgartools HTTP."""
    _validate_sec_url(url)
    ensure_identity(identity)
    if download_json_fn is not None:
        try:
            payload = download_json_fn(url)
        except WarehouseRuntimeError:
            raise
        except Exception as exc:
            raise WarehouseRuntimeError(f"SEC request failed for {url}: {exc}") from exc
        if not isinstance(payload, dict):
            raise WarehouseRuntimeError(f"SEC JSON for {url} was not an object")
        return payload
    raw = download_bytes(url, identity)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise WarehouseRuntimeError(f"SEC JSON parse failed for {url}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise WarehouseRuntimeError(f"SEC JSON for {url} was not an object")
    return parsed

def fetch_companyfacts_json(
    cik: int,
    identity: str,
    *,
    download_json_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Companyfacts for a CIK via edgartools URL builder + HTTP."""
    from edgar.urls import build_company_facts_url

    url = build_company_facts_url(int(cik))
    return download_json(url, identity, download_json_fn=download_json_fn)


def fetch_submissions_main_json(
    cik: int,
    identity: str,
    *,
    download_json_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    from edgar.urls import build_submissions_url

    url = build_submissions_url(int(cik))
    return download_json(url, identity, download_json_fn=download_json_fn)
