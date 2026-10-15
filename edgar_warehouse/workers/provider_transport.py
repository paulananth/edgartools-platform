"""One bounded authorized GET, or POST of a frozen body (ticket 92); scheduling, retries and
receipts belong to callers."""
from __future__ import annotations

from dataclasses import dataclass
import time
from urllib.parse import unquote, urlparse

import httpx

SEC_HOSTS = frozenset({'www.sec.gov', 'sec.gov', 'data.sec.gov', 'reports.adviserinfo.sec.gov'})
MAX_BYTES = 128 * 1024**2


def approved_url(url: str, prefixes: list[str], capability: str) -> str:
    if not isinstance(url, str) or not url or any(ord(c) <= 32 for c in url):
        raise ValueError('Capture requires an explicit HTTPS URL')
    # Check before httpx normalizes literal dot segments away.
    raw_path = unquote(urlparse(url).path)
    if any(p in ('.', '..') for p in raw_path.split('/')) or '\\' in raw_path:
        raise ValueError('Capture URL has an unsupported authority or path')
    normalized = str(httpx.URL(url))
    parsed = urlparse(normalized)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.fragment or parsed.port not in (None, 443)
            or any(p in ('.', '..') for p in unquote(parsed.path).split('/'))
            or '\\' in unquote(parsed.path)):
        raise ValueError('Capture URL has an unsupported authority or path')
    def permits(prefix):
        approved = urlparse(prefix)
        # A textual hostname prefix must never authorize a different host.
        return (approved.scheme == 'https' and approved.hostname == parsed.hostname
                and approved.port in (None, 443) and not approved.username and not approved.password
                and not approved.fragment and normalized.startswith(str(httpx.URL(prefix))))
    if not any(permits(prefix) for prefix in prefixes):
        raise ValueError('Capture URL is outside frozen Rules authority')
    if capability == 'sec.conditional' and parsed.hostname not in SEC_HOSTS:
        raise ValueError('SEC capture requires an approved SEC host')
    if parsed.hostname in SEC_HOSTS and capability != 'sec.conditional':
        raise ValueError('SEC URLs require the SEC transport capability')
    return normalized


def provider_resource(url: str, capability: str) -> str:
    return 'provider:sec' if capability == 'sec.conditional' else f'provider:{urlparse(url).hostname}'


def validator(value):
    if value is not None and (not isinstance(value, str) or not value or len(value) > 8192
                              or any(ord(c) < 32 or ord(c) > 126 for c in value)):
        raise ValueError('Invalid conditional response validator')
    return value


@dataclass(frozen=True)
class Response:
    status: int
    content: bytes
    etag: str | None
    last_modified: str | None


def fetch(url: str, identity: str, *, max_bytes: int, requests_per_second: int,
          before_request, etag=None, last_modified=None, method='GET', body=None,
          extra_headers=None) -> Response:
    """A POST sends `body` with `extra_headers` (a key the caller read for this request
    only) and takes status 200 only; it is never conditional."""
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ValueError('Capture requires a supported explicit response byte bound')
    if type(requests_per_second) is not int or not 1 <= requests_per_second <= 9:
        raise ValueError('Capture rate must be an exact integer from 1 to 9')
    if not isinstance(identity, str) or not identity or any(ord(c) < 32 or ord(c) > 126 for c in identity):
        raise ValueError('Capture requires a printable User-Agent')
    if method not in ('GET', 'POST') or (method == 'POST') != (body is not None):
        raise ValueError('Capture is a GET, or a POST with its frozen body')
    if method == 'POST' and (etag is not None or last_modified is not None):
        raise ValueError('A POST capture is never conditional')
    headers = {'User-Agent': identity, 'Accept': '*/*', **(extra_headers or {})}
    if validator(etag) is not None:
        headers['If-None-Match'] = etag
    if validator(last_modified) is not None:
        headers['If-Modified-Since'] = last_modified
    # A shared provider lease remains held through this minimum request period.
    # Separate worker processes therefore cannot reset an in-memory rate bucket.
    # A killed process retains its lease until expiry. No network retry is hidden here.
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        before_request()
        started = time.monotonic()
        try:
            with client.stream(method, url, headers=headers, content=body) as response:
                if response.status_code not in ((200, 304) if method == 'GET' else (200,)):
                    raise ValueError('Provider did not return 200 or conditional 304')
                found_etag = validator(response.headers.get('etag'))
                modified = validator(response.headers.get('last-modified'))
                if response.status_code == 304:
                    if etag is None and last_modified is None:
                        raise ValueError('Unsolicited 304 has no verified conditional predecessor')
                    return Response(304, b'', found_etag or etag, modified or last_modified)
                chunks, size = [], 0
                for chunk in response.iter_bytes(chunk_size=65536):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError('Provider response exceeds its approved byte bound')
                    chunks.append(chunk)
                return Response(200, b''.join(chunks), found_etag, modified)
        finally:
            time.sleep(max(0, 1 / requests_per_second - (time.monotonic() - started)))
