"""Ticket 12: what two ways past rule .10's violations would hold back.

Rule .10 let through two private REITs registered by Form 10 (Sterling Real
Estate Trust, Terra Property Trust). This runs the engine's rule .10 over all
76,230 filers, then counts, for each option, the Companies it would move to
the Stage and whether it holds the two violators:

- A (narrow): an `operating` REIT code (6798) with no catalog ticker waits,
  and step 6's finance-office codes gain 6798;
- B (forms): an `operating` filer that registered by Form 10 and offers by
  Form D, with no BDC election (N-54A) and no catalog ticker, waits. It needs
  the forms a filer files, which the contract does not read today.

Forms come from the bronze summary. The .10 draws designed both options, so
they are development data: a chosen option needs fresh draws. Zero SEC
requests.

    uv run python .scratch/company-mastering/research/12-options-11.py \\
        <summary.jsonl> <company_tickers_exchange.json>
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("m", HERE / "12-measure-10.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
classify = m.classify
VIOLATORS = {"0001412502", "0001674356"}
FORM_10 = {"10-12G", "10-12G/A"}


def main(summary: Path, tickers: Path) -> None:
    listed = m.catalog(tickers)
    rule, block = classify.rule()
    everyone = classify.population(summary)
    moved = {"A": [], "B": []}
    companies = 0
    for r in everyone:
        t = listed.get(r["cik"], [])
        verdict, step = classify.fired(rule, {**classify.row(r), "tickers": t}, block)
        if verdict != "company":
            continue
        companies += 1
        forms, sic = set(r["forms"]), r.get("sic")
        op = r.get("entityType") == "operating"
        egc_only = (r.get("category") or "") == "<br>Emerging growth company"
        if op and sic == "6798" and (not t or egc_only):
            moved["A"].append(r)
        if (
            op
            and forms & FORM_10
            and forms & {"D", "D/A"}
            and "N-54A" not in forms
            and not t
        ):
            moved["B"].append(r)
    n = len(everyone)
    out = {"filers": n, "companies_under_10": companies}
    for k, rows in moved.items():
        ciks = {r["cik"] for r in rows}
        out[k] = {
            "moved_to_stage": len(rows),
            "companies_after": companies - len(rows),
            "stage_pct": round(100 * (n - companies + len(rows)) / n, 2),
            "holds_violators": sorted(VIOLATORS & ciks),
            "misses_violators": sorted(VIOLATORS - ciks),
            "names": sorted(r["name"] for r in rows)[:60],
        }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
