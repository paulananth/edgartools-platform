"""The N-PORT registrant test run (ticket 79, part 2): every stage once, counts only.

submissions reading -> pair set `filed` -> registrant reading -> reduce -> combine
-> mdm.prepare -> the Dataset Contract. Usage: registrant_test_run.py ZIP OUT"""
import hashlib, json, sys, time
from collections import Counter
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare, source_readings
from edgar_warehouse.mdm.clean import adapters

ZIP, OUT = Path(sys.argv[1]), Path(sys.argv[2])
NAME, CODE = "sec.nport.registrant", "sec.nport.registrant.v1"
FOLDER = Path("rules/sources") / NAME
store = Artifacts(); begun = time.monotonic()
digest = hashlib.sha256()
with ZIP.open("rb") as f:
    for block in iter(lambda: f.read(1 << 20), b""):
        digest.update(block)
capture = {"uri": ZIP.as_uri(), "sha256": digest.hexdigest()}
def reading(root, body, artifact):
    root.mkdir(parents=True, exist_ok=True)
    contract = store.put(root.as_uri(), body)
    manifest = store.put(root.as_uri(), {"version": 3 if "lookups" in artifact else 2, "contract": contract, "artifacts": [artifact]})
    return source_read.execute({"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}, store)
def context(root):
    root.mkdir(parents=True, exist_ok=True)
    return store.put(root.as_uri(), {"version": 1, "input": capture, "values": {}})
def combine(root, body, readings):
    root.mkdir(parents=True, exist_ok=True)
    c = store.put(root.as_uri(), body)
    m = store.put(root.as_uri(), {"version": 1, "contract": c, "readings": readings})
    work = {"input": m, "output": (root / "output/combined.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
    out = source_combine.execute(work, store)
    assert source_combine.verify({**work, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    return out
def tables(ref):
    out = {}
    for a in source_readings.load(ref, store, max_bytes=1 << 32, max_rows=10**7, allow_lookup_receipts=True)[0]["artifacts"]:
        for k, v in a["tables"].items():
            out.setdefault(k, []).extend(v)
    return out

subs = reading(OUT / "submissions", {"source": NAME, **files.load(FOLDER / "submissions.yaml")}, {"input": capture, "context": context(OUT / "submissions")})
dates = Counter(len((r["filed"] or "").split()) == 3 and (r["filed"] or "")[:2] == "20" for r in tables(subs)["filed"])
doc = files.source(NAME)
lookups = store.put((OUT / "filings").as_uri(), {"version": 2, "input": capture, "sets": {"filed": {
    "readings": [subs], "table": "filed", "column": "accession", "value_column": "filed",
    "max_input_bytes": 1 << 30, "max_input_rows": 1_000_000}}})
filings = reading(OUT / "filings", {k: doc[k] for k in ("source", "execution", "read")},
                  {"input": capture, "context": context(OUT / "filings"), "lookups": lookups})
rows = tables(filings)["filing"]
facts = {"filings": len(rows), "filing_dates_sortable": dates[True], "filing_dates_not": dates[False],
         "filings_without_date": sum(r["filed"] is None for r in rows),
         "filings_lei_blank": sum(r["lei"] is None for r in rows), "filings_street2_blank": sum(r["street2"] is None for r in rows)}
ciks = combine(OUT / "reduce", files.load(FOLDER / "reduce.yaml"), {"filings": filings})
combined = combine(OUT / "combine", files.load(FOLDER / "combine.yaml"), {"ciks": ciks, "filings": filings})
reg = tables(combined)["registrant"]
facts.update(registrants=len(reg), registrants_several_filings=sum(r["filings"] > 1 for r in reg),
             names_differ_across_filings=None)
root = OUT / "mdm"
work = {"input": combined, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
        "keys": {"table": "registrant", "dataset": CODE, "policy": "0" * 64, "consumer": "trial",
                 "batch_id": "nport-registrant-trial", "as_of": "2026-10-15T00:00:00+00:00"}}
prepared = mdm_prepare.execute(work, store)
assert mdm_prepare.verify({**work, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
contract = doc["mdm"][CODE]["contract"]
outcome, filled = Counter(), Counter()
for b in store.json(prepared)["batches"]:
    for rec in map(json.loads, (root / b["input"]["path"]).read_bytes().splitlines()):
        try:
            r = adapters.normalize(rec, source_code=CODE, contract=contract, publication={
                **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"], "member": b["input"]["path"]})
            outcome["accepted"] += 1
            for f, v in (r.get("fields") or {}).items():
                if isinstance(v, dict):
                    for sub, x in v.items():
                        filled[f"{f}.{sub}"] += x is not None
                else:
                    filled[f] += v is not None
            for ns in (r.get("identifiers") or {}):
                filled["id:" + ns] += 1
            for ns in (r.get("cross_references") or {}):
                filled["xref:" + ns] += 1
        except adapters.UnsupportedRecord as x:
            outcome[x.reason] += 1
report = {"facts": facts, "contract": {"outcome": dict(outcome), "filled": dict(filled)}, "seconds": round(time.monotonic() - begun, 1)}
print(json.dumps(report, indent=1))
(OUT / "report.json").write_text(json.dumps(report, indent=1))
