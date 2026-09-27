"""Rules skill ticket 08: what placing all 309 SEC codes changes.

Compares origin/main's `names.edgar_jurisdiction` (169 codes) with the one
that reads `rules/reference/sec-place-codes.yaml` (309 codes) over every code
SEC wrote in the ticket 08 bronze scan (2026-09-24, newest submissions.json per
CIK, 76,230 filers): `stateOfIncorporation` and each address's
`stateOrCountry` and `countryCode`. Then names the Companies touched and what
the name rules said about them. No SEC request.

    uv run --no-sync python .scratch/rules-skill/research/08-place-code-impact.py \\
        <names_before.py> <cm08-sec-scan.jsonl> <cm08-coverage-2.jsonl>

`names_before.py` is `git show a425efb0:edgar_warehouse/mdm/clean/names.py`.
"""

from __future__ import annotations

import ast
import collections
import importlib.util
import json
import sys

from edgar_warehouse.mdm.clean import names as after


def main(before_path: str, scan_path: str, coverage_path: str) -> None:
    spec = importlib.util.spec_from_file_location("names_before", before_path)
    before = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(before)

    seen = collections.Counter()
    where = collections.defaultdict(set)
    for line in open(scan_path):
        record = json.loads(line)
        values = [("stateOfIncorporation", record.get("stateOfIncorporation"))]
        addresses = record.get("addresses") or {}
        if isinstance(addresses, str):
            addresses = ast.literal_eval(addresses)
        for kind, address in (addresses or {}).items():
            if isinstance(address, dict):
                values += [(f"{kind}.stateOrCountry", address.get("stateOrCountry"))]
                values += [(f"{kind}.countryCode", address.get("countryCode"))]
        for field, value in values:
            if value in (None, ""):
                continue
            code = str(value).strip().upper()
            seen[code] += 1
            where[code].add((record["cik"], field))

    changed = {
        code: (before.edgar_jurisdiction(code), after.edgar_jurisdiction(code))
        for code in seen
        if before.edgar_jurisdiction(code) != after.edgar_jurisdiction(code)
    }
    filers = {cik for code in changed for cik, _ in where[code]}
    fields = collections.Counter(field for code in changed for _, field in where[code])
    coverage = {json.loads(line)["cik"]: json.loads(line) for line in open(coverage_path)}
    companies = sorted(cik.zfill(10) for cik in filers if cik.zfill(10) in coverage)
    print(json.dumps({
        "distinct_codes_in_bronze": len(seen),
        "codes_whose_answer_changes": changed,
        "fields": dict(fields),
        "filers_touched": len(filers),
        "companies_touched": [
            {"cik": c, "name": coverage[c]["name"], "name_rules": coverage[c]["outcome"]}
            for c in companies
        ],
        "unplaced_in_bronze": {c: n for c, n in seen.items() if after.edgar_jurisdiction(c) is None},
    }, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(*sys.argv[1:4])
