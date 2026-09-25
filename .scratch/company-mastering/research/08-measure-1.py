"""Proving Run for the SEC-to-GLEIF matching rules, version 2026-09-25.1 (ticket 08).

The rules were frozen and committed (`08-rules.json`, commit ac063c10) before
this draw. Every pair below comes from `08-coverage.py` run through the
production code (`clean/names.py`); nothing here re-implements a test.

Left out of every draw: the 1,000 development CIKs whose reviewed pairs
tuned the rule, and the four acceptance Companies (Apple, Microsoft, Shell,
ASML), whose Dutch postal allowance was written after reading ASML.

- `08-1-sample.jsonl`: 300 pairs per rule, simple random, fresh seed;
- `08-1-adversarial.jsonl`: up to 50 pairs per arm, chosen by evidence the
  deciding test does not read, from the pairs either rule binds and the
  samples did not draw. Arms:
  - a foreign filer (SEC entity type `other`);
  - a name of one word before its legal form;
  - GLEIF's headquarters country differs from SEC's business country;
  - GLEIF's legal address is a registered agent's;
  - GLEIF registration LAPSED or RETIRED;
  - a renamed SEC filer (it has former names);
  - postal step with no jurisdiction agreement.

Labels are hand-read (`08-1-label.py`) under `08-labelling-standard.md`.

    python .scratch/company-mastering/research/08-measure-1.py \\
        draw <coverage.jsonl> <gleif-all.jsonl> <out-dir>
    python .scratch/company-mastering/research/08-measure-1.py score <out-dir>
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
DEV = HERE.parent.parent / "gleif-company-augmentation" / "research" / "01-company-cohort-1000.jsonl"
SEED = "20260925.08-1"
SAMPLE_SIZE = 300
PER_ARM = 50
CONFIDENCE = 0.95
RULES = ("sec-gleif-name-jurisdiction", "sec-gleif-name-postal")
FOUR = {"0000320193", "0000789019", "0001306965", "0000937966"}
FORMS = {"INC", "CORP", "CO", "LLC", "LP", "LLP", "LTD", "PLC", "NV", "SA", "AG",
         "SE", "BV", "HLDGS", "HOLDING", "GROUP", "TRUST", "AND"}
AGENT = re.compile(
    r"CORPORATION TRUST|C/O CT CORP|CT CORPORATION|CORPORATION SERVICE COMPANY|"
    r"\bCSC\b|REGISTERED AGENT|NATIONAL REGISTERED AGENTS|INCORP SERVICES|"
    r"UNITED AGENT|COGENCY GLOBAL|MAPLES CORPORATE|WALKERS CORPORATE|"
    r"1209 ORANGE|251 LITTLE FALLS|2711 CENTERVILLE|850 NEW BURTON|UGLAND HOUSE",
    re.IGNORECASE,
)
ELIGIBLE_DEFERS = ("defer: name", "defer: another", "defer: GLEIF")


def fired(r: dict) -> list[str]:
    """The rules that bind this Company, as the frozen rules read it."""
    if "gleif" not in r or r["outcome"] == "no GLEIF record with this name":
        return []
    if r["outcome"].startswith(ELIGIBLE_DEFERS):
        return []
    out = []
    if r["agree"]["jurisdiction"]:
        out.append(RULES[0])
    if r["agree"]["postal"]:
        out.append(RULES[1])
    return out


def view(r: dict, g: dict, rules: list[str], arms: list[str] | None = None) -> dict:
    business = (r.get("addresses") or {}).get("business") or {}
    return {
        "cik": r["cik"],
        "rules": rules,
        "arms": arms or [],
        "sec": {
            "name": r["name"],
            "former_names": r.get("former_names") or [],
            "entity_type": r.get("entity_type"),
            "state_of_incorporation": r.get("state_of_incorporation"),
            "business": {k: business.get(k) for k in
                         ("street1", "city", "stateOrCountry", "countryCode", "zipCode")},
            "tickers": r.get("tickers") or [],
            "classification_step": r["step"],
        },
        "gleif": {
            "lei": g["lei"],
            "legal_name": g["legal_name"],
            "other_names": g["other_names"],
            "legal_form": g["legal_form"],
            "jurisdiction": g["jurisdiction"],
            "entity_status": g["entity_status"],
            "registration_status": g["registration_status"],
            "legal": g["legal"],
            "hq": g["hq"],
        },
    }


def arms_of(r: dict, g: dict, rules: list[str]) -> list[str]:
    arms = []
    if r.get("entity_type") == "other":
        arms.append("foreign filer")
    base = [t for t in r["key"].split() if t not in FORMS]
    if len(base) <= 1:
        arms.append("one-word name")
    business = (r.get("addresses") or {}).get("business") or {}
    hq_country = ((g.get("hq") or {}).get("country") or "").upper()
    sec_place = business.get("stateOrCountry") or business.get("countryCode") or ""
    from edgar_warehouse.mdm.clean.names import edgar_jurisdiction

    sec_country = (edgar_jurisdiction(sec_place) or "").split("-")[0]
    if hq_country and sec_country and hq_country != sec_country:
        arms.append("headquarters country differs")
    legal = " ".join((g.get("legal") or {}).get("lines") or [])
    if AGENT.search(legal):
        arms.append("registered agent legal address")
    if g["registration_status"] in {"LAPSED", "RETIRED"}:
        arms.append("GLEIF lapsed or retired")
    if r.get("former_names"):
        arms.append("renamed SEC filer")
    if rules == [RULES[1]]:
        arms.append("postal step, no jurisdiction agreement")
    return arms


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for row in sorted(rows, key=lambda x: x["cik"]):
            f.write(json.dumps(row, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def draw(coverage: Path, gleif_all: Path, out: Path) -> None:
    with DEV.open() as f:
        dev = {f"{int(json.loads(line)['cik']):010d}" for line in f}
    with coverage.open() as f:
        rows = [json.loads(line) for line in f]
    bound = {}
    for r in rows:
        rules = fired(r)
        if rules and r["cik"] not in dev and r["cik"] not in FOUR:
            bound[r["cik"]] = (r, rules)
    wanted = {r["gleif"]["lei"] for r, _ in bound.values()}
    gleif = {}
    with gleif_all.open() as f:
        for line in f:
            if line[8:28] in wanted:  # '{"lei":"' is 8 characters
                g = json.loads(line)
                gleif[g["lei"]] = g
    # One row per pair; `drawn_for` says which rule's simple random sample
    # drew it, so each rule is scored on its own draw only.
    by_cik: dict[str, dict] = {}
    sizes = {}
    for rule in RULES:
        population = sorted(c for c, (_, rules) in bound.items() if rule in rules)
        picked = random.Random(f"{SEED}-{rule}").sample(population, SAMPLE_SIZE)
        sizes[rule] = {"population": len(population), "drawn": len(picked)}
        for cik in picked:
            if cik not in by_cik:
                r, rules = bound[cik]
                by_cik[cik] = view(r, gleif[r["gleif"]["lei"]], rules)
                by_cik[cik]["drawn_for"] = []
            by_cik[cik]["drawn_for"].append(rule)
    sample, drawn = list(by_cik.values()), set(by_cik)
    by_arm: dict[str, list[str]] = {}
    for cik in sorted(bound):
        if cik in drawn:
            continue
        r, rules = bound[cik]
        for arm in arms_of(r, gleif[r["gleif"]["lei"]], rules):
            by_arm.setdefault(arm, []).append(cik)
    adversarial, taken, arm_sizes = {}, set(), {}
    for arm in sorted(by_arm):
        members = by_arm[arm]
        picked = random.Random(f"{SEED}-arm-{arm}").sample(members, min(PER_ARM, len(members)))
        arm_sizes[arm] = {"population": len(members), "drawn": len(picked)}
        for cik in picked:
            r, rules = bound[cik]
            if cik in adversarial:
                adversarial[cik]["arms"].append(arm)
            else:
                adversarial[cik] = view(r, gleif[r["gleif"]["lei"]], rules, [arm])
            taken.add(cik)
    out.mkdir(parents=True, exist_ok=True)
    write(out / "08-1-sample.jsonl", sample)
    write(out / "08-1-adversarial.jsonl", list(adversarial.values()))
    (out / "08-1-population.json").write_text(
        json.dumps(
            {
                "seed": SEED,
                "coverage_sha256": sha256(coverage),
                "bound_outside_excluded": len(bound),
                "excluded_development_ciks": len(dev),
                "excluded_acceptance_ciks": sorted(FOUR),
                "samples": sizes,
                "adversarial_arms": arm_sizes,
                "sample_pairs": len(sample),
                "adversarial_pairs": len(adversarial),
            },
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )
    print((out / "08-1-population.json").read_text())


def wilson(correct: int, n: int) -> float:
    z = NormalDist().inv_cdf(CONFIDENCE)
    p = correct / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - spread) / (1 + z * z / n)


def score(out: Path) -> None:
    def load(name):
        with (out / name).open() as f:
            return [json.loads(line) for line in f]

    sample, adversarial = load("08-1-sample.jsonl"), load("08-1-adversarial.jsonl")
    if any("final" not in r for r in sample + adversarial):
        raise SystemExit("unlabelled rows remain; run 08-1-label.py first")
    by_rule = {}
    for rule in RULES:
        drawn = [r for r in sample if rule in r["drawn_for"]]
        correct = sum(r["final"] == "same" for r in drawn)
        arms = [r for r in adversarial if rule in r["rules"]]
        by_rule[rule] = {"n": len(drawn), "correct": correct,
                         "lower_bound": round(wilson(correct, len(drawn)), 6),
                         "adversarial": {"n": len(arms),
                                         "violations": sum(r["final"] != "same" for r in arms)}}
    violations = [r for r in adversarial if r["final"] != "same"]
    summary = {
        "by_rule": by_rule,
        "adversarial": {"n": len(adversarial), "violations": len(violations),
                        "by_arm": dict(Counter(a for r in adversarial for a in r["arms"]))},
        "wrong": [{"cik": r["cik"], "rules": r["rules"], "final": r["final"],
                   "note": r.get("note")} for r in sample + adversarial if r["final"] != "same"],
        "files": {name: sha256(out / name) for name in
                  ("08-1-sample.jsonl", "08-1-adversarial.jsonl", "08-1-population.json")},
    }
    (out / "08-1-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=1, sort_keys=True))


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "draw":
        draw(Path(args[0]), Path(args[1]), Path(args[2]))
    else:
        score(Path(args[0]))
