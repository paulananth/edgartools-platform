"""The N-PORT Fund test run (ticket 79, part 3): every stage once, counts only.

Reuses part 2's verified readings (SUBMISSION's filing dates, REGISTRANT's
filings) as the two pair sets, so nothing is read twice; then the Fund
reading -> reduce -> combine -> mdm.prepare -> the Dataset Contract.
Usage: fund_test_run.py ZIP PART2_OUT OUT"""
import hashlib, json, sys, time
from collections import Counter
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare, source_readings
from edgar_warehouse.mdm.clean import adapters

ZIP, PART2, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
NAME, CODE = "sec.nport.fund", "sec.nport.fund.v1"
FOLDER = Path("rules/sources") / NAME
store = Artifacts(); begun = time.monotonic()
def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
capture = {"uri": ZIP.as_uri(), "sha256": sha(ZIP)}
def ref(path):
    return {"uri": path.as_uri(), "sha256": sha(path)}
def context(root):
    root.mkdir(parents=True, exist_ok=True)
    return store.put(root.as_uri(), {"version": 1, "input": capture, "values": {}})
def reading(root, body, artifact):
    root.mkdir(parents=True, exist_ok=True)
    contract = store.put(root.as_uri(), body)
    manifest = store.put(root.as_uri(), {"version": 3, "contract": contract, "artifacts": [artifact]})
    return source_read.execute({"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}, store)
def combine(root, body, readings):
    root.mkdir(parents=True, exist_ok=True)
    c = store.put(root.as_uri(), body)
    m = store.put(root.as_uri(), {"version": 1, "contract": c, "readings": readings})
    work = {"input": m, "output": (root / "output/combined.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
    out = source_combine.execute(work, store)
    assert source_combine.verify({**work, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    return out
def tables(r):
    out = {}
    for a in source_readings.load(r, store, max_bytes=1 << 32, max_rows=10**7, allow_lookup_receipts=True)[0]["artifacts"]:
        for k, v in a["tables"].items():
            out.setdefault(k, []).extend(v)
    return out

subs, regs = ref(PART2 / "submissions/reading.json"), ref(PART2 / "filings/reading.json")
pair = {"max_input_bytes": 1 << 30, "max_input_rows": 1_000_000}
lookups = store.put((OUT / "funds").as_uri(), {"version": 2, "input": capture, "sets": {
    "filed": {"readings": [subs], "table": "filed", "column": "accession", "value_column": "filed", **pair},
    "registrant": {"readings": [regs], "table": "filing", "column": "accession", "value_column": "cik", **pair}}})
doc = files.source(NAME)
filings = reading(OUT / "funds", {k: doc[k] for k in ("source", "execution", "read")},
                  {"input": capture, "context": context(OUT / "funds"), "lookups": lookups})
rows = tables(filings)["filing"]
facts = {"filings": len(rows), "filings_without_series": sum(r["series_id"] is None for r in rows),
         "filings_without_date": sum(r["filed"] is None for r in rows),
         "filings_without_registrant": sum(r["cik"] is None for r in rows),
         "filings_lei_blank": sum(r["lei"] is None for r in rows)}
series = combine(OUT / "reduce", files.load(FOLDER / "reduce.yaml"), {"filings": filings})
combined = combine(OUT / "combine", files.load(FOLDER / "combine.yaml"), {"series": series, "filings": filings})
fund = tables(combined)["fund"]
# A direct calculation of each series' latest filing, to compare.
direct = {}
for r in rows:
    if r["series_id"] and (r["series_id"] not in direct or (r["filed"], r["accession"]) > (direct[r["series_id"]]["filed"], direct[r["series_id"]]["accession"])):
        direct[r["series_id"]] = r
names = {}
for r in rows:
    if r["series_id"]:
        names.setdefault(r["series_id"], set()).add(r["name"])
facts.update(funds=len(fund), funds_several_filings=sum(r["filings"] > 1 for r in fund),
             latest_matches_direct=sum(direct[r["series_id"]]["accession"] == r["latest"]["accession"] for r in fund),
             name_changes=sum(len(v) > 1 for v in names.values()))
root = OUT / "mdm"
work = {"input": combined, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
        "keys": {"table": "fund", "dataset": CODE, "policy": "0" * 64, "consumer": "trial",
                 "batch_id": "nport-fund-trial", "as_of": "2026-10-16T00:00:00+00:00"}}
prepared = mdm_prepare.execute(work, store)
assert mdm_prepare.verify({**work, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
contract = doc["mdm"][CODE]["contract"]
outcome, filled, lei_holders = Counter(), Counter(), Counter()
for b in store.json(prepared)["batches"]:
    for rec in map(json.loads, (root / b["input"]["path"]).read_bytes().splitlines()):
        try:
            r = adapters.normalize(rec, source_code=CODE, contract=contract, publication={
                **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"], "member": b["input"]["path"]})
            outcome["accepted"] += 1
            for f, v in (r.get("fields") or {}).items():
                filled[f] += (v or {}).get("value") is not None
            for ns, v in (r.get("identifiers") or {}).items():
                filled["id:" + ns] += 1
                if ns == "lei":
                    lei_holders[v] += 1
            for ns in (r.get("cross_references") or {}):
                filled["xref:" + ns] += 1
        except adapters.UnsupportedRecord as x:
            outcome[x.reason] += 1
report = {"facts": facts, "contract": {"outcome": dict(outcome), "filled": dict(filled),
          "lei_on_two_funds": sum(c > 1 for c in lei_holders.values())}, "seconds": round(time.monotonic() - begun, 1)}
print(json.dumps(report, indent=1))
(OUT / "report.json").write_text(json.dumps(report, indent=1))
