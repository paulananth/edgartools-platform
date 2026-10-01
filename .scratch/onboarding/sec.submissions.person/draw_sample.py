"""Draw the fresh labelled sample for the Person classification proof (log Q7).

Operator, 2026-10-01: "B, agent drafts labels, I'll check". Filers are taken
in a seeded random order from the pinned capture (all-76230), skipping every
CIK research 18 already labelled, and the ported rule is run on each until
the quotas fill: 570 the rule calls a person (operator, Q12: one wrong call may pass),
150 it does not. Offline: no request leaves the machine.

Writes two files beside this script:
- `fresh-sample.jsonl`: CIK, name and document path only, for the labelling
  agent, which must not see the rule's verdict;
- `fresh-sample-key.jsonl`: the rule's verdict and step per CIK, kept back
  for scoring.

    uv run --no-sync python .scratch/onboarding/sec.submissions.person/draw_sample.py <rules-root>
"""
import json, pathlib, random, sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from score_classification import NAMED, RESEARCH, documents  # noqa: E402

from edgar_warehouse.mdm.clean.classification import fired, resolve_rule
from edgar_warehouse.rules import files

SEED = 20261001
QUOTA = {"person": 570, "not person": 150}
HERE = pathlib.Path(__file__).parent


def main():
    policy = files.policy(root=pathlib.Path(sys.argv[1]))
    rule, doc = resolve_rule(policy, NAMED), policy["kinds"]["person"]
    labelled = {json.loads(l)["owner_cik"] for name in ("18-sample.jsonl", "18-extension-sample.jsonl")
                for l in open(RESEARCH / name)}
    paths = documents()
    order = sorted(set(paths) - labelled)
    random.Random(SEED).shuffle(order)
    taken, sample, key, seen = Counter(), [], [], 0
    for cik in order:
        if taken == Counter(QUOTA):
            break
        seen += 1
        record = json.loads(paths[cik].read_text())
        verdict, step = fired(rule, record, doc)
        stratum = "person" if verdict == "person" else "not person"
        if taken[stratum] >= QUOTA[stratum]:
            continue
        taken[stratum] += 1
        sample.append({"cik": cik, "name": record.get("name"), "document": str(paths[cik])})
        key.append({"cik": cik, "stratum": stratum, "verdict": verdict, "step": step})
    random.Random(SEED + 1).shuffle(sample)
    (HERE / "fresh-sample.jsonl").write_text("".join(json.dumps(r) + "\n" for r in sample))
    (HERE / "fresh-sample-key.jsonl").write_text("".join(json.dumps(r) + "\n" for r in key))
    print(json.dumps({"seed": SEED, "filers_read": seen, "skipped_research_18": len(labelled),
                      "taken": dict(taken), "steps": dict(Counter(f"{k['step']} ({k['verdict']})" for k in key))},
                     indent=1))


if __name__ == "__main__":
    main()
