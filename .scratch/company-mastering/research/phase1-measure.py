"""Measure the phase 1 Company classification (rule 2026-11-09.phase-1-listed-operating), counts only.

Operator, 2026-11-09: "For phase 1 master only publically traded companies (filter)"; "Operating and listed a real company".
Reads the hand-labelled draws of ticket 12 (`12-13-sample.jsonl`, `12-13-adversarial.jsonl`) and, when MDM_DATABASE_URL is set,
the company records the old rule set aside; prints how many each step of the new rule gives, and the Wilson bound.

    uv run python .scratch/company-mastering/research/phase1-measure.py
"""

import json
import os
from collections import Counter
from pathlib import Path

from edgar_warehouse.mdm import classification
from edgar_warehouse.mdm.activation import wilson_lower_bound
from edgar_warehouse.rules import files

HERE = Path(__file__).resolve().parent
POLICY = files.policy()
RULE = next(r for r in POLICY["kinds"]["company"]["rules"] if r["rule_id"] == "sec-company-candidate")
LISTS = POLICY["kinds"]["company"].get("lists") or {}
DOC = {"lists": LISTS, "normalizers": {"conformed": "normalize_text@edgar-conformed-v1"}}


def classify(record: dict) -> tuple[str, str]:
    return classification.fired(RULE, record, {**DOC, "sic": record.get("sic") or "", "category": record.get("category") or ""})


def labelled(row: dict) -> dict:
    return {"entity_type": row["entity_type"], "entity_name": row["name"], "category": row.get("category") or "",
            "sic": row.get("sic") or "", "forms": row.get("forms") or [],
            "tickers": row.get("own_tickers") or row.get("catalog_tickers") or [], "state_of_incorporation": ""}


def draw(name: str) -> Counter:
    out = Counter()
    for line in (HERE / name).read_text().splitlines():
        row = json.loads(line)
        verdict, step = classify(labelled(row))
        out[(row["final"], verdict, step)] += 1
    return out


def main() -> None:
    sample, adversarial = draw("12-13-sample.jsonl"), draw("12-13-adversarial.jsonl")
    for name, counts in (("sample (600)", sample), ("adversarial (328)", adversarial)):
        company = sum(n for (final, verdict, _), n in counts.items() if verdict == "company")
        wrong = sum(n for (final, verdict, _), n in counts.items() if verdict == "company" and final != "company")
        print(f"{name}: classed Company {company}, of them labelled not a Company {wrong}; "
              f"bound {wilson_lower_bound(company - wrong, company, 0.95):.6f}" if company else f"{name}: none")
    print("sample by new step:", {f"{v}:{s}": n for (f, v, s), n in sample.items()})
    if os.environ.get("MDM_DATABASE_URL"):
        import sqlalchemy as sa
        engine = sa.create_engine(os.environ["MDM_DATABASE_URL"])
        became = Counter()
        with engine.connect() as conn:
            for (body,) in conn.execute(sa.text("select body from mastering_deferred where source_code='sec.company.v1'")):
                raw = json.loads(body)["raw_record"]
                record = {"entity_type": raw.get("entity_type") or "", "entity_name": raw.get("entity_name") or "",
                          "category": raw.get("category") or "", "sic": raw.get("sic") or "", "forms": raw.get("forms") or [],
                          "tickers": raw.get("tickers") or [], "state_of_incorporation": ""}
                verdict, step = classify(record)
                became[(verdict, step)] += 1
        print("set-aside company-source records under the new rule:", {f"{v}:{s}": n for (v, s), n in became.items()})


if __name__ == "__main__":
    main()
