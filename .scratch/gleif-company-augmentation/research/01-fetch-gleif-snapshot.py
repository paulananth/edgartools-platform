#!/usr/bin/env python3
"""Download and hash one pinned same-publication GLEIF Golden Copy set.

Archives are retained compressed and never extracted.  Each response is streamed
in 1 MiB chunks so peak local disk is the compressed corpus plus one chunk.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLICATION = "2026-09-11 16:00:00"
MAX_PEAK_BYTES = 3 * 1024**3
MIN_REMAINING_BYTES = 4 * 1024**3
FILES = [
    {
        "family": "lei2",
        "cdf_version": "LEI_3.1",
        "record_count": 3_428_477,
        "declared_size": 927_550_946,
        "url": "https://leidata-preview.gleif.org/storage/golden-copy-files/2026/09/11/1275137/20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip",
    },
    {
        "family": "rr",
        "cdf_version": "RR_2.1",
        "record_count": 487_721,
        "declared_size": 34_953_042,
        "url": "https://leidata-preview.gleif.org/storage/golden-copy-files/2026/09/11/1275182/20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip",
    },
    {
        "family": "repex",
        "cdf_version": "REPEX_2.1",
        "record_count": 6_351_397,
        "declared_size": 63_719_264,
        "url": "https://leidata-preview.gleif.org/storage/golden-copy-files/2026/09/11/1275227/20260911-1600-gleif-goldencopy-repex-golden-copy.json.zip",
    },
]


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def request(url: str, method: str = "GET") -> urllib.request.Request:
    return urllib.request.Request(
        url,
        method=method,
        headers={"User-Agent": "EdgarTools GLEIF research ticket-01"},
    )


def main() -> None:
    expected = sum(item["declared_size"] for item in FILES)
    free_before = shutil.disk_usage(ROOT).free
    if expected > MAX_PEAK_BYTES:
        raise RuntimeError(f"expected compressed peak {expected} exceeds 3 GiB gate")
    if free_before - expected < MIN_REMAINING_BYTES:
        raise RuntimeError(
            f"download would leave less than 4 GiB free: free={free_before}, expected={expected}"
        )

    retrieval_started = now_utc()
    artifacts = []
    for item in FILES:
        url = item["url"]
        with urllib.request.urlopen(request(url, "HEAD"), timeout=60) as response:
            head_status = response.status
            content_length = int(response.headers.get("Content-Length", "0"))
            content_type = response.headers.get("Content-Type")
            etag = response.headers.get("ETag")
            last_modified = response.headers.get("Last-Modified")
        if head_status != 200 or content_length != item["declared_size"]:
            raise RuntimeError(
                f"HEAD mismatch for {item['family']}: status={head_status}, "
                f"content_length={content_length}, declared={item['declared_size']}"
            )

        target = ROOT / ("01-" + url.rsplit("/", 1)[-1])
        partial = target.with_suffix(target.suffix + ".part")
        digest = hashlib.sha256()
        downloaded = 0
        with urllib.request.urlopen(request(url), timeout=300) as response, partial.open("wb") as handle:
            if response.status != 200:
                raise RuntimeError(f"GET {url} returned {response.status}")
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if downloaded % (128 * 1024 * 1024) < len(chunk):
                    print(f"{item['family']}: {downloaded}/{content_length}", flush=True)
            handle.flush()
            os.fsync(handle.fileno())
        if downloaded != content_length:
            raise RuntimeError(
                f"GET length mismatch for {item['family']}: {downloaded} != {content_length}"
            )
        partial.replace(target)
        artifacts.append(
            {
                **item,
                "format": "json.zip",
                "head_status": head_status,
                "content_length": content_length,
                "content_type": content_type,
                "etag": etag,
                "last_modified": last_modified,
                "local_file": target.name,
                "downloaded_size": downloaded,
                "sha256": digest.hexdigest(),
                "retrieved_at_utc": now_utc(),
            }
        )
        print(f"{item['family']}: complete sha256={digest.hexdigest()}", flush=True)

    manifest = {
        "manifest_version": "gleif-golden-copy-freeze-v1",
        "discovery_endpoint": "https://leidata-preview.gleif.org/api/v2/golden-copies/publishes?page=1&per_page=1",
        "official_download_page": "https://www.gleif.org/en/lei-data/gleif-golden-copy/download-the-golden-copy",
        "publication_utc": PUBLICATION,
        "retrieval_started_at_utc": retrieval_started,
        "retrieval_completed_at_utc": now_utc(),
        "download_mode": "streamed compressed archives; no extraction",
        "free_bytes_before": free_before,
        "free_bytes_after": shutil.disk_usage(ROOT).free,
        "expected_compressed_bytes": expected,
        "files": artifacts,
    }
    encoded = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (ROOT / "01-gleif-snapshot-manifest.json").write_bytes(encoded)
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
