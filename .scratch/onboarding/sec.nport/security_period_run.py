"""Ticket 100: the Securities chain to the reduction, with the quarter's period
in the holdings reading's context (security_test_run.py's stages 1-4, unchanged
otherwise). Usage: security_period_run.py ZIP OUT PERIOD"""
import hashlib, json, resource, sys, time
from collections import Counter
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare, source_readings
from edgar_warehouse.mdm.clean import adapters

ZIP, OUT, PERIOD = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
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

def context(root, values=None):
    root.mkdir(parents=True, exist_ok=True)
    return store.put(root.as_uri(), {"version": 1, "input": capture, "values": values or {}})

ids_doc = files.load(FOLDER / "identifiers.yaml")
identifiers = reading(OUT / "identifiers", {"source": NAME, **ids_doc}, {"input": capture, "context": context(OUT / "identifiers")})
stage("1 identifiers read")

doc = files.source(NAME)
lookups = store.put((OUT / "holdings").as_uri(), {"version": 2, "input": capture, "sets": {"isin": {
    "readings": [identifiers], "table": "isin", "column": "holding", "value_column": "isin",
    "max_input_bytes": 16 * 1024**3, "max_input_rows": 100_000_000}}})
holdings = reading(OUT / "holdings", {k: doc[k] for k in ("source", "execution", "read")},
                   {"input": capture, "context": context(OUT / "holdings", {"period": PERIOD}), "lookups": lookups})
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
stage("4 reduce")
print("reduced:", reduced)
