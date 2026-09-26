"""Ticket 05, step 1: freeze CIK manifest v1 for the Proving Run's first phase.

The population is ticket 12's frozen cohort: the 76,230 SEC filers whose
submissions document is in prod bronze, each at the object key the ticket 08
scan read (`08-scan-sec-lei-and-address.py`). The cohort is every filer the
active Company rule (`sec-company-candidate` 2026-09-25.13) calls a Company
(`08-companies.py`, 6,414) plus seeded non-Company controls, Tim Cook and
Satya Nadella named among them, dealt into chunks of 1,000: the most one
`prepare-clean-company` bundle holds. A reversible technical choice (Claude,
2026-09-26), not an operator decision.

    uv run --no-sync python .scratch/company-mastering/research/05-manifest.py \\
        <sec-scan.jsonl> <companies.jsonl> <out.json>
"""

from __future__ import annotations

import hashlib
import json
import random
import sys

SEED = "20260926.05"
CHUNK = 1000
CHUNKS = 7
NAMED_CONTROLS = ["0001214156", "0001513142"]  # Tim Cook, Satya Nadella


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(scan: str, companies: str, out: str) -> None:
    keys = {}
    with open(scan) as stream:
        for line in stream:
            s = json.loads(line)
            if s.get("cik") is not None and s.get("key"):
                keys[f"{int(s['cik']):010d}"] = s["key"]
    with open(companies) as stream:
        company = sorted({f"{int(json.loads(line)['cik']):010d}" for line in stream})
    missing = [c for c in company if c not in keys]
    if missing:
        raise SystemExit(f"{len(missing)} Companies have no bronze key: {missing[:5]}")
    others = sorted(set(keys) - set(company) - set(NAMED_CONTROLS))
    for named in NAMED_CONTROLS:
        if named not in keys or named in company:
            raise SystemExit(f"named control {named} is not a non-Company filer")
    rng = random.Random(SEED)
    drawn = rng.sample(others, CHUNK * CHUNKS - len(company) - len(NAMED_CONTROLS))
    members = [(c, "company") for c in company] + [
        (c, "control") for c in sorted([*NAMED_CONTROLS, *drawn])
    ]
    rng.shuffle(members)
    body = {
        "manifest": "company-proving-run-ciks",
        "version": 1,
        "seed": SEED,
        "population": {
            "description": "SEC filers with a submissions document in prod bronze (ticket 12's frozen cohort)",
            "filers": len(keys),
            "scan_sha256": sha256(scan),
        },
        "companies": {
            "rule": "sec-company-candidate 2026-09-25.13",
            "count": len(company),
            "companies_sha256": sha256(companies),
        },
        "controls": {"count": len(members) - len(company), "named": NAMED_CONTROLS},
        "chunks": [
            [
                {"cik": cik, "role": role, "key": keys[cik]}
                for cik, role in members[i * CHUNK : (i + 1) * CHUNK]
            ]
            for i in range(CHUNKS)
        ],
    }
    data = json.dumps(body, sort_keys=True, indent=1).encode() + b"\n"
    with open(out, "wb") as stream:
        stream.write(data)
    print(
        json.dumps(
            {
                "sha256": hashlib.sha256(data).hexdigest(),
                "filers": len(keys),
                "companies": len(company),
                "controls": len(members) - len(company),
                "chunks": [len(c) for c in body["chunks"]],
            }
        )
    )


if __name__ == "__main__":
    main(*sys.argv[1:4])
