"""Ticket 08: how the draft matching rule falls over the whole Company population.

The draft rule (tuned on the 883 development pairs, `08-dev-levers.py`):

1. the SEC name and the GLEIF legal name are equal with the legal form kept
   (`form_key`: WAYFAIR INC and WAYFAIR LLC differ);
2. that name key belongs to exactly one GLEIF legal entity in the whole
   pinned publication, not counting branches (a branch carries its head
   office's name and is not a separate legal entity);
3. that one record is category GENERAL, and not DUPLICATE or ANNULLED;
4. the name key belongs to exactly one SEC filer among all 76,230;
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
    # SEC keeps only the digits of a Dutch code ("5504" for "5504 DR"): a
    # shorter SEC code agrees when GLEIF's starts with it, from four characters.
    if s_postal != g_postal and not (len(s_postal) >= 4 and g_postal.startswith(s_postal)):
        return False
    return sec_country(business) == (hq.get("country") or "").upper()


def main(companies: str, scan: str, gleif: str, out: str) -> None:
    rows = [json.loads(line) for line in open(companies)]
    for r in rows:
        r["key"] = form_key(r["name"], sec=True)
    wanted = {r["key"] for r in rows}
    sec_count: Counter = Counter()
    for line in open(scan):
        s = json.loads(line)
        if s.get("cik") is not None and s.get("name"):
            sec_count[form_key(s["name"], sec=True)] += 1
    by_key: dict[str, list[dict]] = defaultdict(list)
    for line in open(gleif):
        g = json.loads(line)
        k = form_key(g["legal_name"])
        if k in wanted:
            by_key[k].append(g)
    outcomes: Counter = Counter()
    with open(out, "w") as f:
        for r in rows:
            cands = by_key.get(r["key"], [])
            entities = [g for g in cands if g["category"] != "BRANCH"]
            if not cands:
                outcome = "no GLEIF record with this name"
            elif len(entities) > 1:
                outcome = "defer: name names several GLEIF entities"
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
