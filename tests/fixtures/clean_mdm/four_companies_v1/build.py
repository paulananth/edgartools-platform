"""Rebuild four_companies_v1.json from retained bronze and the GLEIF golden copy.

Zero SEC requests: the SEC inputs are the platform's own bronze submissions
objects, read from S3 (or a local copy of them). The GLEIF inputs are the four
Level 1 records whose LegalName equals one of the four names exactly, streamed
from the golden copy pinned in
.scratch/gleif-company-augmentation/research/01-gleif-snapshot-manifest.json.

The four Companies were **picked by the operator**, and their GLEIF records by
exact legal name. That is test selection, not matching evidence: nothing here
says an SEC record and a GLEIF record are the same Company.

Usage: python build.py <dir holding the bronze JSON files> <golden copy zip>
"""

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import ijson

from edgar_warehouse.loaders.bronze_submission_extractors import stage_company_loader

BRONZE = {
    "0000320193": "cik=320193/main/2026/07/02/CIK0000320193.json",
    "0000789019": "cik=789019/main/2026/07/02/CIK0000789019.json",
    "0001306965": "cik=1306965/main/2026/07/02/CIK0001306965.json",
    "0000937966": "cik=937966/main/2026/06/27/CIK0000937966.json",
    # Controls: two individual filers, SEC entityType "other" like Shell and ASML.
    "0001214156": "cik=1214156/main/2026/09/12/CIK0001214156.json",
    "0001513142": "cik=1513142/main/2026/09/02/CIK0001513142.json",
}
PREFIX = "s3://edgartools-prod-bronze-690839588395/warehouse/bronze/submissions/sec/"
NAMES = {"APPLE INC.", "MICROSOFT CORPORATION", "SHELL PLC", "ASML HOLDING N.V."}


def main(bronze_dir: str, golden_copy: str) -> None:
    sec, sources = [], {}
    for cik, key in BRONZE.items():
        raw = (Path(bronze_dir) / key.rsplit("/", 1)[1]).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        sources[PREFIX + key] = sha
        row = stage_company_loader(
            json.loads(raw), int(cik), "bronze-fixture", sha, "fixture"
        )[0]
        sec.append({**row, "last_sync_run_id": "bronze-fixture"})
    gleif = []
    with zipfile.ZipFile(golden_copy) as z, z.open(z.namelist()[0]) as f:
        for record in ijson.items(f, "records.item", use_float=True):
            if record["Entity"]["LegalName"]["$"].upper() in NAMES:
                gleif.append(record)
    if sorted(r["Entity"]["LegalName"]["$"].upper() for r in gleif) != sorted(NAMES):
        raise SystemExit("Expected exactly one golden-copy record per name")
    body = {
        "version": 1,
        "purpose": (
            "operator-picked Companies (AAPL, MSFT, Shell, ASML) plus two individual "
            "controls; test selection, not matching evidence"
        ),
        "sources": {
            **sources,
            "gleif_golden_copy": {
                "file": Path(golden_copy).name,
                "publication_utc": "2026-09-11 16:00:00",
                "sha256": "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a",
                "selection": "LegalName equals one of four names exactly",
            },
        },
        "sec": sec,
        "gleif": sorted(gleif, key=lambda r: r["LEI"]["$"]),
    }
    out = Path(__file__).with_name("four_companies_v1.json")
    out.write_text(
        json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
