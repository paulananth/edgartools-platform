"""SEC HTTP client with host validation and response-size limits."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import urlparse

from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate

from edgar_warehouse.application.errors import WarehouseRuntimeError

DEFAULT_MAX_RESPONSE_BYTES = 50 * 1024 * 1024
ALLOWED_HOSTS = frozenset({"www.sec.gov", "sec.gov", "data.sec.gov"})


def _create_sec_rate_limiter() -> Limiter:
    # 9 req/sec matches EDGAR_RATE_LIMIT_PER_SEC (edgartools default).
    # In-process only — does not coordinate across ECS tasks.
    rate = Rate(9, Duration.SECOND)
    bucket = InMemoryBucket([rate])
    try:
        return Limiter(bucket, max_delay=Duration.DAY, raise_when_fail=False, retry_until_max_delay=True)
    except TypeError:
        return Limiter(bucket)


_SEC_RATE_LIMITER: Limiter = _create_sec_rate_limiter()


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
    _SEC_RATE_LIMITER.try_acquire("sec_download")
    last_error: Exception | None = None
    headers = {"Accept": "*/*", "User-Agent": identity}
    timeout = httpx.Timeout(30.0, connect=10.0)
    max_response_bytes = int(os.environ.get("WAREHOUSE_SEC_MAX_RESPONSE_BYTES", DEFAULT_MAX_RESPONSE_BYTES))

    for attempt in range(1, 4):
        started_at = time.monotonic()
        _emit_sec_pull_event("sec_pull_started", url=url, attempt=attempt, max_attempts=3)
        try:
            with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                _validate_sec_url(str(response.url))
                if len(response.content) > max_response_bytes:
                    raise WarehouseRuntimeError(
                        f"SEC response exceeded size limit for {url}: {len(response.content)} bytes"
                    )
                _emit_sec_pull_event(
                    "sec_pull_completed",
                    url=url,
                    final_url=str(response.url),
                    attempt=attempt,
                    max_attempts=3,
                    status_code=response.status_code,
                    bytes=len(response.content),
                    duration_ms=_elapsed_ms(started_at),
                )
                return response.content
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code
            if status_code in {429, 500, 502, 503, 504} and attempt < 3:
                _emit_sec_pull_event(
                    "sec_pull_retry",
                    url=url,
                    attempt=attempt,
                    max_attempts=3,
                    status_code=status_code,
                    duration_ms=_elapsed_ms(started_at),
                )
                time.sleep(attempt * 10)
                continue
            _emit_sec_pull_event(
                "sec_pull_failed",
                url=url,
                attempt=attempt,
                max_attempts=3,
                status_code=status_code,
                duration_ms=_elapsed_ms(started_at),
            )
            raise WarehouseRuntimeError(f"SEC request failed for {url}: HTTP {status_code}") from exc
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < 3:
                _emit_sec_pull_event(
                    "sec_pull_retry",
                    url=url,
                    attempt=attempt,
                    max_attempts=3,
                    error=exc.__class__.__name__,
                    duration_ms=_elapsed_ms(started_at),
                )
                time.sleep(attempt)
                continue
            _emit_sec_pull_event(
                "sec_pull_failed",
                url=url,
                attempt=attempt,
                max_attempts=3,
                error=exc.__class__.__name__,
                duration_ms=_elapsed_ms(started_at),
            )
            raise WarehouseRuntimeError(f"SEC request failed for {url}: {exc}") from exc

    raise WarehouseRuntimeError(f"SEC request failed for {url}: {last_error}")


def _elapsed_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _emit_sec_pull_event(event: str, **payload: object) -> None:
    parsed = urlparse(str(payload.get("url", "")))
    document = {
        "event": event,
        "emitted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "host": parsed.netloc,
        "path": parsed.path,
        **payload,
    }
    print(json.dumps(document, sort_keys=True), file=sys.stderr, flush=True)


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


def build_companyfacts_url(cik: int) -> str:
    return f"{SecEndpointConfig.from_env().data_url}/api/xbrl/companyfacts/CIK{cik:010d}.json"


def build_filing_index_url(cik: int, accession_digits: str) -> str:
    return f"{SecEndpointConfig.from_env().archive_url}/data/{cik}/{accession_digits}/{accession_digits}-index.html"


def build_filing_document_url(cik: int, accession_digits: str, document_name: str) -> str:
    return f"{SecEndpointConfig.from_env().archive_url}/data/{cik}/{accession_digits}/{document_name}"


def _validate_sec_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise WarehouseRuntimeError(f"SEC request host is not allowlisted: {host or url}")
