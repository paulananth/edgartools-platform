"""N-PORT Security with OpenFIGI (ticket 80): the stages after the reduction, run once.
figi-found x2 -> figi-pairs -> figi-agree (reading over its pieces) -> figi-offers -> figi-attach
-> combine.yaml -> mdm.prepare + Dataset Contracts. Counts only.
Usage: figi_attach_run.py READ_LOG TNPORT OUT"""
import hashlib, json, resource, sys, time
from collections import Counter
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare, source_readings
from edgar_warehouse.mdm.clean import adapters

LOG, TN, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
NAME = "sec.nport.security"; FOLDER = Path("rules/sources") / NAME
store = Artifacts(); clock = time.monotonic()
def stage(label):
    global clock
    now = time.monotonic()
    print(f"{label}: {now - clock:.0f}s, peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.2f} GB", flush=True)
    clock = now
def ref(path):
    return {"uri": path.as_uri(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
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
    for a in source_readings.load(r, store, max_bytes=16 * 1024**3, max_rows=10**8, allow_lookup_receipts=True)[0]["artifacts"]:
        for k, v in a["tables"].items():
            out.setdefault(k, []).extend(v)
    return out

answers = {"id_cusip": [], "id_isin": []}
for line in LOG.read_text().splitlines():
    d = json.loads(line)
    answers["id_cusip" if "id_cusip" in d["answers"]["uri"] else "id_isin"].append(d["answers"])
assert [len(v) for v in answers.values()] == [8, 8]
found = {k: combine(OUT / f"found-{k}", files.load(FOLDER / "figi-found.yaml"),
                    {f"answers_{i + 1}": r for i, r in enumerate(v)}) for k, v in answers.items()}
stage("figi-found x2")
pairs = combine(OUT / "figi-pairs", files.load(FOLDER / "figi-pairs.yaml"),
                {"pairs": ref(TN / "pairs/output/combined.json"), "cusips": found["id_cusip"], "isins": found["id_isin"]})
stage("figi-pairs")
index = store.json(pairs)
pieces = [p["receipt"] for a in index["artifacts"] for p in a["partitions"]] if index.get("version") == 2 else [pairs]
root = OUT / "figi-agree"; root.mkdir(parents=True, exist_ok=True)
arts = [{"input": p, "context": store.put(root.as_uri(), {"version": 1, "input": p, "values": {}})} for p in pieces]
contract = store.put(root.as_uri(), files.load(FOLDER / "figi-agree.yaml"))
manifest = store.put(root.as_uri(), {"version": 2, "contract": contract, "artifacts": arts})
agreed = source_read.execute({"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}, store)
stage(f"figi-agree over {len(pieces)} pieces")
offers = combine(OUT / "figi-offers", files.load(FOLDER / "figi-offers.yaml"), {"agreed": agreed})
attach = combine(OUT / "figi-attach", files.load(FOLDER / "figi-attach.yaml"), {"agreed": agreed, "offers": offers})
stage("figi-offers + figi-attach")
rows = tables(attach)["attached"]
facts = {"agreed_pairs": len(rows),
         "attached": sum(r["cusip_offers"] == 1 and r["isin_offers"] == 1 for r in rows),
         "cusips_offered_several_isins": len({r["cusip"] for r in rows if r["cusip_offers"] > 1}),
         "isins_offered_several_cusips": len({r["isin"] for r in rows if r["isin_offers"] > 1})}
del rows
combined = combine(OUT / "combine", files.load(FOLDER / "combine.yaml"),
                   {"securities": ref(TN / "reduce/output/combined.json"), "attached": attach})
stage("combine")
report = {"facts": facts, "contracts": {}}
doc = files.source(NAME)
for table, code in (("security", "sec.nport.security.v1"), ("security_isin", "sec.nport.security_isin.v1")):
    root = OUT / f"mdm-{table}"
    work = {"input": combined, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
            "keys": {"table": table, "dataset": code, "policy": "0" * 64, "consumer": "trial",
                     "batch_id": f"nport-{table}-figi-trial", "as_of": "2026-10-15T00:00:00+00:00"}}
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
    stage(f"prepare + contract {code}")
print(json.dumps(report, indent=1))
(OUT / "report.json").write_text(json.dumps(report, indent=1))
