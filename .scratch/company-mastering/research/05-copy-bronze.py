"""Ticket 05, step 2: copy the manifest's bronze documents to a local bronze root.

S3 reads only; zero SEC requests. Each submissions document goes to the same
relative path under the local root that it has under the prod bronze root,
so `bootstrap-batch` finds it as a cached capture. SEC's ticker catalog of
2026-09-02, the newest in bronze and the one ticket 12 measured the Company
rule with, is copied beside them. Writes one receipt line per object (key,
SHA-256, bytes) and refuses a catalog whose hash is not the pinned one.

    uv run --no-sync python .scratch/company-mastering/research/05-copy-bronze.py \\
        <05-manifest.json> <local-bronze-root> <receipts.jsonl>
"""

from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
from botocore.config import Config

BUCKET = "edgartools-prod-bronze-690839588395"
ROOT = "warehouse/bronze/"
CATALOG = ROOT + "reference/sec/company_tickers_exchange/2026/09/02/company_tickers_exchange.json"
CATALOG_SHA256_PREFIX = "836140c5"

s3 = boto3.client(
    "s3",
    region_name="us-east-1",
    config=Config(max_pool_connections=32, retries={"max_attempts": 8}),
)


def copy(key: str, local: Path) -> dict:
    if not key.startswith(ROOT):
        raise ValueError(f"not a bronze key: {key}")
    data = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    target = local / key[len(ROOT) :]
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != data:
        raise SystemExit(f"a different local copy already exists: {target}")
    target.write_bytes(data)
    return {"key": key, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def main(manifest: str, root: str, receipts: str) -> None:
    body = json.loads(Path(manifest).read_text())
    keys = [m["key"] for chunk in body["chunks"] for m in chunk]
    local = Path(root)
    catalog = copy(CATALOG, local)
    if not catalog["sha256"].startswith(CATALOG_SHA256_PREFIX):
        raise SystemExit(f"ticker catalog is not the pinned one: {catalog['sha256']}")
    with ThreadPoolExecutor(max_workers=24) as pool:
        rows = list(pool.map(lambda k: copy(k, local), keys))
    with open(receipts, "w") as out:
        out.writelines(json.dumps(row, sort_keys=True) + "\n" for row in [catalog, *sorted(rows, key=lambda r: r["key"])])
    print(
        json.dumps(
            {
                "documents": len(rows),
                "bytes": sum(r["bytes"] for r in rows),
                "catalog_sha256": catalog["sha256"],
            }
        )
    )


if __name__ == "__main__":
    main(*sys.argv[1:4])
