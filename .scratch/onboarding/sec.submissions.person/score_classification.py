"""Score the ported Person classification rule against research 18's labels.

Reads each labelled owner's submissions document from the pinned capture
(all-76230), runs `sec-person-candidate` exactly as `normalize` would
(`classification.fired`), and scores each step against the label. Offline:
no request leaves the machine.

    uv run --no-sync python .scratch/onboarding/sec.submissions.person/score_classification.py <rules-root>
"""
import json, math, pathlib, re, sys
from collections import Counter, defaultdict

from edgar_warehouse.mdm.clean.classification import fired, resolve_rule
from edgar_warehouse.rules import files

ROOT = pathlib.Path(sys.argv[1])
CAPTURE = pathlib.Path.home() / ".local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230"
RESEARCH = pathlib.Path(".scratch/person-consumer-contract/research")
NAMED = {"kind": "person", "rule_id": "sec-person-candidate", "version": "2026-09-30.1"}


def wilson_lower(k, n, z=1.959964):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


def documents():
    found = {}
    for line in open(CAPTURE / "receipts.jsonl"):
        key = json.loads(line).get("key", "")
        m = re.search(r"CIK(\d{10})\.json$", key)
        if m and "/pagination/" not in key:
            found[int(m.group(1))] = CAPTURE / "bronze" / key.removeprefix("warehouse/bronze/")
    return found


def main():
    policy = files.policy(root=ROOT)
    rule = resolve_rule(policy, NAMED)
    doc = policy["kinds"]["person"]
    paths = documents()
    labelled = [json.loads(l) for l in open(RESEARCH / "18-sample.jsonl")]
    labelled += [dict(json.loads(l), extension=True) for l in open(RESEARCH / "18-extension-sample.jsonl")]
    by_step = defaultdict(Counter)
    wrong = []
    for row in labelled:
        record = json.loads(paths[row["owner_cik"]].read_text())
        verdict, step = fired(rule, record, doc)
        by_step[(step, verdict)][row["label"]] += 1
        right = {"person": "person", "entity_undetermined": "entity"}.get(verdict)
        if right and right != row["label"]:
            wrong.append({"cik": row["owner_cik"], "name": record.get("name"), "step": step,
                          "verdict": verdict, "label": row["label"], "uncertain": row.get("uncertain")})
    out = {"rule": NAMED, "labels": len(labelled), "steps": {}, "wrong": wrong}
    for (step, verdict), labels in sorted(by_step.items()):
        right = {"person": "person", "entity_undetermined": "entity"}.get(verdict)
        entry = {"verdict": verdict, "labels": dict(labels)}
        if right:
            k, n = labels[right], sum(labels.values())
            entry.update(correct=k, total=n, wilson_lower_95=round(wilson_lower(k, n), 4),
                         wilson_lower_975=round(wilson_lower(k, n, z=2.241403), 4))
        out["steps"][f"{step} ({verdict})"] = entry
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
