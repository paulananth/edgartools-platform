"""Ticket 08: the SEC Company population the matching rule works on.

Runs the active Account hold-back (rule `sec-company-candidate`
2026-09-25.13) over the frozen bronze summary exactly as ticket 12 measured
it, and writes one line per Company verdict with the SEC evidence a
SEC-to-GLEIF matching rule can compare (name, former names, SEC's own LEI,
addresses, state of incorporation, tickers), joined from the step-1 bronze
scan. Zero SEC requests; sockets are blocked by `12-classify.py`.

    uv run python .scratch/company-mastering/research/08-companies.py \\
        <summary.jsonl> <company_tickers_exchange.json> <sec-scan.jsonl> <out.jsonl>
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("measure", HERE / "12-measure-13.py")
measure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(measure)
classify = measure.classify


def companies(summary: Path, tickers_path: Path) -> list[dict]:
    candidate, block = classify.rule()
    if candidate["version"] != measure.VERSION:
        raise SystemExit(f"policy holds {candidate['version']}, not {measure.VERSION}")
    listed = measure.catalog(tickers_path)
    out = []
    for r in classify.population(summary):
        row = {
            **classify.row(r),
            "tickers": listed.get(r["cik"], []),
            "forms": sorted(r["forms"]),
        }
        verdict, step = classify.fired(candidate, row, block)
        if verdict == "company":
            out.append({"cik": r["cik"], "step": step, "tickers": row["tickers"]})
    return out


def main(summary: Path, tickers_path: Path, scan: Path, out: Path) -> None:
    rows = {r["cik"]: r for r in companies(summary, tickers_path)}
    found = 0
    with out.open("w") as f:
        for line in scan.open():
            s = json.loads(line)
            if s.get("cik") is None:
                continue
            cik = f"{int(s['cik']):010d}"
            if cik not in rows:
                continue
            found += 1
            rows[cik].update(
                {
                    "name": s.get("name"),
                    "former_names": [n.get("name") for n in s.get("formerNames") or []],
                    "sec_lei": s.get("lei"),
                    "entity_type": s.get("entityType"),
                    "state_of_incorporation": s.get("stateOfIncorporation"),
                    "addresses": s.get("addresses"),
                }
            )
        for cik in sorted(rows):
            f.write(json.dumps(rows[cik], sort_keys=True) + "\n")
    steps = Counter(r["step"] for r in rows.values())
    print(
        json.dumps(
            {
                "companies": len(rows),
                "by_step": dict(sorted(steps.items())),
                "joined_to_scan": found,
                "out_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main(*(Path(a) for a in sys.argv[1:5]))
