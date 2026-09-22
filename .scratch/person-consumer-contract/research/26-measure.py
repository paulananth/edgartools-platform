"""Ticket 26: the measures 10-reparse-bronze.py's score stage does not take.

Reads two parse outputs (``rows.jsonl`` from 10-reparse-bronze.py's parse
stage) — the ticket 10 baseline and the ticket 26 re-parse — collapses each
exactly as that score stage does, and reports for both:

- ``person-name@v2`` acceptance (``is_person_name_candidate``), the rate the
  ticket cites as 93.1%;
- names still carrying any digit, which also catches a superscript the HTML
  flattened to a plain digit ("Brendan Brothers6") — the score stage's
  footnote detector looks only for parentheses and superscript characters;
- executives spelled more than one way across one company's filings, where
  the spellings differ only by a marker ("Raymond F. Lancy" / "Raymond F.
  Lancy (1)"; "Daniel Pinto7" / "Pinto8" / "Pinto11"), and how many of those
  involve a flattened-superscript digit. Both sides are grouped with the
  *new* (v3) ``_strip_name_markers``, so the "before" count asks which of
  ticket 10's spellings v3 would have joined;
- the causes of ``person-name@v2``'s rejections, each counted, so ticket 27's
  breakdown is reproducible.

Offline: reads local files only.

  uv run python 26-measure.py --before W10/rows.jsonl --after W26/rows.jsonl --out 26-measure.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from edgar_warehouse.domain.policy import person_name
from edgar_warehouse.parsers.proxy_fundamentals import _strip_name_markers

HERE = Path(__file__).resolve().parent
FLATTENED_DIGIT = re.compile(r"[A-Za-z.]\d{1,2}(?:\s|$)|\s\d{1,2}\s*$")
CREDENTIAL = re.compile(r"\b(?:M\.D\.|Ph\.D\.|J\.D\.|M\.B\.|C\.P\.A\.|CPA|Esq)")
HONORIFIC_ONLY = re.compile(r"^(?:Mr|Mrs|Ms|Dr)\.?\s+\S+$")


def _research_01():
    """Research 01's plausibility check, as 10-reparse-bronze.py's score stage uses it."""
    import importlib.util
    import os

    os.environ["R17_ALLOW_NET"] = "1"  # 17-common blocks sockets at import; this is offline
    spec = importlib.util.spec_from_file_location("c17", HERE / "17-common.py")
    c17 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c17)
    return lambda n: bool(n) and not c17.looks_like_role_text(n) and len(c17.norm_name(n).split()) >= 2


def rejection_cause(name: str, r01_plausible) -> str:
    """First matching cause, in this order, so the causes partition the rejections."""
    if not r01_plausible(name):
        return "role text (research 01 rejects too)"
    if HONORIFIC_ONLY.match(name):
        return "honorific and surname only"
    if CREDENTIAL.search(name):
        return "degree or credential suffix"
    if re.search("[\u2018\u2019]", name):
        return "curly apostrophe"
    if re.search(r"[^\x00-\x7f]", name):
        return "accented or other non-ASCII letter"
    return "other"


def collapsed_names(path: Path) -> list[tuple]:
    """(cik, accession, fiscal_year, exec_name), latest per key — the dbt collapse."""
    rows: dict[tuple, dict] = {}
    with open(path) as stream:
        for line in stream:
            for row in json.loads(line).get("rows", []):
                key = (row.get("cik"), row.get("accession_number"), row.get("fiscal_year"), row.get("exec_name"))
                rows[key] = row
    return list(rows)


def measure(path: Path, r01_plausible) -> dict:
    keys = collapsed_names(path)
    names = [str(k[3] or "") for k in keys]
    accepted = sum(1 for n in names if person_name.is_person_name_candidate(n))
    digits = Counter(n for n in names if re.search(r"\d", n))
    # One executive of one company, spelled differently in different filings.
    spellings: dict[tuple, set] = defaultdict(set)
    for cik, _, _, name in keys:
        spellings[(cik, _strip_name_markers(str(name or "")))].add(name)
    split = {k: v for k, v in spellings.items() if len(v) > 1}
    return {
        "collapsed_rows": len(names),
        "person_name_v2": {
            "normalizer": person_name.NORMALIZER_VERSION,
            "accepted": accepted,
            "rate": round(accepted / len(names), 5) if names else None,
        },
        "names_with_a_digit": {"rows": sum(digits.values()), "distinct": len(digits), "top": digits.most_common(15)},
        "executives_spelled_several_ways_by_a_marker": {
            "executives": len(split),
            "extra_spellings": sum(len(v) - 1 for v in split.values()),
            "involving_a_flattened_digit": sum(
                1 for v in split.values() if any(FLATTENED_DIGIT.search(n) for n in v)
            ),
            "examples": [sorted(v) for v in list(split.values())[:8]],
        },
        "person_name_v2_rejections_by_cause": dict(
            Counter(
                rejection_cause(n, r01_plausible)
                for n in names
                if not person_name.is_person_name_candidate(n)
            ).most_common()
        ),
        "person_name_v2_rejected_top": Counter(
            n for n in names if not person_name.is_person_name_candidate(n)
        ).most_common(40),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    r01 = _research_01()
    out = {
        "before_ticket_10_parser_v2": measure(Path(args.before), r01),
        "after_ticket_26_parser_v3": measure(Path(args.after), r01),
    }
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for tag, m in out.items():
        print(tag, json.dumps({k: v for k, v in m.items() if k != "person_name_v2_rejected_top"}, ensure_ascii=False)[:900])


if __name__ == "__main__":
    main()
