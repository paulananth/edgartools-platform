"""Proving Run for rule 2026-09-25.9 (company mastering ticket 12).

Version .9 adds three steps that hold back `operating` filers before step 5
calls the rest Companies: a fund word in the name (step 2), a finance-office
industry code with no filer status (step 3), and no industry code (step 4).
They were written from `12-adversarial-2.jsonl`, which is therefore
development data for .9 and measures nothing here.

Everything below is drawn after .9 was frozen, on fresh seeds:

- `12-9-sample.jsonl`: 300 records per Company step (5 and 7), simple random;
- `12-9-adversarial.jsonl`: arms chosen by evidence the deciding step does not
  read (step 5 reads only `entityType`; step 7 reads that a code and a
  category exist and a legal-form word).

Only records the rule calls Company are drawn: nothing else can be wrong.
Labels are hand-read (`12-9-label.py`). Zero SEC requests.

    uv run python .scratch/company-mastering/research/12-measure-9.py \\
        draw <summary.jsonl> <out-dir>
    uv run python .scratch/company-mastering/research/12-measure-9.py \\
        score <out-dir>
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("classify", HERE / "12-classify.py")
classify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classify)  # also blocks sockets

VERSION = "2026-09-25.9"
SEED = "20260925.9"
SAMPLE_SIZE = 300
PER_ARM = 100
CONFIDENCE = 0.95
FINANCE_OFFICE_SIC = {"6199", "6211", "6282", "6799"}
ANNUAL = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
NOT_A_COMPANY = {"fund", "person", "government", "loan trust", "other"}


def arm_of(step: str, r: dict) -> list[str]:
    sic, forms = r.get("sic") or None, set(r.get("forms") or {})
    category = r.get("category") or ""
    arms = []
    if step == "5":
        if sic in FINANCE_OFFICE_SIC:
            arms.append("step 5 with a finance-office industry code")
        if "accelerated filer" not in category.lower():
            arms.append("step 5 with no accelerated or non-accelerated status")
        if not forms & ANNUAL:
            arms.append("step 5 with no annual report")
    if step == "7":
        if not forms & ANNUAL:
            arms.append("step 7 with no annual report")
        if sic in FINANCE_OFFICE_SIC:
            arms.append("step 7 with a finance-office industry code")
    return arms


def record(r: dict, step: str, arms: list[str] | None = None) -> dict:
    out = {
        "cik": r["cik"],
        "name": r["name"],
        "step": step,
        "entity_type": r.get("entityType"),
        "sic": r.get("sic") or None,
        "category": r.get("category") or None,
        "forms": sorted(r["forms"]),
        "tickers": r.get("tickers"),
        "exchanges": r.get("exchanges"),
        "final": None,
        "note": None,
    }
    if arms is not None:
        out["arms"] = sorted(arms)
    return out


def draw(summary: Path, out: Path) -> None:
    candidate, block = classify.rule()
    if candidate["version"] != VERSION:
        raise SystemExit(f"policy holds {candidate['version']}, not {VERSION}")
    everyone = classify.population(summary)
    verdicts: Counter = Counter()
    by_step: dict[str, list[dict]] = {}
    for r in everyone:
        verdict, step = classify.fired(candidate, classify.row(r), block)
        verdicts[f"{verdict}/{step}"] += 1
        if verdict == "company":
            by_step.setdefault(step, []).append(r)
    steps = sorted(by_step)
    sample = []
    for step in steps:
        population = sorted(by_step[step], key=lambda r: r["cik"])
        drawn = random.Random(f"{SEED}-step-{step}").sample(population, SAMPLE_SIZE)
        sample += [record(r, step) for r in drawn]
    with (out / "12-9-sample.jsonl").open("w") as f:
        for r in sorted(sample, key=lambda r: r["cik"]):
            f.write(json.dumps(r, sort_keys=True) + "\n")
    arms: dict[str, list[tuple[str, dict]]] = {}
    for step in steps:
        for r in by_step[step]:
            for arm in arm_of(step, r):
                arms.setdefault(arm, []).append((step, r))
    rng = random.Random(f"{SEED}-adversarial")
    chosen: dict[str, dict] = {}
    sizes = {}
    for arm in sorted(arms):
        members = sorted(arms[arm], key=lambda t: t[1]["cik"])
        picked = members if len(members) <= PER_ARM else rng.sample(members, PER_ARM)
        sizes[arm] = {"population": len(members), "drawn": len(picked)}
        for step, r in picked:
            entry = chosen.setdefault(r["cik"], {"step": step, "r": r, "arms": []})
            entry["arms"].append(arm)
    with (out / "12-9-adversarial.jsonl").open("w") as f:
        for cik in sorted(chosen):
            c = chosen[cik]
            f.write(json.dumps(record(c["r"], c["step"], c["arms"]), sort_keys=True) + "\n")
    (out / "12-9-population.json").write_text(
        json.dumps(
            {
                "rule": {"rule_id": candidate["rule_id"], "version": VERSION},
                "seed": SEED,
                "records": len(everyone),
                "summary_sha256": classify.sha256(summary),
                "verdicts": dict(sorted(verdicts.items())),
                "sample_size_per_step": SAMPLE_SIZE,
                "adversarial_arms": sizes,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def score(out: Path) -> None:
    sample = [json.loads(line) for line in (out / "12-9-sample.jsonl").open()]
    adversarial = [json.loads(line) for line in (out / "12-9-adversarial.jsonl").open()]
    missing = [r["cik"] for r in sample + adversarial if r["final"] is None]
    if missing:
        raise SystemExit(f"{len(missing)} records have no hand-read label")
    by_step = {}
    for step in sorted({r["step"] for r in sample}):
        rows = [r for r in sample if r["step"] == step]
        correct = sum(r["final"] == "company" for r in rows)
        by_step[step] = {
            "n": len(rows),
            "correct": correct,
            "lower_bound": classify.wilson_lower_bound(correct, len(rows), CONFIDENCE),
        }
    n, correct = len(sample), sum(r["final"] == "company" for r in sample)
    violations = [r for r in adversarial if r["final"] in NOT_A_COMPANY]
    files = {
        name: classify.sha256(out / name)
        for name in (
            "12-9-sample.jsonl",
            "12-9-adversarial.jsonl",
            "12-9-population.json",
            "12-classify.py",
            "12-measure-9.py",
            "12-9-label.py",
        )
    }
    summary = {
        "rule_version": VERSION,
        "n": n,
        "correct": correct,
        "lower_bound": classify.wilson_lower_bound(correct, n, CONFIDENCE),
        "by_step": by_step,
        "adversarial": {
            "n": len(adversarial),
            "violations": len(violations),
            "by_step": dict(Counter(r["step"] for r in violations)),
            "violating": [(r["cik"], r["name"], r["final"]) for r in violations],
        },
        "wrong_in_sample": [
            (r["cik"], r["name"], r["step"], r["final"])
            for r in sample
            if r["final"] != "company"
        ],
        "files": files,
    }
    (out / "12-9-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "draw":
        draw(Path(args[0]), Path(args[1]))
    elif command == "score":
        score(Path(args[0]))
    else:
        raise SystemExit(f"unknown command {command}")
