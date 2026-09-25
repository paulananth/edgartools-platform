"""Proving Run for the Forms hold-back, rule 2026-09-25.12 (ticket 12).

The Forms hold-back is the REIT hold-back (2026-09-25.11) plus two steps
before step 8 that read the forms a filer files (operator, 2026-09-25):
`7a`, an `operating` filer that files a registered fund's reports (N-CSR,
N-CSRS, N-CEN, NPORT-P), waits; `7b`, an `operating` filer with a Form 10
and a Form D and no BDC election (N-54A), waits. It also moves every
`token_match` to version 2, which counts `&` only for a list carrying AND.
Step ids are stable; the Company steps stay 8 and 10. The REIT hold-back's
draws designed it, so every record drawn for any earlier version is left
out of the adversarial arms.

Everything below is drawn after the rule was frozen, on a fresh seed:

- `12-12-sample.jsonl`: 300 records per Company step, simple random;
- `12-12-adversarial.jsonl`: arms chosen by evidence the deciding step does
  not read. Step 8 reads the entity type; the rule before it reads codes,
  the category, tickers, name words and three form sets. So the arms are
  private offerings (Form D), Form 10 registrations, investment or
  real-estate codes, a REIT code with a ticker, no annual report,
  investment-company filings (N-2, 497, 40-APP, N-8A) and no ticker under
  step 8; Form D under step 10;
- `12-12-held.jsonl`: up to 100 records each that steps 7a and 7b hold
  back, read to check their Probable Kinds. They cannot be wrong.

Forms come from the bronze summary (each filer's recent submissions page),
as the contract will read them from `sec_company_filing`. Tickers come from the bronze catalog (`company_tickers_exchange.json`), the
evidence the contract reads, not the filer's own `submissions.json`. Labels
are hand-read (`12-12-label.py`). Zero SEC requests.

    uv run python .scratch/company-mastering/research/12-measure-12.py \\
        draw <summary.jsonl> <company_tickers_exchange.json> <out-dir>
    uv run python .scratch/company-mastering/research/12-measure-12.py \\
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

VERSION = "2026-09-25.12"
SEED = "20260925.12"
SAMPLE_SIZE = 300
PER_ARM = 100
HELD_SIZE = 100
CONFIDENCE = 0.95
HOLD_BACK_STEPS = ("7a", "7b")
# Every record drawn for an earlier version designed this one.
EARLIER = (
    "12-sample.jsonl",
    "12-adversarial.jsonl",
    "12-adversarial-2.jsonl",
    "12-9-sample.jsonl",
    "12-9-adversarial.jsonl",
    "12-10-sample.jsonl",
    "12-10-adversarial.jsonl",
    "12-10-held.jsonl",
    "12-11-sample.jsonl",
    "12-11-adversarial.jsonl",
    "12-11-held.jsonl",
)
INVESTMENT_COMPANY = {"N-2", "N-2/A", "497", "40-APP", "40-APP/A", "N-8A"}
INVESTMENT_OR_REAL_ESTATE_SIC = {
    "6199",
    "6211",
    "6282",
    "6726",
    "6799",
    "6500",
    "6510",
    "6512",
    "6513",
    "6519",
    "6531",
    "6532",
    "6552",
    "6798",
}
ANNUAL = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
OFFERING = {"D", "D/A"}
FORM_10 = {"10-12G", "10-12G/A", "10-12B", "10-12B/A"}
NOT_A_COMPANY = {"fund", "person", "government", "loan trust", "other"}
NAMES = ("sample", "adversarial", "held")


def catalog(path: Path) -> dict[str, list[str]]:
    """Each CIK's catalog tickers, in the catalog's order."""
    doc = json.loads(path.read_text())
    at = {name: i for i, name in enumerate(doc["fields"])}
    out: dict[str, list[str]] = {}
    for row in doc["data"]:
        if row[at["cik"]] is None or not row[at["ticker"]]:
            continue
        out.setdefault(f"{int(row[at['cik']]):010d}", []).append(row[at["ticker"]])
    return out


def arm_of(step: str, r: dict, tickers: list[str]) -> list[str]:
    sic, forms = r.get("sic") or None, set(r.get("forms") or {})
    arms = []
    if forms & OFFERING:
        arms.append(f"step {step} with a Form D offering")
    if not tickers:
        arms.append(f"step {step} with no catalog ticker")
    if step == "8":
        if forms & FORM_10:
            arms.append("step 8 with a Form 10 registration")
        if sic in INVESTMENT_OR_REAL_ESTATE_SIC:
            arms.append("step 8 with an investment or real-estate industry code")
        if sic == "6798" and tickers:
            arms.append("step 8 with a REIT code and a catalog ticker")
        if not forms & ANNUAL:
            arms.append("step 8 with no annual report")
        if forms & INVESTMENT_COMPANY:
            arms.append("step 8 with an investment-company filing")
    if step == "10" and not forms & ANNUAL:
        arms.append("step 10 with no annual report")
    return arms


def record(r: dict, step: str, tickers: list[str], arms=None) -> dict:
    out = {
        "cik": r["cik"],
        "name": r["name"],
        "step": step,
        "entity_type": r.get("entityType"),
        "sic": r.get("sic") or None,
        "category": r.get("category") or None,
        "forms": sorted(r["forms"]),
        "catalog_tickers": tickers,
        "own_tickers": r.get("tickers"),
        "exchanges": r.get("exchanges"),
        "final": None,
        "note": None,
    }
    if arms is not None:
        out["arms"] = sorted(arms)
    return out


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in sorted(rows, key=lambda r: r["cik"]):
            f.write(json.dumps(r, sort_keys=True) + "\n")


def earlier_ciks(out: Path) -> set[str]:
    seen = set()
    for name in EARLIER:
        for line in (out / name).open():
            seen.add(json.loads(line)["cik"])
    return seen


def draw(summary: Path, tickers_path: Path, out: Path) -> None:
    candidate, block = classify.rule()
    if candidate["version"] != VERSION:
        raise SystemExit(f"policy holds {candidate['version']}, not {VERSION}")
    listed = catalog(tickers_path)
    everyone = classify.population(summary)
    verdicts: Counter = Counter()
    by_step: dict[str, list[dict]] = {}
    held: dict[str, list[dict]] = {s: [] for s in HOLD_BACK_STEPS}
    for r in everyone:
        row = {
            **classify.row(r),
            "tickers": listed.get(r["cik"], []),
            "forms": sorted(r["forms"]),
        }
        verdict, step = classify.fired(candidate, row, block)
        verdicts[f"{verdict}/{step}"] += 1
        if verdict == "company":
            by_step.setdefault(step, []).append(r)
        elif step in held:
            held[step].append(r)
    steps = sorted(by_step, key=int)
    sample = []
    for step in steps:
        population = sorted(by_step[step], key=lambda r: r["cik"])
        drawn = random.Random(f"{SEED}-step-{step}").sample(population, SAMPLE_SIZE)
        sample += [record(r, step, listed.get(r["cik"], [])) for r in drawn]
    write(out / "12-12-sample.jsonl", sample)
    arms: dict[str, list[tuple[str, dict]]] = {}
    seen = earlier_ciks(out)
    for step in steps:
        for r in by_step[step]:
            if r["cik"] in seen:
                continue
            for arm in arm_of(step, r, listed.get(r["cik"], [])):
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
    write(
        out / "12-12-adversarial.jsonl",
        [
            record(c["r"], c["step"], listed.get(c["r"]["cik"], []), c["arms"])
            for c in chosen.values()
        ],
    )
    held_rows, held_sizes = [], {}
    for step, rows in held.items():
        rows = sorted(rows, key=lambda r: r["cik"])
        drawn = random.Random(f"{SEED}-held-{step}").sample(
            rows, min(HELD_SIZE, len(rows))
        )
        held_sizes[step] = {"population": len(rows), "drawn": len(drawn)}
        held_rows += [record(r, step, listed.get(r["cik"], [])) for r in drawn]
    write(out / "12-12-held.jsonl", held_rows)
    (out / "12-12-population.json").write_text(
        json.dumps(
            {
                "rule": {"rule_id": candidate["rule_id"], "version": VERSION},
                "seed": SEED,
                "records": len(everyone),
                "summary_sha256": classify.sha256(summary),
                "ticker_catalog_sha256": classify.sha256(tickers_path),
                "verdicts": dict(sorted(verdicts.items())),
                "sample_size_per_step": SAMPLE_SIZE,
                "adversarial_arms": sizes,
                "held_back": held_sizes,
                "excluded_earlier_draws": len(seen),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def load(out: Path, name: str) -> list[dict]:
    return [json.loads(line) for line in (out / f"12-12-{name}.jsonl").open()]


def score(out: Path) -> None:
    sample, adversarial, held = (load(out, n) for n in NAMES)
    missing = [r["cik"] for r in sample + adversarial + held if r["final"] is None]
    if missing:
        raise SystemExit(f"{len(missing)} records have no hand-read label")
    by_step = {}
    for step in sorted({r["step"] for r in sample}, key=int):
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
            *(f"12-12-{n}.jsonl" for n in NAMES),
            "12-12-population.json",
            "12-classify.py",
            "12-measure-12.py",
            "12-12-label.py",
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
        "held_back": {
            step: dict(Counter(r["final"] for r in held if r["step"] == step))
            for step in HOLD_BACK_STEPS
        },
        "files": files,
    }
    (out / "12-12-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "draw":
        draw(Path(args[0]), Path(args[1]), Path(args[2]))
    elif command == "score":
        score(Path(args[0]))
    else:
        raise SystemExit(f"unknown command {command}")
