"""The N-PORT Security test run (ticket 79, part 1): every stage once, counts only.

identifiers reading -> derived pair set -> holdings reading -> reduce ->
combine-pairs -> combine -> mdm.prepare (two contracts) -> Dataset Contracts.
"""
import hashlib, json, resource, sys, time
from collections import Counter
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare, source_readings
from edgar_warehouse.mdm.clean import adapters

ZIP, OUT = Path(sys.argv[1]), Path(sys.argv[2])
NAME = "sec.nport.security"
FOLDER = Path("rules/sources") / NAME
store = Artifacts()
clock = time.monotonic()
def stage(label):
    global clock
    now = time.monotonic()
    print(f"{label}: {now - clock:.0f}s, peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.2f} GB", flush=True)
    clock = now

digest = hashlib.sha256()
with ZIP.open("rb") as f:
    for block in iter(lambda: f.read(1 << 20), b""):
        digest.update(block)
capture = {"uri": ZIP.as_uri(), "sha256": digest.hexdigest()}

def reading(root, body, artifact):
    root.mkdir(parents=True, exist_ok=True)
    contract = store.put(root.as_uri(), body)
    manifest = store.put(root.as_uri(), {"version": 3 if "lookups" in artifact else 2, "contract": contract,
                                         "artifacts": [artifact]})
    return source_read.execute({"input": manifest, "output": (root / "reading.json").as_uri(),
                                "checks": ["source.output"]}, store)

def context(root):
    root.mkdir(parents=True, exist_ok=True)
    return store.put(root.as_uri(), {"version": 1, "input": capture, "values": {}})

ids_doc = files.load(FOLDER / "identifiers.yaml")
identifiers = reading(OUT / "identifiers", {"source": NAME, **ids_doc}, {"input": capture, "context": context(OUT / "identifiers")})
stage("1 identifiers read")

doc = files.source(NAME)
lookups = store.put((OUT / "holdings").as_uri(), {"version": 2, "input": capture, "sets": {"isin": {
    "readings": [identifiers], "table": "isin", "column": "holding", "value_column": "isin",
    "max_input_bytes": 16 * 1024**3, "max_input_rows": 100_000_000}}})
holdings = reading(OUT / "holdings", {k: doc[k] for k in ("source", "execution", "read")},
                   {"input": capture, "context": context(OUT / "holdings"), "lookups": lookups})
stage("2-3 pair set and holdings read")

def combine(root, body, readings):
    root.mkdir(parents=True, exist_ok=True)
    c = store.put(root.as_uri(), body)
    m = store.put(root.as_uri(), {"version": 1, "contract": c, "readings": readings})
    work = {"input": m, "output": (root / "output/combined.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
    out = source_combine.execute(work, store)
    assert source_combine.verify({**work, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    return out

def tables(ref):
    return source_readings.load(ref, store, max_bytes=16 * 1024**3, max_rows=10**8, allow_lookup_receipts=True)[0]["artifacts"][0]["tables"]

reduced = combine(OUT / "reduce", files.load(FOLDER / "reduce.yaml"), {"holdings": holdings})
red = tables(reduced)
print("reduced rows:", {k: len(v) for k, v in red.items()}, flush=True)
facts = {
    "holdings_with_usable_cusip": sum(r["holdings"] for r in red["cusips"]),
    "holdings_isin_only": sum(r["holdings"] for r in red["isins"]),
    "cusips_with_several_isins": sum(r["isins"] > 1 for r in red["cusip_isins"]),
    "isins_with_several_cusips": sum(r["cusips"] > 1 for r in red["isin_cusips"]),
}
del red
stage("4a reduce")
pairs = combine(OUT / "pairs", files.load(FOLDER / "combine-pairs.yaml"), {"securities": reduced})
rows = tables(pairs)["pairs"]
facts.update(pairs=len(rows), pairs_one_to_one=sum(r["cusip_isins"] == 1 and r["isin_cusips"] == 1 for r in rows),
             pairs_isin_embeds_cusip=sum(r["isin"][2:11] == r["cusip"] for r in rows))
del rows
combined = combine(OUT / "combine", files.load(FOLDER / "combine.yaml"), {"securities": reduced, "pairs": pairs})
stage("4b combines")

report = {"facts": facts, "contracts": {}}
for table, code in (("security", "sec.nport.security.v1"), ("security_isin", "sec.nport.security_isin.v1")):
    root = OUT / f"mdm-{table}"
    work = {"input": combined, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
            "keys": {"table": table, "dataset": code, "policy": "0" * 64, "consumer": "trial",
                     "batch_id": f"nport-{table}-trial", "as_of": "2026-10-15T00:00:00+00:00"}}
    prepared = mdm_prepare.execute(work, store)
    assert mdm_prepare.verify({**work, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    contract = doc["mdm"][code]["contract"]
    outcome, filled = Counter(), Counter()
    for b in store.json(prepared)["batches"]:
        for rec in map(json.loads, (root / b["input"]["path"]).read_bytes().splitlines()):
            try:
                r = adapters.normalize(rec, source_code=code, contract=contract, publication={
                    **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                    "member": b["input"]["path"]})
                outcome["accepted"] += 1
                for f, v in (r.get("fields") or {}).items():
                    filled[f] += v is not None
                for ns in (r.get("identifiers") or {}):
                    filled["id:" + ns] += 1
            except adapters.UnsupportedRecord as x:
                outcome[x.reason] += 1
    report["contracts"][code] = {"outcome": dict(outcome), "filled": dict(filled)}
    stage(f"5 {code}")
print(json.dumps(report, indent=1))
(OUT / "report.json").write_text(json.dumps(report, indent=1))
