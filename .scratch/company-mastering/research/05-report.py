"""Ticket 05, step 7: summarise the Proving Run against CIK manifest v1.

Reads the harness report (`05_proving_run.py`) and the manifest, and writes
two files: one line per manifest CIK with its outcome (no entity ids, which
are random), and a summary with the counts, the named Companies and
controls, and every disagreement between the research labels
(`08-companies.py`) and what the production path did.

    uv run --no-sync python .scratch/company-mastering/research/05-report.py \\
        <05-manifest.json> <harness-report.json> <outcomes.jsonl> <summary.json>
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter

NAMED = {
    "0000320193": "Apple",
    "0000789019": "Microsoft",
    "0001306965": "Shell",
    "0000937966": "ASML",
    "0001214156": "Tim Cook (control)",
    "0001513142": "Satya Nadella (control)",
}


def outcome(rec: dict | None) -> str:
    if rec is None:
        return "not landed"
    if rec.get("entity_id"):
        return "Company by CIK"
    if rec.get("waiting"):
        return "waiting"
    if rec.get("stage_kind") == "company":
        return "Company kind, no Company"
    return "other"


def main(manifest: str, harness: str, outcomes: str, summary: str) -> None:
    with open(manifest, "rb") as stream:
        manifest_bytes = stream.read()
    body = json.loads(manifest_bytes)
    with open(harness) as stream:
        report = json.load(stream)
    chunks = report["chunks"]
    rows = []
    for n in chunks:
        for member in body["chunks"][n - 1]:
            rec = report["records"].get(member["cik"])
            rows.append(
                {
                    "cik": member["cik"],
                    "chunk": n,
                    "research_label": member["role"],
                    "outcome": outcome(rec),
                    "probable_kind": (rec or {}).get("probable_kind"),
                    "reason": (rec or {}).get("reason"),
                    "step": (rec or {}).get("step"),
                }
            )
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode()
    with open(outcomes, "wb") as stream:
        stream.write(data)
    table = Counter((r["research_label"], r["outcome"]) for r in rows)
    disagreements = [
        r
        for r in rows
        if (r["research_label"] == "company") != (r["outcome"] == "Company by CIK")
    ]
    waiting = Counter(
        (r["probable_kind"], r["step"]) for r in rows if r["outcome"] == "waiting"
    )
    first, second = report["after_first_pass"], report["after_second_pass"]
    out = {
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "outcomes_sha256": hashlib.sha256(data).hexdigest(),
        "chunks": chunks,
        "records_in_manifest": len(rows),
        "records_prepared": sum(b["records"] for b in report["bundles"]),
        "by_research_label_and_outcome": {
            f"{label} -> {result}": count for (label, result), count in sorted(table.items())
        },
        "waiting_by_probable_kind_and_step": {
            f"{kind} / step {step}": count for (kind, step), count in sorted(
                waiting.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
            )
        },
        "disagreements_with_research_labels": disagreements,
        "named": {
            name: next((r["outcome"] for r in rows if r["cik"] == cik), "not in run")
            for cik, name in NAMED.items()
        },
        "companies_created": first["identities"].get("company", 0),
        "cik_on_more_than_one_company": report["cik_on_more_than_one_company"],
        "company_with_more_than_one_sec_record": report[
            "company_with_more_than_one_sec_record"
        ],
        "open_reviews": first["open_reviews"],
        "second_pass_changed_nothing": first == second,
        "candidate_policy_for_approval": report["candidate_policy_for_approval"],
        "registered_for_the_run": report["registered_for_the_run"],
        "live_policy": report["live_policy"],
        "bundles": report["bundles"],
        "timings": [
            {k: t[k] for k in ("chunk", "records", "seconds")} for t in report["timings"]
        ],
        "sql_functions_first_pass": report["sql_functions_first_pass"],
    }
    with open(summary, "w") as stream:
        stream.write(json.dumps(out, sort_keys=True, indent=1) + "\n")
    print(json.dumps({k: out[k] for k in out if k not in ("bundles", "disagreements_with_research_labels")}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:5])
