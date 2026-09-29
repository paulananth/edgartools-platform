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

The passes run in the production function (`edgar_warehouse/mdm/clean/
cascade.py`, `assign`), so this measures what the engine runs. Each pass
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

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord
from edgar_warehouse.mdm.clean.cascade import Entity, Filer, assign, count_addresses, fit_place
from edgar_warehouse.mdm.clean.names import edgar_jurisdiction, legal_form_key, sec_legal_form_key
from edgar_warehouse.mdm.clean.quality import apply
from edgar_warehouse.rules import files

HERE = Path(__file__).parent
OVER_SHARED = 25
PASSES = [
    {"pass": "P1 name + street + city + postcode", "compare": ["street", "city", "postcode"]},
    {"pass": "P2 name + street + postcode", "compare": ["street", "postcode"]},
    {"pass": "P3 name + street + city", "compare": ["street", "city"]},
    {"pass": "P4 name + postcode", "compare": ["postcode"]},
    {"pass": "P5 name + city", "compare": ["city"]},
    {"pass": "P6 name + country", "compare": []},
    {"pass": "P7 name alone", "compare": None},
]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quality_block(source: str, code: str) -> dict:
    body = files.load_source(files.ROOT / "sources" / source / "source.yaml")
    return body["mdm"][code]["contract"].get("quality") or {}


def sec_filer(f: dict, block: dict) -> Filer | None:
    b = (f.get("addresses") or {}).get("business") or {}
    where = edgar_jurisdiction(b.get("stateOrCountry") or b.get("countryCode"))
    country = where.split("-")[0] if where else None
    address = {k: v for k, v in {
        "street": b.get("street1"), "street2": b.get("street2"), "city": b.get("city"),
        "region": b.get("stateOrCountry"), "postcode": b.get("zipCode"), "country": country}.items() if v}
    fields = {"name": f.get("name") or None, "address": address or None,
              "state_of_incorporation": f.get("stateOfIncorporation") or None}
    matching: dict = {}
    try:
        q = apply(block, fields, matching)
    except UnsupportedRecord:
        return None  # an exception never merges
    return Filer(cik=f["cik"], key=sec_legal_form_key(fields["name"]),
                 place=fit_place({"provenance": {"quality": q}}, matching, ("address",)),
                 incorporated=edgar_jurisdiction(fields["state_of_incorporation"]), business_country=country)


def gleif_address(a: dict | None) -> dict | None:
    a = a or {}
    lines = a.get("lines") or []
    return {k: v for k, v in {
        "street": lines[0] if lines else None, "street2": "\n".join(lines[1:]) or None,
        "city": a.get("city"), "region": a.get("region"), "postcode": a.get("postal"),
        "country": a.get("country")}.items() if v} or None


def gleif_entity(e: dict, block: dict, keys: frozenset) -> Entity | None:
    fields = {"name": e.get("legal_name") or None, "address": gleif_address(e.get("legal"))}
    hq = gleif_address(e.get("hq"))
    matching = {"headquarters_address": hq} if hq else {}
    try:
        q = apply(block, fields, matching)
    except UnsupportedRecord:
        return None
    return Entity(lei=e["lei"], keys=keys, place=fit_place({"provenance": {"quality": q}}, matching),
                  jurisdiction=e.get("jurisdiction"), last_update=e.get("last_update") or "",
                  eligible=(e.get("entity_status") == "ACTIVE"
                            and e.get("registration_status") not in ("DUPLICATE", "ANNULLED")))


def main(coverage_path, scan_path, gleif_path, out_path):
    cohort = {json.loads(l)["cik"]: json.loads(l) for l in open(coverage_path)}
    sec_block = quality_block("sec.submissions.company", "sec.submissions.company.v1")
    gleif_block = quality_block("gleif", "gleif.level1.v1")
    filers, exceptions = [], Counter()
    for line in open(scan_path):
        filer = sec_filer(json.loads(line), sec_block)
        if filer is None:
            exceptions["sec"] += 1
        else:
            filers.append(filer)
    wanted = {f.key for f in filers} - {""}
    # Over-shared addresses are counted as ticket 22 measured the threshold:
    # every SEC filer and every GENERAL GLEIF entity. Only GENERAL can bind.
    counts = count_addresses(f.place for f in filers)
    entities = []
    for n, line in enumerate(open(gleif_path)):
        if n % 500000 == 0:
            print(f"gleif {n}", file=sys.stderr, flush=True)
        e = json.loads(line)
        if e.get("category") != "GENERAL":
            continue
        names = [e["legal_name"]] + [name for _, name in e.get("other_names") or []]
        keys = frozenset(legal_form_key(name) for name in names) & wanted
        entity = gleif_entity(e, gleif_block, keys)
        if entity is None:
            exceptions["gleif"] += 1
            continue
        counts.update([entity.place.key] if entity.place.key else [])
        if keys:
            entities.append(entity)
    found = assign(filers, entities, PASSES, address_counts=counts, over_shared=OVER_SHARED)
    matched_sec = {cik: (a["lei"], a["pass"], a["flags"]) for cik, a in found.items()}
    result = {}
    for step in PASSES:
        here = [c for c, (_, p, _) in matched_sec.items() if p == step["pass"]]
        strata = Counter(" + ".join(matched_sec[c][2]) or "clean" for c in here if c in cohort)
        result[step["pass"]] = {"bound_all_filers": len(here), "bound_companies": sum(c in cohort for c in here),
                                "companies_by_stratum": dict(strata)}
    over = sum(1 for k, v in counts.items() if v > OVER_SHARED)

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
        "over_shared": {"threshold": OVER_SHARED, "addresses": over},
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
