#!/usr/bin/env python3
"""Freeze Ticket 01's read-only Snowflake inputs and deterministic cohort."""

from __future__ import annotations

import collections
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SQL_PATH = ROOT / "01-freeze-company-inputs.sql"
SEED = "gleif-company-augmentation-2026-09-11-v1"
QUERY_VERSION = "gleif-company-cohort-v1"

QUOTAS = collections.OrderedDict(
    [
        # Live eligible-universe extraction found zero current rows with the
        # parent-pointer/subsidiary-evidence signal. Preserve that as an
        # explicit zero stratum instead of silently substituting rows.
        ("relationship_evidence", 0),
        ("name_collision_risk", 100),
        ("former_name", 100),
        ("sparse_identity", 100),
        ("ticker_only_nonoperating", 150),
        ("operating_and_ticker", 200),
        ("operating_only", 350),
    ]
)


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def write_jsonl(path: Path, rows: list[dict]) -> str:
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        for row in rows:
            encoded = canonical_bytes(row)
            handle.write(encoded)
            digest.update(encoded)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> str:
    encoded = canonical_bytes(value)
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def normalized_name(value: object) -> str:
    text = re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()
    return re.sub(r"\s+", " ", text)


def stable_key(cik: int) -> str:
    return hashlib.sha256(f"{SEED}:{cik}".encode()).hexdigest()


def stratum(row: dict, name_counts: collections.Counter[str]) -> str:
    name = normalized_name(row.get("canonical_name") or row.get("sec_entity_name"))
    short = len(name) <= 12 or len(name.split()) <= 1
    if row["has_relationship_evidence"]:
        return "relationship_evidence"
    if short or (name and name_counts[name] > 1):
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


def main() -> None:
    result = subprocess.run(
        [
            "uv", "run", "snow", "sql",
            "--connection", "edgartools-prod",
            "--format", "json",
            "--silent",
            "--filename", str(SQL_PATH),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    rows = json.loads(result.stdout)
    query_meta: dict = {}
    tickers: list[dict] = []
    eligible: list[dict] = []
    for wrapper in rows:
        payload = wrapper["PAYLOAD"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if wrapper["ROW_TYPE"] == "meta":
            query_meta = payload
        elif wrapper["ROW_TYPE"] == "ticker":
            tickers.append(payload)
        elif wrapper["ROW_TYPE"] == "eligible":
            eligible.append(payload)

    tickers.sort(key=lambda r: (int(r["cik"]), str(r.get("ticker") or ""), str(r.get("exchange") or "")))
    eligible.sort(key=lambda r: int(r["cik"]))
    if len(eligible) != len({int(r["cik"]) for r in eligible}):
        raise RuntimeError("eligible extraction does not contain distinct CIKs")

    name_counts = collections.Counter(
        normalized_name(r.get("canonical_name") or r.get("sec_entity_name")) for r in eligible
    )
    buckets: dict[str, list[dict]] = {name: [] for name in QUOTAS}
    for row in eligible:
        row["normalized_name_v1"] = normalized_name(
            row.get("canonical_name") or row.get("sec_entity_name")
        )
        row["eligibility_reason"] = (
            "operating_and_ticker" if row["is_operating"] and row["has_canonical_ticker"]
            else "operating_only" if row["is_operating"]
            else "ticker_only_nonoperating"
        )
        assigned = stratum(row, name_counts)
        row["cohort_stratum"] = assigned
        buckets[assigned].append(row)

    cohort: list[dict] = []
    availability = {bucket_name: len(rows) for bucket_name, rows in buckets.items()}
    shortages = {
        bucket_name: {"available": availability[bucket_name], "required": quota}
        for bucket_name, quota in QUOTAS.items()
        if availability[bucket_name] < quota
    }
    if shortages:
        raise RuntimeError(
            "insufficient rows for declared strata: "
            + json.dumps({"shortages": shortages, "availability": availability}, sort_keys=True)
        )
    for bucket_name, quota in QUOTAS.items():
        ordered = sorted(buckets[bucket_name], key=lambda r: (stable_key(int(r["cik"])), int(r["cik"])))
        cohort.extend(ordered[:quota])
    cohort.sort(key=lambda r: (list(QUOTAS).index(r["cohort_stratum"]), stable_key(int(r["cik"])), int(r["cik"])))
    if len(cohort) != 1000 or len({int(r["cik"]) for r in cohort}) != 1000:
        raise RuntimeError("cohort is not exactly 1,000 distinct CIKs")
    for ordinal, row in enumerate(cohort, 1):
        row["cohort_ordinal"] = ordinal
        row["selection_hash"] = stable_key(int(row["cik"]))

    ticker_hash = write_jsonl(ROOT / "01-sec-company-ticker-snapshot.jsonl", tickers)
    universe_hash = write_jsonl(ROOT / "01-eligible-universe.jsonl", eligible)
    cohort_hash = write_jsonl(ROOT / "01-company-cohort-1000.jsonl", cohort)

    def count_by(field: str) -> dict[str, int]:
        return dict(sorted(collections.Counter(str(r.get(field)) for r in eligible).items()))

    composition = {
        "query_version": QUERY_VERSION,
        "selection_seed": SEED,
        "eligible_universe_count": len(eligible),
        "eligibility_reason": count_by("eligibility_reason"),
        "tracking_status": count_by("tracking_status"),
        "has_canonical_ticker": count_by("has_canonical_ticker"),
        "has_sic": dict(sorted(collections.Counter(str(bool(r.get("sic_code"))) for r in eligible).items())),
        "has_incorporation_state": dict(sorted(collections.Counter(str(bool(r.get("state_of_incorporation"))) for r in eligible).items())),
        "has_address": dict(sorted(collections.Counter(str(bool(r["addresses"])) for r in eligible).items())),
        "has_former_name": dict(sorted(collections.Counter(str(bool(r["former_names"])) for r in eligible).items())),
        "has_relationship_evidence": count_by("has_relationship_evidence"),
        "name_collision_risk": {
            "true": sum(
                1 for r in eligible
                if len(r["normalized_name_v1"]) <= 12
                or len(r["normalized_name_v1"].split()) <= 1
                or name_counts[r["normalized_name_v1"]] > 1
            ),
            "definition": "normalized name length <=12, one token, or duplicate normalized name in eligible universe",
        },
        "cohort_stratum_available": availability,
        "cohort_stratum_selected": dict(QUOTAS),
    }
    composition_hash = write_json(ROOT / "01-universe-composition.json", composition)
    manifest = {
        "query_version": QUERY_VERSION,
        "query_sha256": hashlib.sha256(SQL_PATH.read_bytes()).hexdigest(),
        "selection_seed": SEED,
        "snowflake_connection": "edgartools-prod",
        "snowflake_database": "EDGARTOOLS_PROD",
        "read_only": True,
        "query_metadata": query_meta,
        "artifacts": {
            "01-sec-company-ticker-snapshot.jsonl": {"rows": len(tickers), "sha256": ticker_hash},
            "01-eligible-universe.jsonl": {"rows": len(eligible), "sha256": universe_hash},
            "01-company-cohort-1000.jsonl": {"rows": len(cohort), "sha256": cohort_hash},
            "01-universe-composition.json": {"sha256": composition_hash},
        },
    }
    write_json(ROOT / "01-company-input-manifest.json", manifest)
    print(json.dumps({"eligible": len(eligible), "ticker_rows": len(tickers), "cohort": len(cohort), "availability": availability}, indent=2))


if __name__ == "__main__":
    main()
