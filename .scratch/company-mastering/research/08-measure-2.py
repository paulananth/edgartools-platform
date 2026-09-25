"""Proving Run for the Postcode rule with state veto, 2026-09-25.2 (ticket 08).

`sec-gleif-name-postal` version 2026-09-25.2 is version .1 (the
Name-and-postcode rule) plus one veto: SEC and GLEIF must not name two
different places of incorporation (`jurisdictions_conflict`,
`clean/names.py`). Version .1 failed on exactly that shape: 19 of its 162
adversarial pairs, AAON, Inc. among them (`08-1-summary.json`). Its draw
designed this version, so every CIK it drew is left out here, with the 1,000
development CIKs and the four acceptance Companies.

The Name-and-state rule (`sec-gleif-name-jurisdiction` 2026-09-25.1) passed
in `08-1` and is not re-drawn.

- `08-2-sample.jsonl`: 300 pairs the rule binds, simple random, fresh seed;
- `08-2-adversarial.jsonl`: up to 100 pairs per arm, from pairs the rule
  binds that the sample did not draw:
  - the postcode agrees and the jurisdiction does not (SEC names no place,
    or one side names only a country);
  - SEC's US state set aside because SEC's business address and GLEIF's
    jurisdiction both name one other country;
  - a foreign filer (SEC entity type `other`);
  - a name of one word before its legal form;
  - GLEIF's legal address is a registered agent's;
  - GLEIF's headquarters city differs from SEC's business city.

    python .scratch/company-mastering/research/08-measure-2.py \\
        draw <coverage-2.jsonl> <gleif-all.jsonl> <out-dir>
    python .scratch/company-mastering/research/08-measure-2.py score <out-dir>
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("m1", HERE / "08-measure-1.py")
m1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m1)

from edgar_warehouse.mdm.clean.names import edgar_jurisdiction  # noqa: E402

SEED = "20260925.08-2"
RULE = "sec-gleif-name-postal@2026-09-25.2"
SAMPLE_SIZE = 300
PER_ARM = 100
EARLIER = ("08-1-sample.jsonl", "08-1-adversarial.jsonl")


def fired(r: dict) -> bool:
    if "gleif" not in r or r["outcome"] == "no GLEIF record with this name":
        return False
    if r["outcome"].startswith(m1.ELIGIBLE_DEFERS):
        return False
    return r["agree"]["postal_rule"]


def arms_of(r: dict, g: dict) -> list[str]:
    arms = []
    if not r["agree"]["jurisdiction"]:
        arms.append("postcode agrees, jurisdiction does not")
    business = (r.get("addresses") or {}).get("business") or {}
    place = edgar_jurisdiction(business.get("stateOrCountry") or business.get("countryCode"))
    sec = edgar_jurisdiction(r.get("state_of_incorporation"))
    if sec and sec.startswith("US-") and place and not place.startswith("US") and not r["agree"]["jurisdiction"]:
        arms.append("SEC US state set aside")
    if r.get("entity_type") == "other":
        arms.append("foreign filer")
    if len([t for t in r["key"].split() if t not in m1.FORMS]) <= 1:
        arms.append("one-word name")
    if m1.AGENT.search(" ".join((g.get("legal") or {}).get("lines") or [])):
        arms.append("registered agent legal address")
    hq_city = ((g.get("hq") or {}).get("city") or "").upper().replace(".", "")
    sec_city = (business.get("city") or "").upper().replace(".", "")
    if hq_city and sec_city and hq_city != sec_city:
        arms.append("headquarters city differs")
    return arms


def draw(coverage: Path, gleif_all: Path, out: Path) -> None:
    with m1.DEV.open() as f:
        excluded = {f"{int(json.loads(line)['cik']):010d}" for line in f}
    for name in EARLIER:
        with (out / name).open() as f:
            excluded |= {json.loads(line)["cik"] for line in f}
    excluded |= m1.FOUR
    with coverage.open() as f:
        rows = [json.loads(line) for line in f]
    bound = {r["cik"]: r for r in rows if fired(r) and r["cik"] not in excluded}
    wanted = {r["gleif"]["lei"] for r in bound.values()}
    gleif = {}
    with gleif_all.open() as f:
        for line in f:
            if line[8:28] in wanted:
                g = json.loads(line)
                gleif[g["lei"]] = g
    population = sorted(bound)
    picked = random.Random(f"{SEED}-sample").sample(population, SAMPLE_SIZE)
    sample = []
    for cik in picked:
        row = m1.view(bound[cik], gleif[bound[cik]["gleif"]["lei"]], [RULE])
        row["drawn_for"] = [RULE]
        sample.append(row)
    by_arm: dict[str, list[str]] = {}
    for cik in population:
        if cik in picked:
            continue
        r = bound[cik]
        for arm in arms_of(r, gleif[r["gleif"]["lei"]]):
            by_arm.setdefault(arm, []).append(cik)
    adversarial, arm_sizes = {}, {}
    for arm in sorted(by_arm):
        members = by_arm[arm]
        chosen = random.Random(f"{SEED}-arm-{arm}").sample(members, min(PER_ARM, len(members)))
        arm_sizes[arm] = {"population": len(members), "drawn": len(chosen)}
        for cik in chosen:
            if cik in adversarial:
                adversarial[cik]["arms"].append(arm)
            else:
                r = bound[cik]
                adversarial[cik] = m1.view(r, gleif[r["gleif"]["lei"]], [RULE], [arm])
    m1.write(out / "08-2-sample.jsonl", sample)
    m1.write(out / "08-2-adversarial.jsonl", list(adversarial.values()))
    summary = {
        "rule": RULE,
        "seed": SEED,
        "coverage_sha256": m1.sha256(coverage),
        "population": len(population),
        "excluded": {"development_and_earlier_draws_and_acceptance": len(excluded)},
        "sample": {"population": len(population), "drawn": len(sample)},
        "adversarial_arms": arm_sizes,
        "adversarial_pairs": len(adversarial),
    }
    (out / "08-2-population.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=1, sort_keys=True))


def score(out: Path) -> None:
    def load(name):
        with (out / name).open() as f:
            return [json.loads(line) for line in f]

    sample, adversarial = load("08-2-sample.jsonl"), load("08-2-adversarial.jsonl")
    if any("final" not in r for r in sample + adversarial):
        raise SystemExit("unlabelled rows remain; run 08-2-label.py first")
    correct = sum(r["final"] == "same" for r in sample)
    summary = {
        "rule": RULE,
        "sample": {"n": len(sample), "correct": correct,
                   "lower_bound": round(m1.wilson(correct, len(sample)), 6)},
        "adversarial": {"n": len(adversarial),
                        "violations": sum(r["final"] != "same" for r in adversarial),
                        "by_arm": dict(Counter(a for r in adversarial for a in r["arms"]))},
        "wrong": [{"cik": r["cik"], "final": r["final"], "note": r.get("note")}
                  for r in sample + adversarial if r["final"] != "same"],
        "files": {name: m1.sha256(out / name) for name in
                  ("08-2-sample.jsonl", "08-2-adversarial.jsonl", "08-2-population.json")},
    }
    (out / "08-2-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=1, sort_keys=True))


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "draw":
        draw(Path(args[0]), Path(args[1]), Path(args[2]))
    else:
        score(Path(args[0]))
