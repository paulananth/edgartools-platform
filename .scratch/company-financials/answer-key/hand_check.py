"""Ticket 44, by hand: each restatement and stock split in the answer key, read
again from the raw company facts file (exact decimals), with every filed copy of
the period listed and the key's choice compared with the latest-filed copy.
Local only: prints real figures to the terminal, never written to the repo.

    python3 -I .scratch/company-financials/answer-key/hand_check.py <proving/company-facts folder>
"""
import gzip
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(sys.argv[1])
key = json.loads((ROOT / "answer-key.json").read_text())
CASES = json.loads((ROOT / "answer-key-cases.json").read_text())["cases"]


def chosen(case):
    """The chosen company that covers a hard case (the cases file is local)."""
    return next(cik for cik, cases in CASES.items() if case in cases)


def raw(cik):
    with gzip.open(ROOT / "cohort" / f"{cik}.json.gz", "rt") as f:
        return json.loads(f.read(), parse_float=Decimal, parse_int=Decimal)


def copies(doc, taxonomy, concept, unit, start, end):
    facts = doc["facts"].get(taxonomy, {}).get(concept, {}).get("units", {}).get(unit, [])
    return [f for f in facts if f.get("end") == end and f.get("start") == start]


def check(cik, want):
    doc = raw(cik)
    company = key["companies"][cik]
    found = []
    for year, items in sorted(company["line_items"].items()):
        for name, item in items.items():
            if not item.get("concept") or item.get("value") is None or "tried" not in item:
                continue
            start = next((c.get("start") for t in item["tried"] for c in t["copies"]
                          if c["accn"] == item["accn"]), None)
            filed = copies(doc, item["taxonomy"], item["concept"], item["unit"], start, item["end"])
            values = {Decimal(str(f["val"])) for f in filed}
            if len(values) < 2:
                continue
            latest = max(filed, key=lambda f: (f["filed"], f["accn"]))
            ratio = None
            others = [v for v in values if v != Decimal(str(latest["val"]))]
            if want == "split" and others and others[0] != 0:
                ratio = Decimal(str(latest["val"])) / others[0]
            found.append((year, name, item["concept"], len(filed), len(values),
                          Decimal(item["value"]) == Decimal(str(latest["val"])), ratio))
    return found


for cik, want in [(c, "restatement") for c, cases in CASES.items() if "restatement" in cases] + [(chosen("stock_split"), "split")]:
    rows = check(cik, want)
    agree = sum(1 for r in rows if r[5])
    print(f"== {', '.join(CASES[cik])}: {want}: {len(rows)} line-item years with differing filed copies; key takes the latest in {agree}")
    for r in rows[:12]:
        print("  ", r[0], r[1], r[2], f"copies={r[3]} distinct={r[4]} latest={r[5]}", f"ratio={r[6]:.6f}" if r[6] else "")
