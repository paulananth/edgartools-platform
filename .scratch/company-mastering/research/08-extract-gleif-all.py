"""Ticket 08: every GLEIF Level 1 record, with the fields a matching rule reads.

Streams the pinned Golden Copy (2026-09-11 16:00 UTC, sha256 1b6cd9cd...a36a6a,
re-hashed first) with ticket 02's fail-closed record streamer, and writes one
compact line per LEI: legal and other names, category, legal form,
jurisdiction, statuses, successor, legal and headquarters addresses. No
network. The output (about 1.5 GB) stays outside the repo.

    uv run --with orjson --with rapidfuzz python \\
        .scratch/company-mastering/research/08-extract-gleif-all.py <lei2.json.zip> <out.jsonl>
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GLEIF = HERE.parent.parent / "gleif-company-augmentation" / "research"
_spec = importlib.util.spec_from_file_location("t02", GLEIF / "02-compare-gleif-identities.py")
t02 = importlib.util.module_from_spec(_spec)
sys.modules["t02"] = t02  # its dataclasses look their module up by name
_spec.loader.exec_module(t02)

SHA256 = "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a"
RECORDS = 3_428_477
scalar, as_list = t02.scalar, t02.as_list


def address(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    lines = [scalar(raw.get("FirstAddressLine"))]
    lines += [scalar(x) for x in as_list(raw.get("AdditionalAddressLine"))]
    return {
        "lines": [x for x in lines if x],
        "city": scalar(raw.get("City")),
        "region": scalar(raw.get("Region")),
        "country": scalar(raw.get("Country")),
        "postal": scalar(raw.get("PostalCode")),
    }


def names(entity: dict) -> list[list[str]]:
    out = []
    for item in as_list((entity.get("OtherEntityNames") or {}).get("OtherEntityName")):
        if isinstance(item, dict) and scalar(item):
            out.append([item.get("@type") or "OTHER", scalar(item)])
    for item in as_list(
        (entity.get("TransliteratedOtherEntityNames") or {}).get("TransliteratedOtherEntityName")
    ):
        if isinstance(item, dict) and scalar(item):
            out.append([item.get("@type") or "TRANSLITERATED", scalar(item)])
    return out


def row(record: dict) -> dict:
    ent = record.get("Entity") or {}
    reg = record.get("Registration") or {}
    successor = ent.get("SuccessorEntity") or {}
    return {
        "lei": scalar(record.get("LEI")),
        "legal_name": scalar(ent.get("LegalName")),
        "other_names": names(ent),
        "category": scalar(ent.get("EntityCategory")),
        "legal_form": scalar((ent.get("LegalForm") or {}).get("EntityLegalFormCode")),
        "jurisdiction": scalar(ent.get("LegalJurisdiction")),
        "entity_status": scalar(ent.get("EntityStatus")),
        "registration_status": scalar(reg.get("RegistrationStatus")),
        "successor_lei": scalar(successor.get("SuccessorLEI")) if isinstance(successor, dict) else None,
        "legal": address(ent.get("LegalAddress")),
        "hq": address(ent.get("HeadquartersAddress")),
    }


def main(archive: str, out_path: str) -> None:
    h = hashlib.sha256()
    with open(archive, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != SHA256:
        raise SystemExit(f"archive sha256 {h.hexdigest()} is not the pinned {SHA256}")
    started = time.monotonic()
    proc = subprocess.Popen(["unzip", "-p", archive], stdout=subprocess.PIPE)
    seen = 0
    with open(out_path, "w") as out:
        for record in t02.stream_pretty_printed_records(proc.stdout):
            out.write(json.dumps(row(record), separators=(",", ":")) + "\n")
            seen += 1
            if seen % 500_000 == 0:
                print(f"{seen:,} {time.monotonic() - started:.0f}s", file=sys.stderr, flush=True)
            if seen == RECORDS:
                break
    proc.stdout.close()
    proc.terminate()
    proc.wait()
    if seen != RECORDS:
        raise SystemExit(f"read {seen} records, the publication declares {RECORDS}")
    print(json.dumps({"records": seen, "archive_sha256": SHA256,
                      "seconds": round(time.monotonic() - started)}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
