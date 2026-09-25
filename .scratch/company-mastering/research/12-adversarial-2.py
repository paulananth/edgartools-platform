"""A second, fresh adversarial arm for rule 2026-09-24.8 (company mastering ticket 12).

The first fixture (`12-adversarial.jsonl`) was fixed before version .8, and .8
was written to remove the 33 violations .7 had there, so its 0 is in-sample
(three-axis review, 2026-09-24). This arm is drawn after .8 on a fresh seed,
and every arm is chosen by evidence the deciding step does not read:

- step 2 reads only `entityType`, so its arms are chosen by industry code;
- step 4 reads whether an industry code and a category exist and a legal-form
  word, so its arms are chosen by the code's value and the forms filed.

Only records the rule calls Company are drawn: nothing else can be a violation.
Labels are hand-read (`12-label-adversarial-2.py`).

    uv run python .scratch/company-mastering/research/12-adversarial-2.py \\
        draw <summary.jsonl> <out-dir>
    uv run python .scratch/company-mastering/research/12-adversarial-2.py \\
        score <out-dir>
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("classify", HERE / "12-classify.py")
classify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classify)  # also blocks sockets

SEED = "20260924.8-adversarial-2"
PER_ARM = 100
# Industry codes of offices that hold or manage money, not operate a business.
FINANCE_OFFICE_SIC = {"6199", "6211", "6282", "6799"}
ANNUAL = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
NOT_A_COMPANY = {"fund", "person", "government", "loan trust", "other"}


def arms(everyone: list[dict]) -> dict[str, list[dict]]:
    candidate, block = classify.rule()
    found: dict[str, list[dict]] = {
        "operating with a finance-office industry code": [],
        "operating with no industry code": [],
        "step 4 with no annual report": [],
        "step 4 with a finance-office industry code": [],
    }
    for r in everyone:
        verdict, step = classify.fired(candidate, classify.row(r), block)
        if verdict != "company":
            continue
        sic, forms = r.get("sic") or None, set(r.get("forms") or {})
        if step == "2" and sic in FINANCE_OFFICE_SIC:
            found["operating with a finance-office industry code"].append(r)
        if step == "2" and sic is None:
            found["operating with no industry code"].append(r)
        if step == "4" and not forms & ANNUAL:
            found["step 4 with no annual report"].append(r)
        if step == "4" and sic in FINANCE_OFFICE_SIC:
            found["step 4 with a finance-office industry code"].append(r)
    return found


def draw(summary: Path, out: Path) -> None:
    everyone = classify.population(summary)
    candidate, block = classify.rule()
    rng = random.Random(SEED)
    chosen: dict[str, dict] = {}
    sizes = {}
    for arm, records in arms(everyone).items():
        records = sorted(records, key=lambda r: r["cik"])
        picked = records if len(records) <= PER_ARM else rng.sample(records, PER_ARM)
        sizes[arm] = {"population": len(records), "drawn": len(picked)}
        for r in picked:
            chosen.setdefault(r["cik"], {"record": r, "arms": []})["arms"].append(arm)
    with (out / "12-adversarial-2.jsonl").open("w") as f:
        for cik in sorted(chosen):
            r, arm_names = chosen[cik]["record"], chosen[cik]["arms"]
            _, step = classify.fired(candidate, classify.row(r), block)
            f.write(
                json.dumps(
                    {
                        "cik": cik,
                        "name": r["name"],
                        "step": step,
                        "arms": sorted(arm_names),
                        "entity_type": r.get("entityType"),
                        "sic": r.get("sic") or None,
                        "category": r.get("category") or None,
                        "forms": sorted(r["forms"]),
                        "tickers": r.get("tickers"),
                        "exchanges": r.get("exchanges"),
                        "final": None,
                        "note": None,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    (out / "12-adversarial-2-arms.json").write_text(
        json.dumps({"seed": SEED, "arms": sizes}, indent=2, sort_keys=True) + "\n"
    )


def score(out: Path) -> None:
    rows = [json.loads(line) for line in (out / "12-adversarial-2.jsonl").open()]
    unlabelled = [r["cik"] for r in rows if r["final"] is None]
    if unlabelled:
        raise SystemExit(f"{len(unlabelled)} records have no hand-read label")
    violations = [r for r in rows if r["final"] in NOT_A_COMPANY]
    by_step: dict[str, dict] = {}
    for r in rows:
        s = by_step.setdefault(r["step"], {"n": 0, "violations": 0})
        s["n"] += 1
        s["violations"] += r["final"] in NOT_A_COMPANY
    print(
        json.dumps(
            {
                "n": len(rows),
                "violations": len(violations),
                "by_step": by_step,
                "fixture_sha256": classify.sha256(out / "12-adversarial-2.jsonl"),
                "violating": [(r["cik"], r["name"], r["final"]) for r in violations],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "draw":
        draw(Path(args[0]), Path(args[1]))
    elif command == "score":
        score(Path(args[0]))
    else:
        raise SystemExit(f"unknown command {command}")
