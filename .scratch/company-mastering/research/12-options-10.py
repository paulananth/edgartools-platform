"""Ticket 12: how many SEC filers stay in the Stage under each way forward.

Runs the engine's own `fired` over all 76,230 filers in the bronze summary for
three rule documents built from version .9:

- `.9 (& fixed)`: .9 with the ampersand defect repaired (an ampersand counts
  only for a word list carrying AND);
- `option 1`: that, plus a step after step 1: no ticker and "Emerging growth
  company" in the filer category -> the record waits;
- `option 2`: that, plus a step after step 1: no ticker -> the record waits.

The ticker is simulated from the summary's `tickers` (the landing row does not
carry it yet). Zero SEC requests; no hand labels, so this measures how many
wait, not precision.

    uv run python .scratch/company-mastering/research/12-options-10.py <summary.jsonl>
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

from edgar_warehouse.mdm.clean import primitives

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("classify", HERE / "12-classify.py")
classify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classify)

_original = primitives._tokens_found


def _tokens_found_fixed(raw, listed, normalize):
    found = _original(raw, listed, normalize)
    if "&" in found and "AND" not in listed:
        found = [t for t in found if t != "&"]
    return found


NO_TICKER = {"primitive": "fields_all_empty@1", "args": {"fields": ["ticker"]}}
EGC = {
    "primitive": "token_match@1",
    "args": {
        "field": "category",
        "normalizer": "conformed",
        "token_list": ["EMERGING GROWTH COMPANY"],
        "min_count": 1,
    },
}


def variant(rule: dict, when: list | None) -> dict:
    rule = copy.deepcopy(rule)
    if when:
        rule["steps"].insert(1, {"step": "1b", "verdict": "deferred", "when": when})
    return rule


def row(r: dict) -> dict:
    tickers = r.get("tickers") or []
    return {**classify.row(r), "ticker": tickers[0] if tickers else None}


def main(summary: Path) -> None:
    primitives._tokens_found = _tokens_found_fixed
    base, block = classify.rule()
    everyone = classify.population(summary)
    rules = {
        ".9 (& fixed)": variant(base, None),
        "option 1": variant(base, [NO_TICKER, EGC]),
        "option 2": variant(base, [NO_TICKER]),
    }
    out = {}
    for name, rule in rules.items():
        verdicts, by_type, stage_types = Counter(), Counter(), Counter()
        companies = set()
        for r in everyone:
            verdict, step = classify.fired(rule, row(r), block)
            verdicts[f"{verdict}/{step}"] += 1
            by_type[r.get("entityType")] += 1
            if verdict == "company":
                companies.add(r["cik"])
            else:
                stage_types[r.get("entityType")] += 1
        n = len(everyone)
        out[name] = {
            "companies": len(companies),
            "stage": n - len(companies),
            "stage_pct": round(100 * (n - len(companies)) / n, 2),
            "stage_pct_by_type": {
                t: round(100 * stage_types[t] / by_type[t], 1) for t in sorted(by_type)
            },
            "verdicts": dict(sorted(verdicts.items())),
            "_ciks": companies,
        }
    ref = out[".9 (& fixed)"]["_ciks"]
    for name in ("option 1", "option 2"):
        moved = ref - out[name]["_ciks"]
        out[name]["moved_to_stage_vs_.9"] = len(moved)
        out[name]["moved_examples"] = sorted(
            r["name"] for r in everyone if r["cik"] in moved
        )[:40]
    for v in out.values():
        del v["_ciks"]
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
