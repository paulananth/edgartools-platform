"""Hand-read labels for the SEC-to-GLEIF matching rules, version 2026-09-25.1 (ticket 08).

Claude read every pair in `08-1-sample.jsonl` (573) and
`08-1-adversarial.jsonl` (326) by hand on 2026-09-25, under
`08-labelling-standard.md`: SEC and GLEIF names, former and other names,
state or country of incorporation, both addresses, legal form code, status.
A pair not listed below is the same legal entity.

**One pattern holds every miss.** The postal step fired where SEC and GLEIF
each name a definite place of incorporation and the two differ. The rows alone
cannot say which is right, so under the standard ("where the evidence does
not decide, the label is unresolved, and unresolved counts as wrong") each is
unresolved. It stays unresolved even where outside knowledge suggests SEC's
field is stale (Dillard's, Dover and NetApp are Delaware corporations): the
standard admits only the two records. One pair is worse than unresolved: AAON,
Inc. is a Nevada parent with an Oklahoma operating subsidiary of the same name,
and GLEIF's record is the Oklahoma one.

A conflict the rows themselves explain is read as the same entity:
- Energy Focus: SEC's own conformed name carries "/DE", GLEIF's state;
- Voyager Technologies: SEC's names record the move, "/DE" then "/TX";
- Terra Innovatum Global: both sources record the conversion from the Italian
  S.R.L. to the Dutch N.V.

The jurisdiction step has no miss in its sample or in any arm.

    python .scratch/company-mastering/research/08-1-label.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

UNRESOLVED = {
    # Sample pairs (postal step), jurisdictions in conflict.
    "0000927971": "Bank of Montreal: SEC Ontario, GLEIF Quebec; the rows do not decide.",
    "0001468174": "Hyatt Hotels: SEC Illinois, GLEIF Delaware.",
    "0001561550": "Datadog: SEC Nevada, GLEIF Delaware.",
    "0001665918": "US Foods Holding: SEC Illinois, GLEIF Delaware.",
    "0001680062": "ACM Research: SEC California, GLEIF Delaware.",
    "0001795250": "Sphere Entertainment: SEC Nevada, GLEIF Delaware (a conversion the "
    "rows do not show).",
    # Adversarial pairs, arm 'postal step, no jurisdiction agreement'.
    "0000028917": "Dillard's: SEC Texas, GLEIF Delaware.",
    "0000029905": "Dover: SEC New York, GLEIF Delaware.",
    "0000081362": "Quaker Chemical: SEC Pennsylvania, GLEIF Delaware with a Delaware "
    "registered-agent address.",
    "0000098677": "Tootsie Roll Industries: SEC Virginia, GLEIF Illinois.",
    "0000918251": "Motorcar Parts of America: SEC New York, GLEIF California.",
    "0001002047": "NetApp: SEC California, GLEIF Delaware.",
    "0001057060": "MarineMax: SEC Delaware, GLEIF Florida.",
    "0001104506": "Insmed: SEC Virginia, GLEIF New Jersey.",
    "0001137091": "Power Solutions International: SEC Illinois, GLEIF Delaware.",
    "0001211583": "Fennec Pharmaceuticals: SEC British Columbia, GLEIF Ontario.",
    "0001509261": "Rezolute: SEC Nevada, GLEIF Delaware.",
    "0001547903": "NMI Holdings: SEC California, GLEIF Delaware.",
    "0001616000": "Xenia Hotels & Resorts: SEC Florida, GLEIF Maryland.",
    "0001717307": "Industrial Logistics Properties Trust: SEC Maryland, GLEIF "
    "Massachusetts.",
    "0001852973": "Borealis Foods: SEC Cayman Islands, GLEIF Ontario.",
    "0001876183": "IHS Holding: SEC Mauritius, GLEIF Cayman Islands.",
    "0001945415": "HUHUTECH International: SEC China, GLEIF Cayman Islands.",
    "0002075320": "Polaryx Therapeutics: SEC Wyoming, GLEIF Nevada.",
}
DIFFERENT = {
    "0000824142": "AAON, Inc.: SEC Nevada, GLEIF Oklahoma. The Nevada parent has an "
    "Oklahoma operating subsidiary of the same name; GLEIF's is that subsidiary.",
}
SAME_WITH_NOTE = {
    "0000924168": "Energy Focus: SEC state Ohio, but SEC's own name carries /DE, GLEIF's.",
    "0001788060": "Voyager Technologies: SEC names record /DE then /TX; one entity "
    "converted, GLEIF not yet updated.",
    "0002067627": "Terra Innovatum Global: both sources record the S.R.L. to N.V. "
    "conversion.",
    "0001376986": "Tennessee Valley Authority: a corporation the US owns; a Company "
    "(glossary).",
}


def label(name: str) -> list[dict]:
    path = HERE / name
    with path.open() as f:
        rows = [json.loads(line) for line in f]
    for r in rows:
        if r["cik"] in DIFFERENT:
            r["final"], r["note"] = "different", DIFFERENT[r["cik"]]
        elif r["cik"] in UNRESOLVED:
            r["final"], r["note"] = "unresolved", UNRESOLVED[r["cik"]]
        else:
            r["final"] = "same"
            r["note"] = SAME_WITH_NOTE.get(r["cik"], "same legal entity: name with its "
                                           "legal form, place and address agree")
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    return rows


if __name__ == "__main__":
    listed = set(UNRESOLVED) | set(DIFFERENT)
    seen = set()
    for name in ("08-1-sample.jsonl", "08-1-adversarial.jsonl"):
        rows = label(name)
        seen |= {r["cik"] for r in rows}
        print(name, sum(r["final"] != "same" for r in rows), "not the same entity")
    missing = listed - seen
    if missing:
        raise SystemExit(f"labels name CIKs no draw holds: {sorted(missing)}")
