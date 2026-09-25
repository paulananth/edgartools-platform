"""Ticket 08: how the draft matching rule falls over the whole Company population.

The draft rule (tuned on the 883 development pairs, `08-dev-levers.py`):

1. the SEC name and the GLEIF legal name are equal with the legal form kept
   (`form_key`: WAYFAIR INC and WAYFAIR LLC differ);
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

import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("levers", HERE / "08-dev-levers.py")
levers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(levers)
form_key = levers.form_key
CODES = json.loads((HERE / "08-edgar-codes.json").read_text())
FOUR = {"0000320193": "Apple", "0000789019": "Microsoft",
        "0001306965": "Shell", "0000937966": "ASML"}


def sec_jurisdiction(code: str | None) -> str | None:
    if not code:
        return None
    code = code.strip().upper()
    if code in CODES["us_states"]:
        return f"US-{code}"
    return CODES["codes"].get(code)


def jurisdiction_agrees(sec: str | None, gleif: str | None) -> bool:
    if not sec or not gleif:
        return False
    gleif = gleif.upper()
    if sec == gleif:
        return True
    # A territory SEC codes as a state, GLEIF as a country (PR, GU, VI).
    if sec.startswith("US-") and sec[3:] in CODES["us_territory_countries"]:
        return gleif == CODES["us_territory_countries"][sec[3:]]
    # Outside the US a country-only side agrees with a subdivision of it.
    s_country, g_country = sec.split("-")[0], gleif.split("-")[0]
    if s_country == "US" or s_country != g_country:
        return False
    return "-" not in sec or "-" not in gleif


def postal(value: str | None) -> str:
    text = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return text[:5] if re.fullmatch(r"\d{5}(\d{4})?", text) else text


def sec_country(address: dict) -> str | None:
    """A foreign address may carry its code in countryCode, not stateOrCountry."""
    j = sec_jurisdiction(address.get("stateOrCountry") or address.get("countryCode"))
    return j.split("-")[0] if j else None


def postal_agrees(sec_addresses: dict | None, hq: dict | None) -> bool:
    if not hq or not sec_addresses:
        return False
    business = (sec_addresses or {}).get("business") or {}
    s_postal, g_postal = postal(business.get("zipCode")), postal(hq.get("postal"))
    if not s_postal or not g_postal:
        return False
    country = (hq.get("country") or "").upper()
    if sec_country(business) != country:
        return False
    if s_postal == g_postal:
        return True
    # SEC keeps only the four digits of a Dutch code ("5504" for "5504 DR").
    # Only that shape agrees on a prefix: four digits against four digits and
    # two letters, in the Netherlands.
    return (
        country == "NL"
        and re.fullmatch(r"\d{4}", s_postal) is not None
        and re.fullmatch(r"\d{4}[A-Z]{2}", g_postal) is not None
        and g_postal.startswith(s_postal)
    )


def main(companies: str, scan: str, gleif: str, out: str) -> None:
    rows = [json.loads(line) for line in open(companies)]
    for r in rows:
        r["key"] = form_key(r["name"], sec=True)
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
                sec_holders[form_key(name, sec=True)].add(s["cik"])
    sec_count = Counter({k: len(v) for k, v in sec_holders.items() if k in wanted})
    by_key: dict[str, list[dict]] = defaultdict(list)
    vetoers: dict[str, dict] = defaultdict(dict)
    for line in open(gleif):
        g = json.loads(line)
        k = form_key(g["legal_name"])
        if k in wanted:
            by_key[k].append(g)
        if g["category"] == "BRANCH":
            continue
        for key in {k} | {form_key(n) for _, n in g["other_names"]}:
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
                agree_j = jurisdiction_agrees(
                    sec_jurisdiction(r["state_of_incorporation"]), g["jurisdiction"]
                )
                agree_p = postal_agrees(r["addresses"], g["hq"])
                if g["category"] != "GENERAL":
                    outcome = f"defer: GLEIF category {g['category']}"
                elif g["registration_status"] in {"DUPLICATE", "ANNULLED"}:
                    outcome = f"defer: GLEIF {g['registration_status']}"
                elif sec_count[r["key"]] > 1:
                    outcome = "defer: name names several SEC filers"
                elif not (agree_j or agree_p):
                    outcome = "defer: no jurisdiction or postal agreement"
                else:
                    outcome = "BIND " + ("jurisdiction" if agree_j else "postal")
                r["gleif"] = {k: g[k] for k in ("lei", "legal_name", "category",
                                                "jurisdiction", "registration_status",
                                                "entity_status", "legal_form")}
                r["gleif"]["hq"] = g["hq"]
                r["agree"] = {"jurisdiction": agree_j, "postal": agree_p}
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
