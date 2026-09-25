"""Ticket 08: does the production path reproduce the measured coverage?

Builds the Name Census with the production builder (`clean/name_census.py`)
over every SEC filer in the bronze scan (current and former names) and the
full pinned GLEIF Golden Copy, then runs the production rule tests
(`clean/matching.py`, through `_passes`) over the 6,414 Account hold-back
Companies with the declared rules (`policies/company.json`, `name_binding`).
It compares the Companies that bind with the research coverage
(`08-coverage.py`, sha256 97e5d118...).

Two readings of the SEC business country: `bronze` uses `countryCode` where
`stateOrCountry` is empty, as the research did; `silver` does not, because
silver lands `stateOrCountry` only.

    uv run --no-sync python .scratch/company-mastering/research/08-parity.py \\
        <sec-scan.jsonl> <companies.jsonl> <coverage-2.jsonl> <gleif-all.jsonl> \\
        <lei2.json.zip> <out.json>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from edgar_warehouse.mdm.clean.matching import _passes
from edgar_warehouse.mdm.clean.name_census import build, entry
from edgar_warehouse.mdm.clean.names import edgar_jurisdiction
from edgar_warehouse.mdm.clean.store import digest
from edgar_warehouse.mdm.policies import load_kinds

SHA = "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a"
META = {
    "format": "json.zip",
    "cdf_version": "LEI_3.1",
    "content_date": "2026-09-11T16:00:00+00:00",
    "file_content": "GLEIF_FULL_PUBLISHED",
    "delta_start": None,
    "record_count": 3428477,
}


def field(value):
    return {"op": "value", "value": value} if value is not None else {"op": "unknown"}


def main(scan, companies, coverage, gleif_all, archive, out):
    filers = []
    for line in open(scan):
        s = json.loads(line)
        if s.get("cik") is None:
            continue
        former = [n.get("name") for n in s.get("formerNames") or [] if n.get("name")]
        filers.append((f"{int(s['cik']):010d}", s.get("name"), former))
    with open(archive, "rb") as stream:
        census = build(
            filers=filers,
            sec_population={"capture_run_id": "bronze-scan", "filers": len(filers)},
            gleif_archive=stream,
            gleif_metadata=META,
            gleif_sha256=SHA,
        )
    census_hash = digest(census)
    rows = [json.loads(line) for line in open(companies)]
    wanted = {}
    for r in rows:
        e = entry(census, r["name"], census_digest=census_hash)
        r["entry"] = e
        if e and e["lei_count"] == 1:
            wanted[e["leis"][0][0]] = None
    for line in open(gleif_all):
        if line[8:28] in wanted:
            g = json.loads(line)
            wanted[g["lei"]] = g
    rules = [r for r in load_kinds()["company"]["rules"] if r["family"] == "name_binding"]
    result = {}
    for reading in ("bronze", "silver"):
        bound = set()
        for r in rows:
            e = r["entry"]
            if not e or e["lei_count"] != 1 or wanted.get(e["leis"][0][0]) is None:
                continue
            g = wanted[e["leis"][0][0]]
            business = (r.get("addresses") or {}).get("business") or {}
            code = business.get("stateOrCountry")
            if reading == "bronze":
                code = code or business.get("countryCode")
            place = edgar_jurisdiction(code)
            sec = {
                "record_key": r["cik"],
                "fields": {
                    "name": field(r["name"]),
                    "state_of_incorporation": field(r.get("state_of_incorporation") or None),
                },
                "provenance": {
                    "matching": {
                        "business_postal_code": business.get("zipCode"),
                        "business_country": place.split("-")[0] if place else None,
                        "name_census": e,
                    }
                },
            }
            hq = g.get("hq") or {}
            gleif = {
                "kind": "company" if g["category"] == "GENERAL" else "deferred",
                "identifiers": {"lei": g["lei"]},
                "fields": {
                    "name": field(g["legal_name"]),
                    "jurisdiction": field(g["jurisdiction"]),
                    # The extract keeps no LastUpdateDate; the census read the
                    # same archive, so the freshness check holds by design.
                    "gleif_last_update": field(e["leis"][0][1] or None),
                    "gleif_entity_status": field(g["entity_status"]),
                    "gleif_registration_status": field(g["registration_status"]),
                },
                "provenance": {
                    "matching": {
                        "headquarters_postal_code": hq.get("postal"),
                        "headquarters_country": hq.get("country"),
                    }
                },
            }
            if any(_passes(rule, sec, gleif) for rule in rules):
                bound.add(r["cik"])
        result[reading] = bound
    research = {
        json.loads(line)["cik"]
        for line in open(coverage)
        if json.loads(line)["outcome"].startswith("BIND")
    }
    report = {
        "census_sha256": census_hash,
        "census_entries": len(census["entries"]),
        "research_binds": len(research),
        "coverage_sha256": hashlib.sha256(Path(coverage).read_bytes()).hexdigest(),
        **{
            reading: {
                "binds": len(bound),
                "only_production": sorted(bound - research),
                "only_research": sorted(research - bound),
            }
            for reading, bound in result.items()
        },
    }
    Path(out).write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: (v if not isinstance(v, dict) else {x: (y if not isinstance(y, list) else len(y)) for x, y in v.items()}) for k, v in report.items()}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:7])
