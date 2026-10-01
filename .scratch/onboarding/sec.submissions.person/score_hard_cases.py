"""Score `sec-person-candidate` on the agent-drafted hard cases (log Q8:
"yes"; "Step 2"). Offline: no request leaves the machine.

A violation is a decided verdict that contradicts the case's truth: a person
called an entity, or an entity called a person. A hold-back (`deferred`) is
not a violation; it costs coverage, not precision.

    uv run --no-sync python .scratch/onboarding/sec.submissions.person/score_hard_cases.py <rules-root>
"""
import json, pathlib, sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from score_classification import NAMED, documents  # noqa: E402

from edgar_warehouse.mdm.clean.classification import fired, resolve_rule
from edgar_warehouse.rules import files

HERE = pathlib.Path(__file__).parent
DECIDED = {"person": "person", "entity_undetermined": "entity"}


def main():
    policy = files.policy(root=pathlib.Path(sys.argv[1]))
    rule, doc = resolve_rule(policy, NAMED), policy["kinds"]["person"]
    paths = documents()
    cases = [json.loads(l) for l in open(HERE / "hard-cases-draft.jsonl")]
    rows, outcome = [], Counter()
    for case in cases:
        verdict, step = fired(rule, json.loads(paths[case["cik"]].read_text()), doc)
        decided = DECIDED.get(verdict)
        result = "held back" if decided is None else ("right" if decided == case["truth"] else "VIOLATION")
        outcome[result] += 1
        rows.append({**case, "verdict": verdict, "step": step, "result": result})
    (HERE / "hard-cases-scored.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(json.dumps({"cases": len(cases), "outcome": dict(outcome),
                      "by_family": {f: dict(Counter(r["result"] for r in rows if r["family"] == f))
                                    for f in sorted({r["family"] for r in rows})},
                      "violations": [{k: r[k] for k in ("cik", "name", "family", "truth", "uncertain", "verdict", "step")}
                                     for r in rows if r["result"] == "VIOLATION"]}, indent=1))


if __name__ == "__main__":
    main()
