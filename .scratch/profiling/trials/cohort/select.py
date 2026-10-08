"""Profiling ticket 08: the recreation proof's cohort, 500 fixed entities.

Plan decision 29: one coherent cohort of 500 fixed entities and 2 years,
its list in the repo, all copies local. The operator (2026-10-07: "Local
feeds only (Recommended)"): the cohort is fixed from the feeds on this
machine, SEC submissions (every filer) and the GLEIF Golden Copy of
2026-09-11; the proof covers those and the 13F tables on hand, and DIFF.md
lists every other feed as not covered.

The window is the 2 years before the SEC captures (2024-07-01 to
2026-06-30): an entity is in scope when it filed in it (its latest filing
is on or after its start). Each
stratum is drawn in a fixed order, the sha256 of a seed and the CIK, so the
list is the same on every run. Inputs, read only:

- `summary.jsonl`: each SEC filer's type, name and latest filing date;
- `cm08-coverage.jsonl`: each operating company's SEC-to-GLEIF outcome
  (company mastering ticket 08), and its GLEIF LEI where one was named.

    uv run python .scratch/profiling/trials/cohort/select.py
"""

from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

RESEARCH = Path.home() / ".local/share/edgartools/clean-mdm/research/rebuilt-2026-09-28"
CAPTURE = Path.home() / ".local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230"
OUT = Path(__file__).parent
SEED = "profiling-08-cohort-v1"
WINDOW = ("2024-07-01", "2026-06-30")
# The named examples every trial in this program follows.
NAMED = {"0000320193": "Apple", "0000789019": "Microsoft", "0001306965": "Shell", "0000937966": "ASML"}
# How many of each stratum, and why it is there (500 in all, named included).
STRATA = {
    "company_bound_to_gleif": (171, "an operating company a name rule binds to its GLEIF record"),
    "company_deferred": (75, "an operating company a name rule holds for a steward, each reason represented"),
    "company_no_gleif": (75, "an operating company with no GLEIF record of its name"),
    "investment": (75, "an investment company"),
    "other_filer": (100, "any other filer: people and other entities"),
}


def order(cik: str) -> str:
    return hashlib.sha256(f"{SEED}:{cik}".encode()).hexdigest()


def main() -> None:
    filers = {}
    for line in (RESEARCH / "summary.jsonl").open():
        row = json.loads(line)
        # Filed in the window: its latest filing is on or after the window's start.
        if (row.get("latest") or "") >= WINDOW[0]:
            filers[row["cik"]] = row
    coverage = {json.loads(line)["cik"]: json.loads(line) for line in (RESEARCH / "cm08-coverage.jsonl").open()}
    keys = {entry["cik"]: entry["key"] for chunk in json.loads((CAPTURE / "manifest.json").read_text())["chunks"]
            for entry in chunk}

    def stratum(cik: str) -> str:
        row, cover = filers[cik], coverage.get(cik)
        if row["entityType"] == "operating" and cover:
            if cover["outcome"].startswith("BIND"):
                return "company_bound_to_gleif"
            if cover["outcome"].startswith("defer"):
                return "company_deferred"
            return "company_no_gleif"
        return {"investment": "investment"}.get(row["entityType"], "other_filer")

    pools = collections.defaultdict(list)
    for cik in sorted(filers, key=order):
        pools[stratum(cik)].append(cik)
    chosen = {cik: "named" for cik in NAMED if cik in filers}
    for name, (size, _why) in STRATA.items():
        pool = [cik for cik in pools[name] if cik not in chosen]
        if name == "company_deferred":
            # Each hold-back reason first, then the rest in the fixed order.
            reasons = {}
            for cik in pool:
                reasons.setdefault(coverage[cik]["outcome"], cik)
            pool = list(reasons.values()) + [cik for cik in pool if cik not in reasons.values()]
        for cik in pool[: size - sum(1 for c, s in chosen.items() if s == name)]:
            chosen[cik] = name
    entities = []
    for cik, name in sorted(chosen.items()):
        row, cover = filers[cik], coverage.get(cik) or {}
        entities.append({
            "cik": cik, "name": row["name"], "entity_type": row["entityType"], "stratum": name,
            "latest_filing": row["latest"], "gleif_outcome": cover.get("outcome"),
            "lei": ((cover.get("gleif") or {}).get("lei") or cover.get("sec_lei")),
            "named": NAMED.get(cik), "submissions_key": keys.get(cik),
        })
    sizes = [(CAPTURE / "bronze" / e["submissions_key"].removeprefix("warehouse/bronze/")).stat().st_size
             for e in entities if e["submissions_key"]]
    cohort = {
        "seed": SEED, "window": {"from": WINDOW[0], "to": WINDOW[1]},
        "inputs": {"sec_filers_in_window": len(filers), "sec_filers_captured": len(keys),
                   "operating_companies_with_gleif_outcome": len(coverage)},
        "strata": {name: {"size": sum(1 for e in entities if e["stratum"] == name), "why": why}
                   for name, (_size, why) in {**STRATA, "named": (0, "the program's named examples")}.items()},
        "count": len(entities),
        "with_lei": sum(1 for e in entities if e["lei"]),
        "submissions_bytes": sum(sizes),
        "entities": entities,
    }
    (OUT / "cohort.json").write_text(json.dumps(cohort, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in cohort.items() if k != "entities"}, indent=1))


if __name__ == "__main__":
    main()
