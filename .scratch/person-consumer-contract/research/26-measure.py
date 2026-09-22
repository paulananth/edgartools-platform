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
  the spellings differ only by a marker ("Daniel Pinto7" / "Daniel Pinto8" /
  "Daniel Pinto11", one per year).

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


def collapsed_names(path: Path) -> list[tuple]:
    """(cik, accession, fiscal_year, exec_name), latest per key — the dbt collapse."""
    rows: dict[tuple, dict] = {}
    for line in open(path):
        for row in json.loads(line).get("rows", []):
            key = (row.get("cik"), row.get("accession_number"), row.get("fiscal_year"), row.get("exec_name"))
            rows[key] = row
    return list(rows)


def measure(path: Path) -> dict:
    keys = collapsed_names(path)
    names = [str(k[3] or "") for k in keys]
    accepted = sum(1 for n in names if person_name.is_person_name_candidate(n))
    digits = Counter(n for n in names if re.search(r"\d", n))
    # One executive of one company, spelled differently in different filings.
    spellings: dict[tuple, set] = defaultdict(set)
    for cik, _accession, _year, name in keys:
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
            "examples": [sorted(v) for v in list(split.values())[:8]],
        },
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
    out = {"before_ticket_10_parser_v2": measure(Path(args.before)), "after_ticket_26_parser_v3": measure(Path(args.after))}
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for tag, m in out.items():
        print(tag, json.dumps({k: v for k, v in m.items() if k != "person_name_v2_rejected_top"}, ensure_ascii=False)[:900])


if __name__ == "__main__":
    main()
