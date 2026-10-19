"""Outcome and filled counts of a declared run's prepared records (pass 1), as openfigi_run.py counts them."""
import json, sys
from collections import Counter
from pathlib import Path
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.rules import files

env_file, code = Path(sys.argv[1]), sys.argv[2]
root = next(l.split("=", 1)[1].strip().strip("'\"") for l in env_file.read_text().splitlines()
            if l.startswith("export BOOKKEEPING_MANIFEST_ROOT="))
base = Path(root.removeprefix("file://"))
(folder,) = [p for p in base.glob("rules-test.openfigi.*/pass-1/prepare")]
contract = files.source("openfigi")["mdm"][code]["contract"]
outcome, filled = Counter(), Counter()
for b in json.loads((folder / "manifest.json").read_text())["batches"]:
    for rec in map(json.loads, (folder / b["input"]["path"]).read_bytes().splitlines()):
        try:
            r = adapters.normalize(rec, source_code=code, contract=contract, publication={
                **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                "member": b["input"]["path"]})
            outcome["accepted"] += 1
            for ns in r.get("identifiers") or {}: filled["id:" + ns] += 1
            for ns in r.get("cross_references") or {}: filled["xref:" + ns] += 1
        except adapters.UnsupportedRecord as refused:
            outcome[refused.reason] += 1
print(json.dumps({"outcome": dict(outcome), "filled": dict(sorted(filled.items()))}))
