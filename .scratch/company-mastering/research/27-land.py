"""Ticket 27, step 3: land every SEC filer of the pinned bronze copy, offline.

`bootstrap-batch` is retired from the CLI (#738), and the configured
Bookkeeping path lands one CIK at a time through three databases. This lands
each chunk of `chunks.json` (77 chunks of at most 1,000: ticket 05's seven
cohort chunks first, then the rest of the population by CIK) through
the same production pieces `bootstrap-batch` used, with pagination off as in
ticket 05: the parser (`SilverLandingStore.stage_submission`, load mode
`bootstrap_batch`) and the landing writer (`write_landing_export`). Each
chunk is one capture with its own run manifest, which `mdm name-census` and
`mdm prepare-clean-company` read. Each document's sha256 is checked against
the copy's receipts first. Resumable: a chunk with a run manifest is skipped.
No network is used.

    uv run --no-sync python .scratch/company-mastering/research/27-land.py <first> <last>
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.serving.silver_landing_export import LandingExportBuffer
from edgar_warehouse.serving.silver_landing_writer import write_landing_export
from edgar_warehouse.silver_landing_store import SilverLandingStore

CAPTURE = Path.home() / ".local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230"
WORK = Path.home() / ".local/share/edgartools/clean-mdm/proving/cm27"
LANDING = WORK / "silver-landing"
BUSINESS_DATE = "2026-09-29"
PREFIX = "warehouse/bronze/"


def receipts() -> dict[str, str]:
    found = {}
    with open(CAPTURE / "receipts.jsonl") as f:
        for line in f:
            row = json.loads(line)
            if "key" in row:
                found[row["key"]] = row["sha256"]
    return found


def land(n: int, chunk: list[dict], hashes: dict[str, str]) -> dict:
    run_id = f"local-cm27-chunk{n}"
    buffer = LandingExportBuffer()
    store = SilverLandingStore(landing_export=buffer)
    for row in chunk:
        raw = (CAPTURE / "bronze" / row["key"].removeprefix(PREFIX)).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if sha != hashes[row["key"]]:
            raise SystemExit(f"{row['key']}: sha256 differs from the copy's receipt")
        store.stage_submission(
            cik=int(row["cik"]), main_payload=json.loads(raw), pagination_payloads=[],
            sync_run_id=run_id, raw_object_id=sha, load_mode="bootstrap_batch",
        )
    return write_landing_export(
        buffer, StorageLocation(str(LANDING)), run_id=run_id, business_date=BUSINESS_DATE,
        command_name="bootstrap-batch", environment_name="local", now=datetime.now(UTC),
    )


def main(first: int, last: int) -> None:
    chunks = json.loads((WORK / "chunks.json").read_text())["chunks"]
    hashes = receipts()
    base = LANDING / "manifests/workflow_name=silver_landing_bootstrap_batch" / f"business_date={BUSINESS_DATE}"
    for n in range(first, last + 1):
        if (base / f"run_id=local-cm27-chunk{n}/run_manifest.json").exists():
            continue
        started = datetime.now()
        counts = land(n, chunks[n - 1], hashes)
        print(json.dumps({"chunk": n, "filers": len(chunks[n - 1]), "counts": counts,
                          "seconds": round((datetime.now() - started).total_seconds(), 1)}), flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]))
