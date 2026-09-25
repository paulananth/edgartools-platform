"""Ticket 08: how the draft matching rule falls over the whole Company population.

The draft rule (tuned on the 883 development pairs, `08-dev-levers.py`):

1. the SEC name and the GLEIF legal name are equal with the legal form kept
   (`legal_form_key`, `edgar_warehouse/mdm/clean/names.py`: WAYFAIR INC and WAYFAIR LLC differ);
2. that name key belongs to exactly one GLEIF legal entity in the whole
   pinned publication, counting its legal and other names but not branches
   (a branch carries its head office's name and is not a separate legal
   entity);
3. that one record is category GENERAL and ACTIVE, and not DUPLICATE or
   ANNULLED;
4. the name key belongs to exactly one SEC filer among all 76,230, counting
   current and former names;
5. the jurisdiction agrees (SEC state of incorporation mapped to ISO, as GLEIF
   writes it), or the headquarters postal code agrees within the same country.

Uniqueness is counted over the whole GLEIF publication and every SEC filer,
never over what a Stage happens to hold, so load order cannot change it.

    python .scratch/company-mastering/research/08-coverage.py \\
        <cm08-companies.jsonl> <cm08-sec-scan.jsonl> <cm08-gleif-all.jsonl> <out.jsonl>
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from edgar_warehouse.mdm.clean.names import (  # noqa: E402  the production code
    edgar_jurisdiction,
    jurisdictions_agree,
    jurisdictions_conflict,
    legal_form_key,
    postal_codes_agree,
    sec_legal_form_key,
)

FOUR = {"0000320193": "Apple", "0000789019": "Microsoft",
        "0001306965": "Shell", "0000937966": "ASML"}


def business_country(sec_addresses: dict | None) -> str | None:
    business = (sec_addresses or {}).get("business") or {}
    place = edgar_jurisdiction(business.get("stateOrCountry") or business.get("countryCode"))
    return place.split("-")[0] if place else None


def postal_agrees(sec_addresses: dict | None, hq: dict | None) -> bool:
    business = (sec_addresses or {}).get("business") or {}
    if not hq or not business:
        return False
    # A foreign address may carry its code in countryCode, not stateOrCountry.
    place = edgar_jurisdiction(business.get("stateOrCountry") or business.get("countryCode"))
    return postal_codes_agree(
        business.get("zipCode"),
        place.split("-")[0] if place else None,
        hq.get("postal"),
        (hq.get("country") or "").upper() or None,
    )


def main(companies: str, scan: str, gleif: str, out: str) -> None:
    rows = [json.loads(line) for line in open(companies)]
    for r in rows:
        r["key"] = sec_legal_form_key(r["name"])
    wanted = {r["key"] for r in rows}
    # The veto counts every name either side has carried; the match reads
    # only the current SEC name against the GLEIF legal name.
    sec_holders: dict[str, set] = defaultdict(set)
    for line in open(scan):
        s = json.loads(line)
        if s.get("cik") is None:
            continue
        for name in [s.get("name")] + [n.get("name") for n in s.get("formerNames") or []]:
            if name:
                sec_holders[sec_legal_form_key(name)].add(s["cik"])
    sec_count = Counter({k: len(v) for k, v in sec_holders.items() if k in wanted})
    by_key: dict[str, list[dict]] = defaultdict(list)
    vetoers: dict[str, dict] = defaultdict(dict)
    for line in open(gleif):
        g = json.loads(line)
        k = legal_form_key(g["legal_name"])
        if k in wanted:
            by_key[k].append(g)
        if g["category"] == "BRANCH":
            continue
        for key in {k} | {legal_form_key(n) for _, n in g["other_names"]}:
            if key in wanted:
                vetoers[key][g["lei"]] = g
    outcomes: Counter = Counter()
    with open(out, "w") as f:
        for r in rows:
            cands = by_key.get(r["key"], [])
            entities = [g for g in cands if g["category"] != "BRANCH"]
            if not cands:
                outcome = "no GLEIF record with this name"
            elif len(entities) > 1:
                outcome = "defer: name names several GLEIF entities"
            elif set(vetoers[r["key"]]) - {e["lei"] for e in entities}:
                outcome = "defer: another GLEIF entity carries this name as another name"
            elif not entities:
                outcome = "no GLEIF record with this name (branches only)"
            else:
                g = entities[0]
                agree_j = jurisdictions_agree(
                    edgar_jurisdiction(r["state_of_incorporation"]), g["jurisdiction"]
                )
                agree_p = postal_agrees(r["addresses"], g["hq"])
                # Rule 2026-09-25.2: the postal step vetoes two different
                # places of incorporation (the Name-and-postcode rule's misses).
                conflict = jurisdictions_conflict(
                    edgar_jurisdiction(r["state_of_incorporation"]),
                    g["jurisdiction"],
                    sec_business_country=business_country(r["addresses"]),
                )
                if g["category"] != "GENERAL":
                    outcome = f"defer: GLEIF category {g['category']}"
                elif g["registration_status"] in {"DUPLICATE", "ANNULLED"}:
                    outcome = f"defer: GLEIF {g['registration_status']}"
                elif sec_count[r["key"]] > 1:
                    outcome = "defer: name names several SEC filers"
                elif agree_j:
                    outcome = "BIND jurisdiction"
                elif agree_p and not conflict:
                    outcome = "BIND postal"
                elif agree_p:
                    outcome = "defer: postal agrees, jurisdictions conflict"
                else:
                    outcome = "defer: no jurisdiction or postal agreement"
                r["gleif"] = {k: g[k] for k in ("lei", "legal_name", "category",
                                                "jurisdiction", "registration_status",
                                                "entity_status", "legal_form")}
                r["gleif"]["hq"] = g["hq"]
                r["agree"] = {"jurisdiction": agree_j, "postal": agree_p,
                              "conflict": conflict, "postal_rule": agree_p and not conflict}
            # An INACTIVE entity has ceased (merged, dissolved) while its SEC
            # filer still files: the labelling standard reads it unresolved.
            if outcome.startswith("BIND") and r["gleif"]["entity_status"] != "ACTIVE":
                outcome = f"defer: GLEIF entity {r['gleif']['entity_status']}"
            r["outcome"] = outcome
            r["gleif_same_name"] = len(cands)
            r["sec_same_name"] = sec_count[r["key"]]
            outcomes[(outcome, r["step"])] += 1
            f.write(json.dumps(r, sort_keys=True) + "\n")
            if r["cik"] in FOUR:
                print(FOUR[r["cik"]], r["key"], outcome, r.get("gleif", {}).get("lei"))
    total = Counter()
    for (outcome, step), n in sorted(outcomes.items()):
        print(f"{n:6} step {step:>2}  {outcome}")
        total[outcome] += n
    print(json.dumps(dict(total.most_common()), indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
