"""SEC HTTP client with host validation and response-size limits."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from edgar_warehouse.application.errors import WarehouseRuntimeError

DEFAULT_MAX_RESPONSE_BYTES = 50 * 1024 * 1024
ALLOWED_HOSTS = frozenset({"www.sec.gov", "sec.gov", "data.sec.gov"})


@dataclass(frozen=True)
class SecEndpointConfig:
    """Resolved SEC endpoint configuration."""

    base_url: str
    data_url: str
    environment_name: str

    @classmethod
    def from_env(cls) -> "SecEndpointConfig":
        environment_name = os.environ.get("WAREHOUSE_ENVIRONMENT", "").strip() or "local"
        base_url = os.environ.get("EDGAR_BASE_URL", "https://www.sec.gov").rstrip("/")
        data_url = os.environ.get("EDGAR_DATA_URL", "https://data.sec.gov").rstrip("/")
        if environment_name.lower() in {"prod", "production"}:
            if base_url != "https://www.sec.gov" or data_url != "https://data.sec.gov":
                raise WarehouseRuntimeError("SEC endpoint overrides are not allowed in production environments")
        return cls(base_url=base_url, data_url=data_url, environment_name=environment_name)

    @property
    def archive_url(self) -> str:
        return f"{self.base_url}/Archives/edgar"


def download_sec_bytes(url: str, identity: str) -> bytes:
    import httpx

    _validate_sec_url(url)
    last_error: Exception | None = None
    headers = {"Accept": "*/*", "User-Agent": identity}
    timeout = httpx.Timeout(30.0, connect=10.0)
    max_response_bytes = int(os.environ.get("WAREHOUSE_SEC_MAX_RESPONSE_BYTES", DEFAULT_MAX_RESPONSE_BYTES))

    for attempt in range(1, 4):
        try:
            with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                _validate_sec_url(str(response.url))
                if len(response.content) > max_response_bytes:
                    raise WarehouseRuntimeError(
                        f"SEC response exceeded size limit for {url}: {len(response.content)} bytes"
                    )
                return response.content
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code
            if status_code in {429, 500, 502, 503, 504} and attempt < 3:
                time.sleep(attempt)
                continue
            raise WarehouseRuntimeError(f"SEC request failed for {url}: HTTP {status_code}") from exc
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(attempt)
                continue
            raise WarehouseRuntimeError(f"SEC request failed for {url}: {exc}") from exc

    raise WarehouseRuntimeError(f"SEC request failed for {url}: {last_error}")


def build_company_tickers_url() -> str:
    return f"{SecEndpointConfig.from_env().base_url}/files/company_tickers.json"


def build_company_tickers_exchange_url() -> str:
    return f"{SecEndpointConfig.from_env().base_url}/files/company_tickers_exchange.json"


def build_daily_index_url(target_date: date) -> str:
    quarter = ((target_date.month - 1) // 3) + 1
    return f"{SecEndpointConfig.from_env().archive_url}/daily-index/{target_date.year}/QTR{quarter}/form.{target_date:%Y%m%d}.idx"


def build_submissions_url(cik: int) -> str:
    return f"{SecEndpointConfig.from_env().data_url}/submissions/CIK{cik:010d}.json"


def build_submission_pagination_url(file_name: str) -> str:
    return f"{SecEndpointConfig.from_env().data_url}/submissions/{file_name}"


def _validate_sec_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise WarehouseRuntimeError(f"SEC request host is not allowlisted: {host or url}")
