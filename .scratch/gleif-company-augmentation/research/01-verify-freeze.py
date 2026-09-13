#!/usr/bin/env python3
"""Offline verification and cohort replay for GLEIF augmentation Ticket 01."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED = "gleif-company-augmentation-2026-09-11-v1"
QUOTAS = collections.OrderedDict(
    [
        ("relationship_evidence", 0),
        ("name_collision_risk", 100),
        ("former_name", 100),
        ("sparse_identity", 100),
        ("ticker_only_nonoperating", 150),
        ("operating_and_ticker", 200),
        ("operating_only", 350),
    ]
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalized_name(value: object) -> str:
    text = re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()
    return re.sub(r"\s+", " ", text)


def stable_key(cik: int) -> str:
    return hashlib.sha256(f"{SEED}:{cik}".encode()).hexdigest()


def classify(row: dict, counts: collections.Counter[str]) -> str:
    name = normalized_name(row.get("canonical_name") or row.get("sec_entity_name"))
    if row["has_relationship_evidence"]:
        return "relationship_evidence"
    if len(name) <= 12 or len(name.split()) <= 1 or (name and counts[name] > 1):
        return "name_collision_risk"
    if row["former_names"]:
        return "former_name"
    if not row["addresses"] or not row.get("sic_code") or not row.get("state_of_incorporation"):
        return "sparse_identity"
    if row["has_canonical_ticker"] and not row["is_operating"]:
        return "ticker_only_nonoperating"
    if row["has_canonical_ticker"]:
        return "operating_and_ticker"
    return "operating_only"


def canonical_hash(rows: list[dict]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(
            (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        )
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip-crc", action="store_true", help="also stream-decompress every ZIP member")
    args = parser.parse_args()

    company_manifest = json.loads((ROOT / "01-company-input-manifest.json").read_text())
    query_hash = sha256(ROOT / "01-freeze-company-inputs.sql")
    if query_hash != company_manifest["query_sha256"]:
        raise RuntimeError(
            f"query digest mismatch: {query_hash} != {company_manifest['query_sha256']}"
        )
    artifact_results = {}
    for name, expected in company_manifest["artifacts"].items():
        path = ROOT / name
        actual = sha256(path)
        if actual != expected["sha256"]:
            raise RuntimeError(f"digest mismatch for {name}: {actual} != {expected['sha256']}")
        if "rows" in expected and len(read_jsonl(path)) != expected["rows"]:
            raise RuntimeError(f"row-count mismatch for {name}")
        artifact_results[name] = {"sha256": actual, "verified": True}

    eligible = read_jsonl(ROOT / "01-eligible-universe.jsonl")
    counts = collections.Counter(
        normalized_name(r.get("canonical_name") or r.get("sec_entity_name")) for r in eligible
    )
    buckets = {name: [] for name in QUOTAS}
    for row in eligible:
        expected_stratum = classify(row, counts)
        if row["cohort_stratum"] != expected_stratum:
            raise RuntimeError(f"stratum drift for CIK {row['cik']}")
        buckets[expected_stratum].append(dict(row))

    replay: list[dict] = []
    for name, quota in QUOTAS.items():
        ordered = sorted(buckets[name], key=lambda r: (stable_key(int(r["cik"])), int(r["cik"])))
        replay.extend(ordered[:quota])
    replay.sort(key=lambda r: (list(QUOTAS).index(r["cohort_stratum"]), stable_key(int(r["cik"])), int(r["cik"])))
    for ordinal, row in enumerate(replay, 1):
        row["cohort_ordinal"] = ordinal
        row["selection_hash"] = stable_key(int(row["cik"]))
    replay_hash = canonical_hash(replay)
    expected_cohort_hash = company_manifest["artifacts"]["01-company-cohort-1000.jsonl"]["sha256"]
    if len(replay) != 1000 or replay_hash != expected_cohort_hash:
        raise RuntimeError(
            f"cohort replay mismatch rows={len(replay)} hash={replay_hash} expected={expected_cohort_hash}"
        )

    def counts(rows: list[dict], field: str, *, blank: str = "<NULL>") -> dict[str, int]:
        return dict(
            sorted(
                collections.Counter(str(row.get(field) or blank) for row in rows).items(),
                key=lambda item: (-item[1], item[0]),
            )
        )

    gleif_manifest = json.loads((ROOT / "01-gleif-snapshot-manifest.json").read_text())
    gleif_results = {}
    for item in gleif_manifest["files"]:
        path = ROOT / item["local_file"]
        actual_size = path.stat().st_size
        actual_hash = sha256(path)
        if actual_size != item["downloaded_size"] or actual_hash != item["sha256"]:
            raise RuntimeError(f"GLEIF archive mismatch for {path.name}")
        crc_result = "not_requested"
        if args.zip_crc:
            with zipfile.ZipFile(path) as archive:
                bad_member = archive.testzip()
            if bad_member is not None:
                raise RuntimeError(f"ZIP CRC failed for {path.name}: {bad_member}")
            crc_result = "passed"
        gleif_results[item["family"]] = {
            "file": path.name,
            "size": actual_size,
            "sha256": actual_hash,
            "zip_crc": crc_result,
        }

    result = {
        "verification_version": "gleif-company-freeze-offline-v1",
        "company_artifacts": artifact_results,
        "query_sha256": query_hash,
        "cohort_replay": {"rows": len(replay), "sha256": replay_hash, "passed": True},
        "composition_detail": {
            "eligible_sec_entity_type": counts(eligible, "sec_entity_type"),
            "eligible_incorporation_state": counts(eligible, "state_of_incorporation"),
            "cohort_eligibility_reason": counts(replay, "eligibility_reason"),
            "cohort_stratum": counts(replay, "cohort_stratum"),
            "cohort_incorporation_state": counts(replay, "state_of_incorporation"),
        },
        "gleif_archives": gleif_results,
        "all_checks_passed": True,
    }
    output = ROOT / "01-freeze-verification.json"
    output.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
