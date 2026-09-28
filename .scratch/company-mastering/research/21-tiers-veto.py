"""Ticket 21: how a priority (cascade) name-and-address matching falls.

Operator, 2026-09-27: match on name and address first; merge what matches;
then drop fields one at a time to merge more. No jurisdiction test.

Each pass takes only the SEC filers and GLEIF entities still unmatched. A pair
binds in a pass when the names are equal (legal form kept, as today) and the
pass's address fields agree, and it is one-to-one in that pass: the filer has
exactly one such GLEIF entity, and that entity exactly one such filer. The
GLEIF entity must still be GENERAL, ACTIVE and not DUPLICATE or ANNULLED.

A registered agent's address ("C/O", Corporation Trust Center, ...) is shared
by thousands of unrelated companies: only its country is compared, never its
street, city or postcode.

    python .scratch/company-mastering/research/21-tiers.py \\
        <cm08-coverage-2.jsonl> <cm08-sec-scan.jsonl> <cm08-gleif-all.jsonl> <out.json>
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from edgar_warehouse.mdm.clean.names import (
    jurisdictions_conflict,
    edgar_jurisdiction,
    legal_form_key,
    postal_codes_agree,
    sec_legal_form_key,
)

HERE = Path(__file__).parent
PASSES = [
    ("P1 name + street + city + postcode", ("street", "city", "postal")),
    ("P2 name + street + postcode", ("street", "postal")),
    ("P3 name + street + city", ("street", "city")),
    ("P4 name + postcode", ("postal",)),
    ("P5 name + city", ("city",)),


]
# Every pass but the last also needs the same country.
AGENT = re.compile(
    r"\bC/?O\b|CARE OF|CORPORATION TRUST|1209 ORANGE|251 LITTLE FALLS|"
    r"2711 CENTERVILLE|CORPORATION SERVICE|REGISTERED AGENT|CT CORPORATION|"
    r"1521 CONCORD PIKE|8 THE GREEN|3500 SOUTH DUPONT|INCORP SERVICES|"
    r"NATIONAL CORPORATE RESEARCH|COGENCY GLOBAL|UNITED AGENT|"
    r"VCORP|HARVARD BUSINESS SERVICES|REGISTERED OFFICE"
)
WORDS = {
    "STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "ROAD": "RD", "DRIVE": "DR",
    "BOULEVARD": "BLVD", "LANE": "LN", "PLACE": "PL", "COURT": "CT",
    "PARKWAY": "PKWY", "HIGHWAY": "HWY", "CIRCLE": "CIR", "SQUARE": "SQ",
    "CENTER": "CTR", "CENTRE": "CTR", "TERRACE": "TER", "PLAZA": "PLZ",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW",
    "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5",
    "FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD", "FOURTH": "4TH", "FIFTH": "5TH",
    "MOUNT": "MT", "SAINT": "ST", "FORT": "FT",
}
UNIT = re.compile(r"\b(STE|SUITE|FL|FLOOR|UNIT|RM|ROOM|BLDG|BUILDING|APT|DEPT|MS|MAIL STOP|PO BOX)\b.*$")


def _words(text) -> str:
    text = re.sub(r"[^A-Z0-9 ]+", " ", str(text or "").upper().replace("&", " AND ").replace("#", " STE "))
    return " ".join(WORDS.get(w, w) for w in text.split())


def street(text) -> str:
    return UNIT.sub("", _words(text)).strip()


def sec_places(filer: dict) -> list[dict]:
    out = []
    for role in ("business", "mailing"):
        a = (filer.get("addresses") or {}).get(role) or {}
        place = edgar_jurisdiction(a.get("stateOrCountry") or a.get("countryCode"))
        lines = [a.get("street1"), a.get("street2")]
        if not place:
            continue
        if AGENT.search(" ".join(str(x or "").upper() for x in lines)):
            out.append({"street": set(), "city": "", "postal": None, "country": place.split("-")[0]})
            continue
        out.append({
            "street": {street(x) for x in lines if street(x)},
            "city": _words(a.get("city")),
            "postal": a.get("zipCode"),
            "country": place.split("-")[0],
        })
    return out


def gleif_places(entity: dict) -> list[dict]:
    out = []
    for role in ("legal", "hq"):
        a = entity.get(role) or {}
        lines = a.get("lines") or []
        if not a.get("country"):
            continue
        if AGENT.search(" ".join(lines).upper()):
            out.append({"street": set(), "city": "", "postal": None, "country": a["country"]})
            continue
        out.append({
            "street": {street(x) for x in lines if street(x)},
            "city": _words(a.get("city")),
            "postal": a.get("postal"),
            "country": a["country"],
        })
    return out


def agrees(s: dict, g: dict, fields: tuple | None) -> bool:
    if fields is None:
        return True
    if s["country"] != g["country"]:
        return False
    for f in fields:
        if f == "street" and not (s["street"] & g["street"]):
            return False
        if f == "city" and not (s["city"] and s["city"] == g["city"]):
            return False
        if f == "postal" and not postal_codes_agree(s["postal"], s["country"], g["postal"], g["country"]):
            return False
    return True


def eligible(e: dict) -> bool:
    return (e["category"] == "GENERAL" and e["entity_status"] == "ACTIVE"
            and e["registration_status"] not in ("DUPLICATE", "ANNULLED"))


def main(coverage_path, scan_path, gleif_path, out_path):
    cohort = {json.loads(l)["cik"]: json.loads(l) for l in open(coverage_path)}
    filers = {}
    by_key = defaultdict(set)
    for line in open(scan_path):
        f = json.loads(line)
        key = sec_legal_form_key(f["name"])
        if key:
            filers[f["cik"]] = {"key": key, "places": sec_places(f), "soi": edgar_jurisdiction(f.get("stateOfIncorporation")), "country": (sec_places(f) or [{}])[0].get("country")}
            by_key[key].add(f["cik"])
    # Every GLEIF entity carrying an SEC filer's name key, legal or other name.
    gleif, holders = {}, defaultdict(set)
    for line in open(gleif_path):
        e = json.loads(line)
        names = [e["legal_name"]] + [n for _, n in e.get("other_names") or []]
        keys = {legal_form_key(n) for n in names} & by_key.keys()
        if not keys:
            continue
        gleif[e["lei"]] = {"eligible": eligible(e), "places": gleif_places(e), "raw": e}
        for k in keys:
            holders[k].add(e["lei"])

    matched_sec, matched_lei, result = {}, set(), {}
    for label, fields in PASSES:
        proposals = defaultdict(set)  # cik -> leis
        claims = defaultdict(set)  # lei -> ciks
        for cik, f in filers.items():
            if cik in matched_sec:
                continue
            for lei in holders.get(f["key"], ()):
                g = gleif[lei]
                if lei in matched_lei or not g["eligible"]:
                    continue
                if jurisdictions_conflict(f["soi"], g["raw"]["jurisdiction"], sec_business_country=f["country"]):
                    continue
                if fields is None or any(agrees(s, p, fields) for s in f["places"] for p in g["places"]):
                    proposals[cik].add(lei)
                    claims[lei].add(cik)
        bound = {cik: next(iter(leis)) for cik, leis in proposals.items()
                 if len(leis) == 1 and len(claims[next(iter(leis))]) == 1}
        for cik, lei in bound.items():
            matched_sec[cik] = (lei, label)
            matched_lei.add(lei)
        result[label] = {"bound_all_filers": len(bound),
                         "bound_companies": sum(c in cohort for c in bound),
                         "ambiguous_companies": sum(c in cohort and len(proposals[c]) + 0 > 0 for c in proposals if c not in bound)}

    # The floor: name alone, one-to-one over what is left (not proposed).
    left = Counter()
    for cik in cohort:
        if cik in matched_sec or cik not in filers:
            continue
        leis = [l for l in holders.get(filers[cik]["key"], ()) if l not in matched_lei and gleif[l]["eligible"]]
        left["name names no eligible GLEIF entity" if not leis else
             "name alone, one GLEIF entity, no address agrees" if len(leis) == 1 and len(by_key[filers[cik]["key"]]) == 1 else
             "name alone, several GLEIF entities or SEC filers"] += 1

    # Against today's rules and the ticket 08 labels.
    today = Counter()
    for cik, row in cohort.items():
        now = row["outcome"].split(":")[0]
        new = matched_sec.get(cik)
        lei_now = (row.get("gleif") or {}).get("lei") if now.startswith("BIND") else None
        today[(now, "cascade binds" if new else "cascade leaves",
               "same LEI" if new and lei_now == new[0] else "other LEI" if new and lei_now else "-")] += 1
    labels = Counter()
    for name in ("08-1-sample.jsonl", "08-2-sample.jsonl", "08-1-adversarial.jsonl", "08-2-adversarial.jsonl"):
        for line in open(HERE / name):
            r = json.loads(line)
            hit = matched_sec.get(r["cik"])
            if hit and hit[0] == r["gleif"]["lei"]:
                labels[(hit[1], r["final"])] += 1
            elif hit:
                labels[(hit[1], "binds a different LEI than the labelled pair")] += 1
    out = {
        "passes": result,
        "companies": len(cohort),
        "bound_companies": sum(c in cohort for c in matched_sec),
        "left": dict(left),
        "against_today": {" | ".join(k): v for k, v in sorted(today.items())},
        "labels_by_pass": {" | ".join(k): v for k, v in sorted(labels.items())},
    }
    Path(out_path).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    with open(Path(out_path).with_suffix(".bound.jsonl"), "w") as w:
        for cik, (lei, label) in sorted(matched_sec.items()):
            if cik in cohort:
                w.write(json.dumps({"cik": cik, "lei": lei, "pass": label}) + "\n")
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(*sys.argv[1:5])
