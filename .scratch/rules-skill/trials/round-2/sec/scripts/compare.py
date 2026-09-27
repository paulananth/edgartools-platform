"""Before/after answer 5: what changed in what MDM would receive, plus proof
that no binding rule can join on ein or sec_lei."""
import json, sys
from pathlib import Path
from edgar_warehouse.mdm.clean.activation import check_binding_rule
from edgar_warehouse.mdm.clean.store import Conflict
from edgar_warehouse.rules import files

a, b = (json.loads(Path(p).read_text()) for p in sys.argv[1:3])
da, db = (json.loads(Path(p).read_text()) for p in sys.argv[3:5])
old = {x["record_key"]: x for x in a}; new = {x["record_key"]: x for x in b}
print("companies before/after:", len(old), len(new), "set aside before/after:", len(da), len(db),
      "same set-aside CIKs:", sorted(d["cik"] for d in da) == sorted(d["cik"] for d in db))
for k in sorted(new):
    o, n = old[k], new[k]
    changed = sorted(p for p in n if p != "assertion_id" and n[p] != o[p])
    print(f"  {k} identifiers {o['identifiers']} -> {n['identifiers']} | other keys changed: {changed} | "
          f"assertion_id changed: {o['assertion_id'] != n['assertion_id']}")
kinds = files.policy()["kinds"]
for ns in ("ein", "sec_lei", "ticker", "lei"):
    rule = {"rule_id": f"probe-{ns}", "applies_to_verdict": "company", "emits": ["bind"], "on_no_match": "wait",
            "when": [{"primitive": "identifier_match@1", "args": {"namespace": ns}}]}
    try:
        check_binding_rule("company", rule, kinds); print(f"binding rule on {ns}: accepted by the rule checker")
    except (Conflict, ValueError, KeyError) as e:
        print(f"binding rule on {ns}: refused -> {e}")
