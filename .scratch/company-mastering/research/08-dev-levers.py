"""Ticket 08: which stricter evidence makes a SEC-to-GLEIF name match safe?

Development data only: the 883 reviewed candidate pairs from
gleif-company-augmentation ticket 02 (`02-reviewed-candidates.jsonl`), each
with a reviewer's disposition. They tune the rule; they never qualify it (the
ticket: "the 308 adjudicated seed links are comparison only").

Precision here counts only `same_legal_entity` as correct; `unresolved` and
`different_legal_entity` both count as wrong, so it is conservative.

Fixes over the ticket 02 comparison, found by reading its rows:
- SEC puts a US state code in `country` ("MI"); a two-letter US state or DC
  means the country is US.
- A registered agent's address (the Corporation Trust Company at 1209 Orange
  St, Wilmington, and others) is shared by many thousands of entities, so it
  is no address evidence. Only GLEIF's headquarters address, and a legal
  address that names no agent, count.

    uv run python .scratch/company-mastering/research/08-dev-levers.py \\
        <02-reviewed-candidates.jsonl> <cm08-companies.jsonl>
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from statistics import NormalDist

US = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
    "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "PR",
}
AGENT = re.compile(
    r"CORPORATION TRUST|C O CT CORP|CT CORPORATION|CORPORATION SERVICE COMPANY|"
    r"\bCSC\b|REGISTERED AGENT|NATIONAL REGISTERED AGENTS|INCORP SERVICES|"
    r"UNITED AGENT|COGENCY GLOBAL|MAPLES CORPORATE|WALKERS CORPORATE|"
    r"INTERTRUST|OGIER|CONYERS|APPLEBY|HARNEYS|VISTRA|TMF |"
    r"1209 ORANGE|251 LITTLE FALLS|2711 CENTERVILLE|850 NEW BURTON|"
    r"PO BOX 309|P O BOX 309|UGLAND HOUSE"
)


FORMS = [
    ("L L C", "LLC"), ("L P", "LP"), ("L L P", "LLP"), ("P L C", "PLC"),
    ("N V", "NV"), ("S A", "SA"), ("A G", "AG"), ("S E", "SE"), ("B V", "BV"),
    ("CORPORATION", "CORP"), ("INCORPORATED", "INC"), ("COMPANY", "CO"),
    ("LIMITED", "LTD"), ("HOLDINGS", "HLDGS"), ("INTERNATIONAL", "INTL"),
]
SEC_TAG = re.compile(r"\s*/[A-Z0-9 .]{1,6}/?\s*$")


def form_key(name: str | None, sec: bool = False) -> str:
    """A name with its legal form kept: WAYFAIR INC and WAYFAIR LLC differ."""
    import unicodedata

    text = str(name or "")
    if sec:
        text = SEC_TAG.sub("", text.upper())
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).upper()
    text = text.replace("&", " AND ")
    text = " " + re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", text)).strip() + " "
    for long, short in FORMS:
        text = text.replace(f" {long} ", f" {short} ")
    text = text.strip()
    text = text.removeprefix("THE ")
    return text


def wilson(correct: int, n: int, confidence: float = 0.95) -> float:
    if n == 0:
        return 0.0
    z = NormalDist().inv_cdf(confidence)
    p = correct / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - spread) / (1 + z * z / n)


def sec_country(a: dict) -> str:
    region = a["normalized"]["region"]
    country = a["normalized"]["country"]
    if region in US or country in US:
        return "US"
    return country or region


def agent(a: dict) -> bool:
    return bool(AGENT.search(" ".join(a["normalized"]["lines"])))


def address_evidence(r: dict) -> dict:
    ctx = r["context_comparison"]
    sec = [a for a in ctx["mdm_addresses"] if a["source"] == "sec_business"] or ctx[
        "mdm_addresses"
    ]
    out = {"hq_postal": False, "hq_street": False, "hq_city": False,
           "legal_postal_non_agent": False, "country": None}
    for g in ctx["gleif_addresses"]:
        gn = g["normalized"]
        usable = g["source"] == "gleif_headquarters" or not agent(g)
        for s in sec:
            sn = s["normalized"]
            same_country = sec_country(s) == gn["country"]
            if out["country"] is not True:
                out["country"] = same_country
            if not (usable and same_country):
                continue
            postal = bool(sn["postal_code"]) and sn["postal_code"] == gn["postal_code"]
            street = bool(set(sn["street_numbers"]) & set(gn["street_numbers"]))
            city = bool(sn["city"]) and sn["city"] == gn["city"]
            if g["source"] == "gleif_headquarters":
                out["hq_postal"] |= postal
                out["hq_street"] |= street and postal
                out["hq_city"] |= city
            else:
                out["legal_postal_non_agent"] |= postal
    return out


def features(r: dict) -> dict:
    nc = r["name_comparison"]
    g = r["gleif_raw"]
    ctx = r["context_comparison"]
    addr = address_evidence(r)
    sec_key = form_key(r["mdm_raw"]["sec_entity_name"], sec=True)
    legal = [n["raw"] for n in g["names"] if n["source"] == "gleif_legal"]
    return {
        "form_exact": any(form_key(n) == sec_key for n in legal),
        "form_exact_any": any(form_key(n["raw"]) == sec_key for n in g["names"]),
        "name": nc["kind"],
        "former": nc["uses_former_name"],
        "general": g["category"] == "GENERAL",
        "status_ok": g["registration_status"] not in {"DUPLICATE", "ANNULLED"},
        "issued": g["registration_status"] == "ISSUED",
        "jur_match": ctx["jurisdiction_match"],
        "jur_conflict": ctx["jurisdiction_conflict"],
        **addr,
    }


BASE = lambda f: f["form_exact"] and f["general"] and f["status_ok"]
RULES = {
    "FORM: SEC name = GLEIF legal name, form kept": lambda f, r: BASE(f),
    "FORM + jurisdiction match": lambda f, r: BASE(f) and f["jur_match"],
    "FORM + HQ postal": lambda f, r: BASE(f) and f["hq_postal"],
    "FORM + (jurisdiction or HQ postal)": lambda f, r: BASE(f) and (f["jur_match"] or f["hq_postal"]),
    "FORM + jurisdiction and HQ postal": lambda f, r: BASE(f) and f["jur_match"] and f["hq_postal"],
    "FORM + no jurisdiction conflict + same country": lambda f, r: BASE(f) and not f["jur_conflict"] and f["country"],
    "FORM(any name) + (jurisdiction or HQ postal)": lambda f, r: f["form_exact_any"] and f["general"] and f["status_ok"] and (f["jur_match"] or f["hq_postal"]),
    "tier B as measured": lambda f, r: r["evidence_tier"] == "B",
    "current name exact/suffix, GENERAL, status ok": lambda f, r: (
        f["name"] != "fuzzy" and not f["former"] and f["general"] and f["status_ok"]
    ),
    "+ jurisdiction match": lambda f, r: (
        f["name"] != "fuzzy" and not f["former"] and f["general"] and f["status_ok"]
        and f["jur_match"]
    ),
    "+ HQ postal": lambda f, r: (
        f["name"] != "fuzzy" and not f["former"] and f["general"] and f["status_ok"]
        and f["hq_postal"]
    ),
    "+ HQ postal and street number": lambda f, r: (
        f["name"] != "fuzzy" and not f["former"] and f["general"] and f["status_ok"]
        and f["hq_street"]
    ),
    "+ jurisdiction and HQ postal": lambda f, r: (
        f["name"] != "fuzzy" and not f["former"] and f["general"] and f["status_ok"]
        and f["jur_match"] and f["hq_postal"]
    ),
    "+ HQ postal or non-agent legal postal": lambda f, r: (
        f["name"] != "fuzzy" and not f["former"] and f["general"] and f["status_ok"]
        and (f["hq_postal"] or f["legal_postal_non_agent"])
    ),
    "+ HQ city, no jurisdiction conflict": lambda f, r: (
        f["name"] != "fuzzy" and not f["former"] and f["general"] and f["status_ok"]
        and f["hq_city"] and not f["jur_conflict"]
    ),
    "fuzzy name + HQ postal and street": lambda f, r: (
        f["name"] == "fuzzy" and not f["former"] and f["general"] and f["status_ok"]
        and f["hq_street"]
    ),
}


def main(reviewed: str, companies: str) -> None:
    active = {json.loads(line)["cik"] for line in open(companies)}
    rows = [json.loads(line) for line in open(reviewed)]
    for r in rows:
        r["cik10"] = f"{int(r['cik']):010d}"
        r["f"] = features(r)
    for scope, pool in (
        ("all 883", rows),
        ("CIK is an Account hold-back Company", [r for r in rows if r["cik10"] in active]),
    ):
        print(f"\n== {scope}: {len(pool)} pairs, "
              f"{len({r['cik10'] for r in pool})} CIKs ==")
        print(f"{'rule':52} {'fired':>5} {'uniq':>5} {'same':>5} {'prec':>6} {'LB95':>6}")
        for name, rule in RULES.items():
            fired = [r for r in pool if rule(r["f"], r)]
            per_cik = Counter(r["cik10"] for r in fired)
            per_lei = Counter(r["lei"] for r in fired)
            unique = [r for r in fired if per_cik[r["cik10"]] == 1 and per_lei[r["lei"]] == 1]
            same = sum(r["manual_review"]["candidate_disposition"] == "same_legal_entity"
                       for r in unique)
            n = len(unique)
            print(f"{name:52} {len(fired):5} {n:5} {same:5} "
                  f"{(same / n if n else 0):6.3f} {wilson(same, n):6.3f}")
        wrong = defaultdict(list)
        rule = RULES["FORM + (jurisdiction or HQ postal)"]
        for r in pool:
            if rule(r["f"], r) and r["manual_review"]["candidate_disposition"] != "same_legal_entity":
                wrong[r["manual_review"]["reason_code"]].append(
                    (r["cik10"], r["name_comparison"]["mdm"]["raw"],
                     r["name_comparison"]["gleif"]["raw"], r["gleif_raw"]["registration_status"])
                )
        print("  wrong under 'FORM + (jurisdiction or HQ postal)':")
        for reason, items in wrong.items():
            for item in items:
                print("   ", reason, item)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
