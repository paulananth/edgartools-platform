"""Proving Run, classification part (company mastering ticket 12).

Measures `sec-company-candidate`'s `company` verdict on bronze. Zero SEC
requests: the population is the newest bronze `submissions.json` per CIK,
summarised by `.scratch/individual-filer-company-misclassification/research/
05-scan-bronze-entity-types.py` (76,230 CIKs, 2026-09-24).

The rule is run by the engine itself (`classification.fired`), from the
Company policy in the repo, so the number measures the code that will run.

Labels come from evidence the rule does **not** read. The rule reads
`entityType`, `sic` and a legal-form word in the name; the draft label reads
the forms filed, tickers, exchanges and filer category first, and the name
only when none of those decides. Every
draft that is not a plain "company" is then read by hand (`12-sample.jsonl`,
`final` and `note`), as research 18 did.

    uv run python .scratch/company-mastering/research/12-classify.py \\
        sample <summary.jsonl> <out-dir>
    uv run python .scratch/company-mastering/research/12-classify.py \\
        score <out-dir>
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import socket
import sys
from collections import Counter
from pathlib import Path

from edgar_warehouse.mdm.clean.activation import wilson_lower_bound
from edgar_warehouse.mdm.clean.classification import fired
from edgar_warehouse.mdm.policies import load_kinds


def _no_network(*args, **kwargs):
    raise RuntimeError("12-classify.py makes no network requests")


socket.socket = _no_network  # type: ignore[assignment,misc]

# A fresh seed per frozen version: each earlier draw shaped the next version
# (20260924 -> .4 held back people, loan trusts, governments; 20260924.4 ->
# .5 held back exchange-traded trusts; 20260924.5 -> .6 held back an `other`
# name with a person's suffix, found by the adversarial arm, not the sample),
# so none of them may measure it.
SEED = "20260924.6"
# Individuals SEC gave an industry code whose name carries a legal-form word
# the draft's own pattern would take for an entity: read by hand.
HAND_PEOPLE = {"0001065416"}  # HOLDING FRANK B JR: surname Holding
# ...and the reverse: an entity the draft's pattern misses (a spaced "L P").
HAND_ENTITIES = {"0000779335"}  # GOULD INVESTORS L P: a limited partnership
SAMPLE_SIZE = 300
CONFIDENCE = 0.95
ADVERSARIAL_PER_ARM = 100

# A company-only form: an issuer's periodic report or registration.
COMPANY_FORMS = {
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "8-K",
    "8-K/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
    "6-K",
    "6-K/A",
    "S-1",
    "S-1/A",
    "F-1",
    "F-1/A",
    "S-3",
    "F-3",
    "S-4",
    "F-4",
    "S-8",
    "10-12G",
    "10-12B",
    "20FR12B",
    "8-A12B",
    "DEF 14A",
    "ARS",
    "1-A",
    "1-K",
    "C",
    "C-AR",
    "11-K",
    "424B2",
    "424B3",
    "424B4",
    "424B5",
    "15-12G",
    "15-15D",
    "NT 10-K",
    "NT 20-F",
    "D",
    "D/A",
    "13F-HR",
    "ADV-NR",
    "X-17A-5",
    "TA-1",
    "TA-2",
    "N-54A",
}
# A fund-only form: a registered fund's report or prospectus.
FUND_FORMS = {
    "N-CSR",
    "N-CSRS",
    "N-CEN",
    "NPORT-P",
    "485BPOS",
    "485APOS",
    "497",
    "497K",
    "497J",
    "24F-2NT",
    "N-1A",
    "N-PX",
    "N-30D",
    "N-30B-2",
    "N-VPFS",
    "N-MFP",
    "N-MFP2",
    "N-MFP3",
    "N-Q",
    "N-4",
    "N-6",
    "N-3",
    "S-6",
    "N-8B-2",
}
PERIODIC = {"10-K", "10-Q", "20-F", "40-F"}
OWNERSHIP_FORMS = {
    "3",
    "3/A",
    "4",
    "4/A",
    "5",
    "5/A",
    "144",
    "144/A",
    "SC 13D",
    "SC 13D/A",
    "SC 13G",
    "SC 13G/A",
    "SCHEDULE 13D",
    "SCHEDULE 13D/A",
    "SCHEDULE 13G",
    "SCHEDULE 13G/A",
}
LEGAL_FORM = re.compile(
    r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|LLC|"
    r"L\.?L\.?C|LP|L\.?P|LLP|SE|NV|N\.V|AG|SA|S\.A|SPA|S\.P\.A|AB|ASA|OYJ|KK|"
    r"BV|B\.V|GMBH|HOLDINGS?|GROUP|TRUST|BANK|BANCORP|FUND|PARTNERS|CAPITAL|"
    r"TECHNOLOGIES|PHARMACEUTICALS|THERAPEUTICS|ENERGY|RESOURCES|MINING)\b",
    re.IGNORECASE,
)


def row(record: dict) -> dict:
    """The three fields the rule reads, as the SEC landing row holds them."""
    return {
        "entity_type": record.get("entityType"),
        "sic": record.get("sic") or None,
        "entity_name": record.get("name"),
    }


def rule() -> tuple[dict, dict]:
    block = load_kinds()["company"]
    (candidate,) = [
        r for r in block["rules"] if r["rule_id"] == "sec-company-candidate"
    ]
    return candidate, block


def draft_label(record: dict) -> tuple[str, str]:
    """A label from evidence the rule never reads; never `entityType`/`sic`."""
    forms = set(record.get("forms") or {})
    name = record.get("name") or ""
    if forms & FUND_FORMS and not forms & PERIODIC:
        return "fund", "files fund forms and no periodic report"
    if forms & {"18-K", "18-K/A"}:
        return "government", "files 18-K, a foreign government's annual report"
    if forms & {"ANNLRPT", "QRTLYRPT", "DSTRBRPT"}:
        return "development bank", "files a development bank's reports"
    if forms & {"10-D", "ABS-EE", "ABS-15G"} and not forms & PERIODIC:
        return "loan trust", "files asset-backed reports (10-D, ABS-EE)"
    if forms & COMPANY_FORMS:
        return "company", "files company forms: " + ",".join(
            sorted(forms & COMPANY_FORMS)[:4]
        )
    if record.get("tickers") or record.get("exchanges"):
        return "company", "has a ticker or exchange"
    if record.get("category"):
        return "company", f"filer category {record['category']}"
    if LEGAL_FORM.search(name):
        return "company", "legal-form word in the name"
    if forms and forms <= OWNERSHIP_FORMS:
        return "individual", "ownership forms only and no legal-form word"
    return "unsure", "no decisive evidence"


def population(summary: Path) -> list[dict]:
    records = []
    for line in summary.open():
        r = json.loads(line)
        if "cik" in r:
            records.append(r)
    return records


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample(summary: Path, out: Path) -> None:
    candidate, block = rule()
    everyone = population(summary)
    verdicts = Counter()
    fired_company = []
    for r in everyone:
        verdict, step = fired(candidate, row(r), block)
        verdicts[(verdict, step)] += 1
        if verdict == "company":
            fired_company.append({**r, "step": step})
    fired_company.sort(key=lambda r: r["cik"])
    drawn = random.Random(SEED).sample(fired_company, SAMPLE_SIZE)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "12-sample.jsonl").open("w") as f:
        for r in sorted(drawn, key=lambda r: r["cik"]):
            label, reason = draft_label(r)
            f.write(
                json.dumps(
                    {
                        "cik": r["cik"],
                        "name": r["name"],
                        "step": r["step"],
                        "forms": sorted(r["forms"])[:12],
                        "tickers": r.get("tickers"),
                        "category": r.get("category"),
                        "draft": label,
                        "draft_reason": reason,
                        "final": label if label == "company" else None,
                        "note": None,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    # Adversarial fixture: records the rule must never call a Company.
    # Individuals (ownership forms only, no legal-form word) and funds
    # (SEC `investment`), drawn by the same seed.
    individuals = sorted(
        (r for r in everyone if draft_label(r)[0] == "individual" and not r.get("sic")),
        key=lambda r: r["cik"],
    )
    funds = sorted(
        (r for r in everyone if r.get("entityType") == "investment"),
        key=lambda r: r["cik"],
    )
    # The hard arm, in full: individuals SEC gave an industry code, which step
    # 1's lookup and a bare "has a SIC" test both take for companies.
    coded_people = [
        r
        for r in everyone
        if r.get("entityType") == "other"
        and r.get("sic")
        and set(r.get("forms") or {})
        and set(r["forms"]) <= OWNERSHIP_FORMS
        and (not LEGAL_FORM.search(r.get("name") or "") or r["cik"] in HAND_PEOPLE)
        and r["cik"] not in HAND_ENTITIES
    ]
    rng = random.Random(SEED + "-adversarial")
    adversarial = (
        rng.sample(individuals, ADVERSARIAL_PER_ARM)
        + rng.sample(funds, ADVERSARIAL_PER_ARM)
        + coded_people
    )
    arms = {r["cik"]: "individual with industry code" for r in coded_people}
    with (out / "12-adversarial.jsonl").open("w") as f:
        for r in sorted(adversarial, key=lambda r: r["cik"]):
            f.write(
                json.dumps(
                    {
                        "cik": r["cik"],
                        "name": r["name"],
                        "entity_type": r.get("entityType"),
                        "sic": r.get("sic") or None,
                        "arm": arms.get(
                            r["cik"],
                            "fund"
                            if r.get("entityType") == "investment"
                            else "individual",
                        ),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    (out / "12-population.json").write_text(
        json.dumps(
            {
                "summary_sha256": sha256(summary),
                "records": len(everyone),
                "verdicts": {f"{v}/{s}": n for (v, s), n in sorted(verdicts.items())},
                "company_verdicts": len(fired_company),
                "seed": SEED,
                "sample_size": SAMPLE_SIZE,
                "rule": {
                    "rule_id": candidate["rule_id"],
                    "version": candidate["version"],
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def score(out: Path) -> None:
    candidate, block = rule()
    lines = [json.loads(line) for line in (out / "12-sample.jsonl").open()]
    open_labels = [r["cik"] for r in lines if r["final"] is None]
    if open_labels:
        raise SystemExit(f"{len(open_labels)} sample lines have no final label")
    by_step: dict[str, Counter] = {}
    for r in lines:
        by_step.setdefault(r["step"], Counter())[r["final"] == "company"] += 1
    n = len(lines)
    correct = sum(r["final"] == "company" for r in lines)
    violations = []
    for line in (out / "12-adversarial.jsonl").open():
        a = json.loads(line)
        verdict, _ = fired(
            candidate,
            {
                "entity_type": a["entity_type"],
                "sic": a["sic"],
                "entity_name": a["name"],
            },
            block,
        )
        if verdict == "company":
            violations.append(a["cik"])
    files = {
        name: sha256(out / name)
        for name in ("12-sample.jsonl", "12-adversarial.jsonl", "12-population.json")
    }
    files["12-classify.py"] = sha256(Path(__file__))
    summary = {
        "rule": {"rule_id": candidate["rule_id"], "version": candidate["version"]},
        "n": n,
        "correct": correct,
        "lower_bound": wilson_lower_bound(correct, n, CONFIDENCE),
        "one_sided_confidence": CONFIDENCE,
        "by_step": {
            step: {
                "n": sum(c.values()),
                "correct": c[True],
                "lower_bound": wilson_lower_bound(c[True], sum(c.values()), CONFIDENCE),
            }
            for step, c in sorted(by_step.items())
        },
        "errors": [
            {"cik": r["cik"], "name": r["name"], "final": r["final"], "note": r["note"]}
            for r in lines
            if r["final"] != "company"
        ],
        "adversarial": {
            "n": sum(1 for _ in (out / "12-adversarial.jsonl").open()),
            "violations": len(violations),
            "violating_ciks": violations,
        },
        "files": files,
    }
    (out / "12-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    if command == "sample":
        sample(Path(args[0]), Path(args[1]))
    elif command == "score":
        score(Path(args[0]))
    else:
        raise SystemExit(f"unknown command {command}")
