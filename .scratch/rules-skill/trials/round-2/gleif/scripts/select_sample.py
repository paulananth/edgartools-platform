"""Pick a bounded dry-run sample from the first N Level 1 and RR records.

Writes scratch/sample/{level1,relationships}.pick.json: the raw records, as the
files hold them. Each pick says why it was picked. Bounded: first N records only.
"""

import json
import sys
import zipfile
from pathlib import Path

import ijson

S = Path(sys.argv[1])
N = int(sys.argv[2])
IN = S / "inputs"
OUT = S / "scratch" / "sample"
OUT.mkdir(parents=True, exist_ok=True)
L1 = IN / "01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip"
RR = IN / "01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip"


def v(node, path):
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def stream(path, wrapper):
    with zipfile.ZipFile(path) as z, z.open(z.infolist()[0]) as f:
        for i, r in enumerate(ijson.items(f, f"{wrapper}.item")):
            if i >= N:
                return
            yield i, r


def l1_tests():
    return [
        ("general_active_issued_with_address_lines",
         lambda r: v(r, "Entity.EntityCategory.$") == "GENERAL"
         and v(r, "Entity.EntityStatus.$") == "ACTIVE"
         and v(r, "Registration.RegistrationStatus.$") == "ISSUED"
         and isinstance(v(r, "Entity.LegalAddress.AdditionalAddressLine"), list)),
        ("general_legal_and_hq_postcodes_differ",
         lambda r: v(r, "Entity.EntityCategory.$") == "GENERAL"
         and v(r, "Entity.EntityStatus.$") == "ACTIVE"
         and v(r, "Entity.LegalAddress.PostalCode.$") != v(r, "Entity.HeadquartersAddress.PostalCode.$")),
        ("general_inactive_retired",
         lambda r: v(r, "Entity.EntityCategory.$") == "GENERAL"
         and v(r, "Registration.RegistrationStatus.$") == "RETIRED"),
        ("fund", lambda r: v(r, "Entity.EntityCategory.$") == "FUND"),
        ("branch", lambda r: v(r, "Entity.EntityCategory.$") == "BRANCH"),
        ("sole_proprietor", lambda r: v(r, "Entity.EntityCategory.$") == "SOLE_PROPRIETOR"),
        ("government", lambda r: v(r, "Entity.EntityCategory.$") == "RESIDENT_GOVERNMENT_ENTITY"),
        ("annulled_bad_check_digit", lambda r: v(r, "LEI.$") == "0292001629A3Q7XJ0D13"),
        ("general_left_out_of_dry_run_scope",
         lambda r: v(r, "Entity.EntityCategory.$") == "GENERAL"
         and v(r, "Registration.RegistrationStatus.$") == "LAPSED"),
    ]


# Pass 1: Level 1 LEIs and one record per test.
leis, picks = set(), {}
for i, r in stream(L1, "records"):
    leis.add(v(r, "LEI.$"))
    for name, test in l1_tests():
        if name not in picks and test(r):
            picks[name] = {"why": name, "ordinal": i, "record": r}
            break

# Pass 2: RR records whose both ends are among those Level 1 LEIs, plus edge cases.
rr_picks = {}
wanted_types = ["IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY",
                "IS_INTERNATIONAL_BRANCH_OF", "IS_FUND-MANAGED_BY", "IS_SUBFUND_OF"]
for i, r in stream(RR, "relations"):
    rel = v(r, "RelationshipRecord.Relationship")
    start, end = v(rel, "StartNode.NodeID.$"), v(rel, "EndNode.NodeID.$")
    rtype, status = v(rel, "RelationshipType.$"), v(rel, "RelationshipStatus.$")
    periods = v(rel, "RelationshipPeriods.RelationshipPeriod")
    plist = periods if isinstance(periods, list) else [periods]
    has_rp = any(v(p, "PeriodType.$") == "RELATIONSHIP_PERIOD" for p in plist if isinstance(p, dict))
    key = None
    if start in leis and end in leis and rtype in wanted_types and f"both_ends:{rtype}" not in rr_picks:
        key = f"both_ends:{rtype}"
    elif status == "NULL" and "status_null" not in rr_picks:
        key = "status_null"
    elif not has_rp and "no_relationship_period" not in rr_picks:
        key = "no_relationship_period"
    elif start not in leis and "start_outside_dry_run_scope" not in rr_picks and i > 1000:
        key = "start_outside_dry_run_scope"
    if key:
        rr_picks[key] = {"why": key, "ordinal": i, "record": r}

# Pass 3: the Level 1 records of every RR endpoint picked with both ends known.
need = set()
for p in rr_picks.values():
    rel = v(p["record"], "RelationshipRecord.Relationship")
    if p["why"].startswith("both_ends"):
        need |= {v(rel, "StartNode.NodeID.$"), v(rel, "EndNode.NodeID.$")}
have = {v(p["record"], "LEI.$") for p in picks.values()}
for i, r in stream(L1, "records"):
    lei = v(r, "LEI.$")
    if lei in need and lei not in have:
        picks[f"rr_endpoint:{lei}"] = {"why": "rr_endpoint", "ordinal": i, "record": r}
        have.add(lei)
    if need <= have:
        break

json.dump(sorted(picks.values(), key=lambda p: p["ordinal"]),
          open(OUT / "level1.pick.json", "w"), indent=1, ensure_ascii=False)
json.dump(sorted(rr_picks.values(), key=lambda p: p["ordinal"]),
          open(OUT / "relationships.pick.json", "w"), indent=1, ensure_ascii=False)
print("level1:", [(p["why"], p["ordinal"], v(p["record"], "LEI.$")) for p in picks.values()])
print("rr:", [(p["why"], p["ordinal"]) for p in rr_picks.values()])
