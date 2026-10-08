"""Ticket 21: the cascade on the values the data quality rule leaves fit.

`21-tiers.py` measured the operator's passes (2026-09-27) before ticket 22.
This measures them as they will run, with the rulings since:

- Each side's address is the one the quality rule (`quality.apply`, the
  repo's `quality.yaml`) leaves fit: GLEIF's headquarters address first,
  else its legal address; SEC's business address. A withheld address (an
  agent's, a placeholder) is never compared: only its country is.
- An address (standardized street, 5-digit postcode, country) that more than
  25 entities use across both sources is not compared either (ticket 22,
  "25, yes").
- No jurisdiction test. A pair whose places of incorporation conflict binds
  like any other and is flagged as its own stratum: the proof decides
  whether that stratum binds or goes to review (operator, 2026-09-28).
- Each bound pair is also flagged when its name is not unique over the whole
  of both sources (only unique among what an earlier pass left), the other
  risk the research names.

Every filer and entity is read by the census's own readers
(`company_source.cascade_filer`, `name_census.cascade_entity`), the passes
come from the Company rules (`cascade.spec`) and run in the census's own
function (`cascade.assign`), so this measures what the census will do. Each pass
takes only the SEC filers and GLEIF entities still unmatched, and binds a
pair only one to one in that pass. Names are equal with the legal
form kept, counting GLEIF's other names. The GLEIF entity is GENERAL, ACTIVE,
not DUPLICATE or ANNULLED. A record the quality rule makes an exception
(no name) never binds. Only GENERAL GLEIF entities are read: no other
category can bind (a branch carries its head office's name). Zero SEC requests: bronze only.

    uv run python .scratch/company-mastering/research/21-cascade.py \\
        <cm08-coverage.jsonl> <cm08-sec-scan.jsonl> <cm08-gleif-all.jsonl> <out.json>
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from edgar_warehouse.mdm.clean import cascade
from edgar_warehouse.mdm.clean.company_source import POLICY, cascade_filer
from tests.support.retired_company_address import business_address
from edgar_warehouse.mdm.clean.gleif_source import dataset_contract
from edgar_warehouse.mdm.clean.name_census import cascade_entity

HERE = Path(__file__).parent


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sec_row(f: dict) -> tuple[dict, dict | None]:
    """A scanned filer as the landing writes it: the Company row and its
    business address row, read by the census's own reader."""
    b = (f.get("addresses") or {}).get("business")
    address = business_address({
        "street1": b.get("street1"), "street2": b.get("street2"), "city": b.get("city"),
        "state_or_country": b.get("stateOrCountry"), "zip_code": b.get("zipCode"),
        "country_code": b.get("countryCode")}) if b else None
    return {"cik": int(f["cik"]), "entity_name": f.get("name") or None,
            "state_of_incorporation": f.get("stateOfIncorporation") or None}, address


def native(e: dict) -> dict:
    """An extracted GLEIF record back in the Golden Copy's shape, read by the
    census's own reader. The extract moved a second address line up when the
    first was empty; that one case compares its street where the census,
    reading the archive, compares only the country."""
    def address(a):
        a = a or {}
        lines = a.get("lines") or []
        return {k: v for k, v in {
            "FirstAddressLine": {"$": lines[0]} if lines else None,
            "AdditionalAddressLine": [{"$": x} for x in lines[1:]] or None,
            "City": {"$": a["city"]} if a.get("city") else None,
            "Region": {"$": a["region"]} if a.get("region") else None,
            "PostalCode": {"$": a["postal"]} if a.get("postal") else None,
            "Country": {"$": a["country"]} if a.get("country") else None}.items() if v}
    return {
        "LEI": {"$": e["lei"]},
        "Entity": {
            "LegalName": {"$": e["legal_name"]},
            "OtherEntityNames": {"OtherEntityName": [{"$": n, "@type": t} for t, n in e.get("other_names") or []]},
            "EntityCategory": {"$": e.get("category")},
            "LegalJurisdiction": {"$": e.get("jurisdiction")},
            "EntityStatus": {"$": e.get("entity_status")},
            "LegalAddress": address(e.get("legal")),
            "HeadquartersAddress": address(e.get("hq")),
        },
        "Registration": {"RegistrationStatus": {"$": e.get("registration_status")}},
    }


def main(coverage_path, scan_path, gleif_path, out_path):
    cohort = {json.loads(l)["cik"]: json.loads(l) for l in open(coverage_path)}
    spec = cascade.spec(POLICY)
    filers, exceptions = [], Counter()
    for line in open(scan_path):
        found = cascade_filer(*sec_row(json.loads(line)))
        if found is None:
            exceptions["sec"] += 1
        else:
            filers.append(found)
    wanted = {f.key for f in filers} - {""}
    inputs = {"spec": spec, "gleif_contract": dataset_contract("level1")}
    # Over-shared addresses count every SEC filer and every GENERAL GLEIF
    # entity, as the census does.
    counts = cascade.count_addresses(f.place for f in filers)
    entities = []
    for n, line in enumerate(open(gleif_path)):
        if n % 500000 == 0:
            print(f"gleif {n}", file=sys.stderr, flush=True)
        e = json.loads(line)
        if e.get("category") != "GENERAL":
            continue
        entity = cascade_entity(native(e), inputs, wanted)
        if entity is None:
            exceptions["gleif"] += 1
            continue
        if entity.place.key:
            counts[entity.place.key] += 1
        if entity.keys & wanted:
            entities.append(entity)
    found = cascade.assign(filers, entities, spec["passes"], address_counts=counts, over_shared=spec["over_shared"])
    matched_sec = {cik: (a["lei"], a["pass"], a["flags"]) for cik, a in found.items()}
    result = {}
    for step in spec["passes"]:
        here = [c for c, (_, p, _) in matched_sec.items() if p == step["pass"]]
        strata = Counter(" + ".join(matched_sec[c][2]) or "clean" for c in here if c in cohort)
        result[step["pass"]] = {"bound_all_filers": len(here), "bound_companies": sum(c in cohort for c in here),
                                "companies_by_stratum": dict(strata)}
    over = sum(1 for k, v in counts.items() if v > spec["over_shared"])

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
        "inputs": {name: {"path": p, "sha256": sha256(p)} for name, p in
                   (("coverage", coverage_path), ("sec_scan", scan_path), ("gleif", gleif_path))},
        "over_shared": {"threshold": spec["over_shared"], "addresses": over},
        "exceptions_never_bound": dict(exceptions),
        "passes": result,
        "companies": len(cohort),
        "bound_companies": sum(c in cohort for c in matched_sec),
        "against_today": {" | ".join(k): v for k, v in sorted(today.items())},
        "labels_by_pass": {" | ".join(k): v for k, v in sorted(labels.items())},
    }
    Path(out_path).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    with open(Path(out_path).with_suffix(".bound.jsonl"), "w") as w:
        for cik, (lei, label, flags) in sorted(matched_sec.items()):
            if cik in cohort:
                w.write(json.dumps({"cik": cik, "lei": lei, "pass": label, "flags": flags}) + "\n")
    print(json.dumps({k: out[k] for k in ("companies", "bound_companies", "passes", "over_shared")}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
