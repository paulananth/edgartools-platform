"""Hand-read labels for the Postcode rule with state veto, 2026-09-25.2 (ticket 08).

Claude read every pair in `08-2-sample.jsonl` (300) and
`08-2-adversarial.jsonl` (315) by hand on 2026-09-25, under
`08-labelling-standard.md`. Every pair is the same legal entity.

The arm that failed the Name-and-postcode rule now holds only pairs where one
side names no place of incorporation, or names only the country (GLEIF's
"US"). Its 78 pairs are all the same entity. The two pairs whose SEC US state
was set aside are Bausch Health (SEC "NJ"; SEC's own Quebec address and
GLEIF's British Columbia jurisdiction agree) and U.S. GoldMining (GLEIF names
only the US).

    python .scratch/company-mastering/research/08-2-label.py
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTES = {
    "0000885590": "Bausch Health Companies: SEC's state NJ set aside; SEC's Quebec "
    "address and GLEIF's British Columbia jurisdiction both put it in Canada.",
    "0001947244": "U.S. GoldMining: SEC Nevada, GLEIF names only the US; Vancouver "
    "headquarters on both sides.",
    "0000070502": "National Rural Utilities Cooperative Finance: a District of "
    "Columbia cooperative on both sides.",
}


def label(name: str) -> list[dict]:
    path = HERE / name
    with path.open() as f:
        rows = [json.loads(line) for line in f]
    for r in rows:
        r["final"] = "same"
        r["note"] = NOTES.get(r["cik"], "same legal entity: name with its legal form, "
                              "postcode and place agree")
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    return rows


if __name__ == "__main__":
    for name in ("08-2-sample.jsonl", "08-2-adversarial.jsonl"):
        rows = label(name)
        print(name, len(rows), "pairs,", sum(r["final"] != "same" for r in rows), "not the same")
