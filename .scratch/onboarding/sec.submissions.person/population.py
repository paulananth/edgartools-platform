"""Run the ported Person classification rule over every filer of the pinned
capture: how many each step decides, and, among those it calls a person,
how many never filed a Form 3, 4 or 5 (outside research 18's population).

    uv run --no-sync python .scratch/onboarding/sec.submissions.person/population.py <rules-root>
"""
import json, pathlib, random, sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from score_classification import NAMED, documents  # noqa: E402

from edgar_warehouse.mdm.clean.classification import fired, resolve_rule
from edgar_warehouse.rules import files

OWNERSHIP = {"3", "4", "5", "3/A", "4/A", "5/A"}


def main():
    policy = files.policy(root=pathlib.Path(sys.argv[1]))
    rule, doc = resolve_rule(policy, NAMED), policy["kinds"]["person"]
    steps, people_forms, outside = Counter(), Counter(), []
    for cik, path in sorted(documents().items()):
        record = json.loads(path.read_text())
        verdict, step = fired(rule, record, doc)
        steps[f"{step} ({verdict})"] += 1
        if verdict == "person":
            forms = set((record.get("filings") or {}).get("recent", {}).get("form") or [])
            if forms & OWNERSHIP:
                people_forms["files Form 3/4/5"] += 1
            else:
                people_forms["never a Form 3/4/5"] += 1
                outside.append({"cik": cik, "name": record.get("name"),
                                "forms": sorted(forms)[:8]})
    random.Random(20261001).shuffle(outside)
    top = Counter(f for o in outside for f in o["forms"])
    print(json.dumps({"filers": sum(steps.values()), "steps": dict(sorted(steps.items())),
                      "people": dict(people_forms), "outside_forms": dict(top.most_common(15)),
                      "outside_sample": outside[:40]}, indent=1))


if __name__ == "__main__":
    main()
