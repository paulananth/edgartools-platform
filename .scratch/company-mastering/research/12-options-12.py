"""Ticket 12: does a hold-back on the forms a filer files stop every Fund found so far?

Rules .10 and .11 each let Funds through at step 8. Every one shows in its
forms, not in its code or ticker:
- Sterling Real Estate Trust, Terra Property Trust and InPoint Commercial
  Real Estate Income, GPB Automotive Portfolio: Form 10 plus Form D, no BDC
  election;
- Ellington Credit Co: a registered fund's reports (N-CSR, N-CEN, N-PORT).

This runs the engine's rule .11 over all 76,230 filers and counts what one
forms step before step 8 would move to the Stage. An `operating` filer
waits when either:
- F1: it registered by Form 10 (10-12G) and offers by Form D, with no BDC
  election (N-54A);
- F2: it files a registered fund's reports (N-CSR, N-CEN or NPORT-P).
Forms come from the bronze summary. Zero SEC requests; development data only.

    uv run python .scratch/company-mastering/research/12-options-12.py \\
        <summary.jsonl> <company_tickers_exchange.json>
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("m", HERE / "12-measure-11.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
classify = m.classify
KNOWN_FUNDS = {
    "0001412502": "Sterling Real Estate Trust",
    "0001674356": "Terra Property Trust",
    "0001690012": "InPoint Commercial Real Estate Income",
    "0001578742": "GPB Automotive Portfolio",
    "0001560672": "Ellington Credit Co",
}
FORM_10 = {"10-12G", "10-12G/A"}
FUND_REPORTS = {"N-CSR", "N-CSRS", "N-CEN", "NPORT-P"}


def main(summary: Path, tickers: Path) -> None:
    listed = m.catalog(tickers)
    rule, block = classify.rule()
    everyone = classify.population(summary)
    companies, moved = 0, {"F1": [], "F2": []}
    for r in everyone:
        t = listed.get(r["cik"], [])
        verdict, step = classify.fired(rule, {**classify.row(r), "tickers": t}, block)
        if verdict != "company":
            continue
        companies += 1
        forms = set(r["forms"])
        if r.get("entityType") != "operating":
            continue
        if forms & FORM_10 and forms & {"D", "D/A"} and "N-54A" not in forms:
            moved["F1"].append(r)
        elif forms & FUND_REPORTS:
            moved["F2"].append(r)
    both = moved["F1"] + moved["F2"]
    ciks = {r["cik"] for r in both}
    n = len(everyone)
    print(
        json.dumps(
            {
                "companies_under_11": companies,
                "moved_to_stage": {k: len(v) for k, v in moved.items()},
                "companies_after": companies - len(both),
                "stage_pct": round(100 * (n - companies + len(both)) / n, 2),
                "holds": sorted(KNOWN_FUNDS[c] for c in KNOWN_FUNDS if c in ciks),
                "misses": sorted(KNOWN_FUNDS[c] for c in KNOWN_FUNDS if c not in ciks),
                "F1_names": sorted(r["name"] for r in moved["F1"]),
                "F2_names": sorted(r["name"] for r in moved["F2"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
