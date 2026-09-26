"""Whole-file accounting of RR and REPEX through the written mapping.

Every record goes through gleif_source.record_evidence with the approved scope
set to every Level 1 LEI (the widest scope possible), so the counts show what
the mapping itself decides, not the scope. For RR it also joins the start and
end LEIs to their Level 1 category (from scratch/level1-table.tsv).
"""

from __future__ import annotations

import json
import sys
import zipfile
from collections import Counter, defaultdict

import ijson

from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence
from edgar_warehouse.rules import files

INPUTS, TABLE, OUT, MEMBER = sys.argv[1:5]
FILES = {
    "relationships": ("01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip", "relations"),
    "reporting_exceptions": ("01-20260911-1600-gleif-goldencopy-repex-golden-copy.json.zip", "exceptions"),
}
CODES = {e["contract"]["adapter"]["native_member"]: c for c, e in files.source("gleif")["mdm"].items()}


def main():
    category = {}
    with open(TABLE) as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            category[parts[0]] = parts[1] or "(none)"
    name, wrapper = FILES[MEMBER]
    contract = dataset_contract(MEMBER)
    eligible = set(category)
    outcomes = Counter()
    blocking = Counter()
    nonblocking = set(contract.get("nonblocking_deferred_reasons", []))
    by_type = defaultdict(Counter)
    samples = defaultdict(list)
    with zipfile.ZipFile(f"{INPUTS}/{name}") as z, z.open(z.infolist()[0]) as f:
        for n, row in enumerate(ijson.items(f, f"{wrapper}.item", use_float=True)):
            kind, body = record_evidence(
                row, member=MEMBER, contract=contract, source_code=CODES[MEMBER],
                eligible_leis=eligible, ordinal=n,
                publication={"publication_key": "account", "revision": 0,
                             "artifact_sha256": "0" * 64, "member": MEMBER},
            )
            key = "assertion" if kind == "assertion" else body["reason"]
            outcomes[key] += 1
            if kind == "deferred" and key not in nonblocking:
                blocking[key] += 1
            if len(samples[key]) < 3:
                samples[key].append(n)
            if MEMBER == "relationships":
                rel = row["RelationshipRecord"]["Relationship"]
                t = rel["RelationshipType"]["$"]
                s = category.get(rel["StartNode"]["NodeID"]["$"], "(not in Level 1)")
                e = category.get(rel["EndNode"]["NodeID"]["$"], "(not in Level 1)")
                by_type[t][f"{s} -> {e}"] += 1
    report = {"member": MEMBER, "records": sum(outcomes.values()), "outcomes": dict(outcomes),
              "blocking": dict(blocking), "sample_ordinals": dict(samples),
              "start_end_categories_by_type": {t: c.most_common() for t, c in by_type.items()}}
    with open(OUT, "w") as fh:
        json.dump(report, fh, indent=1)
    print(json.dumps({k: report[k] for k in ("records", "outcomes", "blocking")}, indent=1))


if __name__ == "__main__":
    main()
