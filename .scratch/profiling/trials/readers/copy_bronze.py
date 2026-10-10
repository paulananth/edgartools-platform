"""Ticket 07: a read-only local copy of prod bronze objects for the proof's cohort.

    uv run python .scratch/profiling/trials/readers/copy_bronze.py <keys.txt> <out folder>

Operator ruling, 2026-10-09 09:10 ET: "Read-only prod bronze slice
(Recommended)". Only GET and HEAD requests are made; nothing in S3 changes. Each
object lands at <out>/<its key>, written to a temporary name first; an object
already copied is skipped, so a stopped copy resumes. COPY.json beside the
files lists each key with its size and sha256.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore.config import Config

BUCKET = "edgartools-prod-bronze-690839588395"
WORKERS = 32


def main(keys_file: Path, out: Path) -> None:
    keys = [k for k in keys_file.read_text().splitlines() if k]
    s3 = boto3.client("s3", config=Config(max_pool_connections=WORKERS, retries={"max_attempts": 8, "mode": "adaptive"}))
    started, done, failed = time.monotonic(), [], []

    def fetch(key: str) -> dict:
        dest = out / key
        if not dest.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            part = dest.with_name(dest.name + ".part")
            s3.download_file(BUCKET, key, str(part))
            os.replace(part, dest)
        body = dest.read_bytes()
        return {"key": key, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}

    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(fetch, k): k for k in keys}
        for n, future in enumerate(as_completed(futures), 1):
            try:
                done.append(future.result())
            except Exception as exc:  # noqa: BLE001 - recorded, and the copy is rerun to fetch it again
                failed.append({"key": futures[future], "error": type(exc).__name__})
            if n % 1000 == 0:
                print(f"{n}/{len(keys)} in {time.monotonic() - started:.0f}s", flush=True)
    done.sort(key=lambda d: d["key"])
    manifest = {"bucket": BUCKET, "objects": len(done), "bytes": sum(d["bytes"] for d in done),
                "seconds": round(time.monotonic() - started), "failed": failed, "files": done}
    (out / "COPY.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{len(done)} objects, {manifest['bytes'] / 1e9:.2f} GB in {manifest['seconds']}s; {len(failed)} failed")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
