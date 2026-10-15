"""Measure the approved Person and link checks (rebuild ticket 10) on the local copies.

Counts only (the repo is public): names and CIKs stay on this machine.
  PYTHONPATH=. python .scratch/onboarding/sec.submissions.person/measure_quality.py [--examples]
--examples prints up to five names per finding to the terminal; nothing else is written.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from edgar_warehouse.mdm.clean.classification import fired, resolve_rule  # noqa: E402
from edgar_warehouse.rules import files  # noqa: E402

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "sec.ownership"))
import proving_run as ownership  # noqa: E402

CAPTURE = Path.home() / ".local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230"
OUT = HERE / "measure-quality.json"

DEGREE = re.compile(r"(,?\s*(M\.?D|Ph\.?\s?D|J\.?D|M\.?B\.?A|C\.?P\.?A|Esq|D\.?D\.?S|M\.?B|R\.?N|CFA)\.?)+\s*$", re.I)
SUFFIX = re.compile(r"\b(JR|SR|II|III|IV)\.?\s*$", re.I)
MARKS = {
    "asterisk": re.compile(r"\*"),
    "dagger": re.compile(r"[†‡§¶#]"),
    "parenthesised_number": re.compile(r"\(\s*\d+\s*\)"),
    "superscript": re.compile(r"[¹²³⁰-⁹]"),
    "trailing_digit": re.compile(r"\D\d{1,2}\s*$"),
    "any_digit": re.compile(r"\d"),
}


def shapes(name: str | None) -> list[str]:
    if name is None or not str(name).strip():
        return ["empty"]
    name = str(name)
    found = []
    if not any(unicodedata.category(c).startswith("L") for c in name):
        found.append("no_letter")
    if any(c.isalpha() and not c.isascii() for c in name):
        found.append("non_ascii_letter")
    if "’" in name or "‘" in name:
        found.append("curly_apostrophe")
    if "'" in name:
        found.append("straight_apostrophe")
    if DEGREE.search(name):
        found.append("degree_suffix")
    if SUFFIX.search(name):
        found.append("generational_suffix")
    found += [f"mark:{k}" for k, rx in MARKS.items() if rx.search(name)]
    return found


def submissions(examples) -> dict:
    policy = files.policy()
    named = files.mdm_contract("sec.submissions.person", "sec.submissions.person.v1")["adapter"]["classification"]
    rule, doc = resolve_rule(policy, named), policy["kinds"]["person"]
    tally, people = Counter(), 0
    for line in (CAPTURE / "receipts.jsonl").open():
        key = json.loads(line).get("key", "")
        if not re.search(r"CIK\d{10}\.json$", key) or "/pagination/" in key:
            continue
        row = json.loads((CAPTURE / "bronze" / key.removeprefix("warehouse/bronze/")).read_bytes())
        if fired(rule, row, doc)[0] != "person":
            continue
        people += 1
        cik = str(row.get("cik") or "")
        if not (cik.isdigit() and len(cik) <= 10 and int(cik) > 0):
            tally["cik_invalid"] += 1
        for s in shapes(row.get("name")):
            tally[s] += 1
            examples[f"submissions {s}"].append(row.get("name"))
    return {"people": people, "findings": dict(sorted(tally.items()))}


def owners(examples) -> dict:
    tally, links, rows = Counter(), Counter(), 0
    for _, tables in ownership.filings():
        for owner in tables.get("reporting_owner", []):
            rows += 1
            person_role = bool(owner.get("is_director") or owner.get("is_officer"))
            for s in shapes(owner.get("rpt_owner_name")):
                tally[s] += 1
                if person_role:
                    tally[f"director_or_officer {s}"] += 1
                examples[f"ownership {s}"].append(owner.get("rpt_owner_name"))
            held = [c for c in ("is_director", "is_officer", "is_ten_percent_owner") if owner.get(c) is True]
            for c in held:
                links[f"held {c}"] += 1
            issuer = owner.get("issuer_cik")
            if held and not issuer:
                links["held, issuer_cik missing"] += 1
            if held and not owner.get("period_of_report"):
                links["held, period_of_report missing"] += 1
            if held and issuer and str(issuer).strip().lstrip("0") == str(owner.get("rpt_owner_cik") or "").lstrip("0"):
                links["held, owner is the issuer"] += 1
            if not held:
                links["no capacity held"] += 1
            if owner.get("is_other") is True:
                links["is_other true"] += 1
    return {"owner_rows": rows, "findings": dict(sorted(tally.items())), "links": dict(sorted(links.items()))}


def main() -> None:
    examples: dict[str, list] = defaultdict(list)
    result = {"submissions_person": submissions(examples), "ownership": owners(examples)}
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if "--examples" in sys.argv:
        for k, v in sorted(examples.items()):
            print(k, v[:5])


if __name__ == "__main__":
    main()
