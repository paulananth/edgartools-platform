"""Ticket 12: do SEC's ticker catalog and each filer's own record agree on tickers?

Rule .10 (option 1) holds back a filer with no ticker and an Emerging growth
company category. The option was measured with the tickers in each filer's
bronze `submissions.json`, which the landing row drops. The contract can read
the ticker catalog instead (`company_tickers_exchange.json`, landed as
`sec_company_ticker`). This compares the two over all filers in the summary,
and re-runs option 1 with the catalog's tickers. Zero SEC requests: both
files come from bronze.

    uv run python .scratch/company-mastering/research/12-ticker-sources.py \
        <summary.jsonl> <company_tickers_exchange.json>
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("options", HERE / "12-options-10.py")
options = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(options)
classify = options.classify


def catalog(path: Path) -> dict[str, list[str]]:
    doc = json.loads(path.read_text())
    at = {name: i for i, name in enumerate(doc["fields"])}
    out: dict[str, list[str]] = {}
    for row in doc["data"]:
        if row[at["cik"]] is None or not row[at["ticker"]]:
            continue
        out.setdefault(f"{int(row[at['cik']]):010d}", []).append(row[at["ticker"]])
    return out


def main(summary: Path, tickers: Path) -> None:
    options.primitives._tokens_found = options._tokens_found_fixed
    listed = catalog(tickers)
    everyone = classify.population(summary)
    own = {r["cik"] for r in everyone if r.get("tickers")}
    cat = {r["cik"] for r in everyone if r["cik"] in listed}
    base, block = classify.rule()
    rule = options.variant(base, [options.NO_TICKER, options.EGC])

    def run(ticker_of):
        companies, verdicts = set(), Counter()
        for r in everyone:
            verdict, step = classify.fired(
                rule, {**classify.row(r), "ticker": ticker_of(r)}, block
            )
            verdicts[f"{verdict}/{step}"] += 1
            if verdict == "company":
                companies.add(r["cik"])
        return companies, verdicts

    by_own, _ = run(lambda r: (r.get("tickers") or [None])[0])
    by_cat, verdicts = run(lambda r: (listed.get(r["cik"]) or [None])[0])
    n = len(everyone)
    names = {r["cik"]: r["name"] for r in everyone}
    print(
        json.dumps(
            {
                "filers": n,
                "catalog_ciks": len(listed),
                "catalog_ciks_not_in_summary": len(set(listed) - {r["cik"] for r in everyone}),
                "ticker_in_own_record": len(own),
                "ticker_in_catalog": len(cat),
                "both": len(own & cat),
                "own_record_only": len(own - cat),
                "catalog_only": len(cat - own),
                "option_1_companies_own_record": len(by_own),
                "option_1_companies_catalog": len(by_cat),
                "option_1_stage_pct_catalog": round(100 * (n - len(by_cat)) / n, 2),
                "company_by_own_record_only": len(by_own - by_cat),
                "company_by_catalog_only": len(by_cat - by_own),
                "examples_company_by_own_record_only": sorted(
                    names[c] for c in by_own - by_cat
                )[:25],
                "examples_company_by_catalog_only": sorted(
                    names[c] for c in by_cat - by_own
                )[:25],
                "verdicts_catalog": dict(sorted(verdicts.items())),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
