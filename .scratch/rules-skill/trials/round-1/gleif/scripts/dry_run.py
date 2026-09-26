"""Step 7 stand-in: put real sample records through the mapping, show what MDM gets.

Samples come from the captured files only. Level 1 is split on GLEIF's
pretty-print record boundary ("{\n" at column 0) so the scan can stop early;
each sample is then parsed with json. RR and REPEX are streamed with ijson.

Each sample goes through gleif_source.record_evidence (the native reader, which
calls adapters.normalize with the contract from rules/sources/gleif/source.yaml).
It also shows the skill's literal call (bare normalize with the skill's
publication dict) and what it does.

This matches nothing against existing records: it is not a preview.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from collections import Counter

import ijson

from edgar_warehouse.mdm.clean.adapters import normalize
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract, record_evidence
from edgar_warehouse.rules import files

INPUTS = sys.argv[1]
OUT = sys.argv[2]
L1 = f"{INPUTS}/01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip"
RR = f"{INPUTS}/01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip"
REPEX = f"{INPUTS}/01-20260911-1600-gleif-goldencopy-repex-golden-copy.json.zip"
SHA = {
    "level1": "1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a",
    "relationships": "089a2513d2b5d78fc6359c87ef4bc25a56ac7f58d6b3cb740b954e3ecd2bd0c3",
    "reporting_exceptions": "f205fd8dfc8dc04587fcd2465b741562bf39af3835916314b96033982023e831",
}
CODES = {m: c for c, e in files.source("gleif")["mdm"].items() for m in [e["contract"]["adapter"]["native_member"]]}
APPLE = "21380068P1DRHMJ8KU70"  # Shell plc: a Company the SEC side already holds (four-companies fixture)
BAD_CHECKSUM = sys.argv[3]  # a Level 1 LEI that fails mod 97, from the profile


def lei_ok(v):
    return bool(re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", v)) and int(
        "".join(str(ord(c) - 55) if c.isalpha() else c for c in v)
    ) % 97 == 1


def level1_samples():
    wanted = {"GENERAL": 2, "FUND": 1, "BRANCH": 1, "RESIDENT_GOVERNMENT_ENTITY": 1,
              "INTERNATIONAL_ORGANIZATION": 1, "SOLE_PROPRIETOR": 1}
    found, special = [], {}
    buf: list[bytes] = []
    ordinal = -1

    def take(lines, n):
        text = b"".join(lines).decode("utf-8").rstrip().rstrip(",")
        if text.endswith("]}"):
            text = text[:-2]
        row = json.loads(text)
        lei = row["LEI"]["$"]
        cat = (row.get("Entity", {}).get("EntityCategory") or {}).get("$")
        if lei in (APPLE, BAD_CHECKSUM):
            special[lei] = (n, row)
        elif wanted.get(cat, 0) > 0:
            wanted[cat] -= 1
            found.append((n, row))

    with zipfile.ZipFile(L1) as z, z.open(z.infolist()[0]) as f:
        for line in f:
            if line == b"{\n":
                if buf and ordinal >= 0:
                    take(buf, ordinal)
                buf, ordinal = [line], ordinal + 1
                if not any(wanted.values()) and len(special) == 2:
                    break
            elif ordinal >= 0:
                buf.append(line)
    return found + sorted(special.values())


def rr_samples():
    by_type, picks, seen = {}, [], Counter()
    with zipfile.ZipFile(RR) as z, z.open(z.infolist()[0]) as f:
        for n, row in enumerate(ijson.items(f, "relations.item", use_float=True)):
            rel = row["RelationshipRecord"]["Relationship"]
            t = rel["RelationshipType"]["$"]
            status = rel["RelationshipStatus"]["$"]
            start = rel["StartNode"]["NodeID"]["$"]
            if t not in by_type:
                by_type[t] = (n, row)
            if status in ("NULL", "INACTIVE") and seen[status] == 0:
                seen[status] += 1
                picks.append((n, row))
            if not lei_ok(start) and seen["bad"] == 0:
                seen["bad"] += 1
                picks.append((n, row))
    return list(by_type.values()) + picks


def repex_samples():
    picks, deletion = [], None
    with zipfile.ZipFile(REPEX) as z, z.open(z.infolist()[0]) as f:
        for n, row in enumerate(ijson.items(f, "exceptions.item", use_float=True)):
            if n < 2:
                picks.append((n, row))
            if deletion is None and "Extension" in row:
                deletion = (n, row)
            if n >= 2 and deletion:
                break
    return picks + [deletion]


def leis_of(member, row):
    if member == "relationships":
        rel = row["RelationshipRecord"]["Relationship"]
        return {rel["StartNode"]["NodeID"]["$"], rel["EndNode"]["NodeID"]["$"]}
    return {row["LEI"]["$"]}


def main():
    samples = {
        "level1": level1_samples(),
        "relationships": rr_samples(),
        "reporting_exceptions": repex_samples(),
    }
    # The approved Company scope for the dry run: every sampled LEI, except one
    # GENERAL record left out on purpose to show the out-of-scope path.
    out_of_scope = samples["level1"][1][1]["LEI"]["$"]
    eligible = set().union(*(leis_of(m, r) for m, rows in samples.items() for _, r in rows))
    eligible.discard(out_of_scope)
    results = []
    for member, rows in samples.items():
        contract = dataset_contract(member)
        for ordinal, row in rows:
            kind, body = record_evidence(
                row,
                member=member,
                contract=contract,
                source_code=CODES[member],
                eligible_leis=eligible,
                publication={
                    "publication_key": "dry-run",
                    "revision": 0,
                    "artifact_sha256": SHA[member],
                    "member": member,
                },
                ordinal=ordinal,
            )
            results.append({"member": member, "ordinal": ordinal, "outcome": kind,
                            "raw": row, "mdm": body})
    # The skill's literal step 7 call: bare normalize, the skill's publication dict.
    literal = {}
    for member, (ordinal, row) in (("level1", samples["level1"][0]), ("relationships", samples["relationships"][0])):
        try:
            literal[member] = normalize(
                row,
                contract=dataset_contract(member),
                source_code=CODES[member],
                policy=files.policy(),
                publication={"member": "sample", "publication_key": "dry-run", "revision": 0},
            )
        except Exception as exc:  # noqa: BLE001 - reporting what the skill's call does
            literal[member] = f"{type(exc).__name__}: {exc}"
    with open(OUT, "w") as fh:
        json.dump({"eligible_leis": sorted(eligible), "out_of_scope": out_of_scope,
                   "results": results, "skill_literal_normalize": literal},
                  fh, indent=1, ensure_ascii=False)
    for r in results:
        b = r["mdm"]
        print(r["member"], r["ordinal"], r["outcome"],
              b.get("kind") or b.get("reason"), b.get("record_key") or b.get("record_locator"),
              b.get("probable_kind", ""))
    print("literal normalize:", {k: (v if isinstance(v, str) else "ok") for k, v in literal.items()})


if __name__ == "__main__":
    main()
