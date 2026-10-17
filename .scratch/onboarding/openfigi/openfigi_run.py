"""OpenFIGI through the configured chain (ticket 80): requests -> answers (streamed) -> per kind: reduce,
combine -> record -> mdm.prepare + Dataset Contracts. Counts only; reads the kept capture, asks
OpenFIGI nothing. Usage: openfigi_run.py CAPTURE OUT FILES_PER_KIND (0 = every file)."""
import hashlib
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
import json
import resource
import sys
import time
from collections import Counter
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read, source_readings

CAP, OUT, LIMIT = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
FOLDER = files.ROOT / "sources" / "openfigi"
KINDS = {"id_cusip": ("cusip", None, "openfigi.security.v1"), "id_isin": ("isin", None, "openfigi.security_isin.v1")}
store = Artifacts()
clock = time.monotonic()
report = {"stages": {}}


def stage(label):
    global clock
    now = time.monotonic()
    report["stages"][label] = round(now - clock, 1)
    print(f"{label}: {now - clock:.0f}s, peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.2f} GB",
          flush=True)
    clock = now


def ref(path):
    return {"uri": path.as_uri(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def read(root, body, artifacts, version):
    root.mkdir(parents=True, exist_ok=True)
    manifest = store.put(root.as_uri(), {"version": version, "contract": store.put(root.as_uri(), body),
                                         "artifacts": artifacts})
    task = {"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}
    out = source_read.execute(task, store)
    assert source_read.verify({**task, "candidate": out}, store) == ({"source.output": True}, [])
    return out


def combine(root, body, readings):
    root.mkdir(parents=True, exist_ok=True)
    manifest = store.put(root.as_uri(), {"version": 1, "contract": store.put(root.as_uri(), body), "readings": readings})
    task = {"input": manifest, "output": (root / "output/combined.json").as_uri(), "checks": [source_combine.CHECK],
            "keys": {}}
    out = source_combine.execute(task, store)
    assert source_combine.verify({**task, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    return out


def context(root, path, values):
    root.mkdir(parents=True, exist_ok=True)
    return store.put(root.as_uri(), {"version": 1, "input": ref(path), "values": values})


answers_body = {k: v for k, v in files.source("openfigi").items() if k in ("source", "execution", "read")}
doc = files.source("openfigi")
report["contracts"] = {}


def answers_reading(job):
    """One answers reading (one of a kind's 8), with each file's pair set from its own request file:
    one built from the whole group is re-read for every file (quadratic, found 2026-10-17)."""
    kind, word, g, group = job
    root = OUT / word / f"answers_{g}"
    arts = []
    for n in group:
        batch, request, path = f"{kind}/{n.split('.')[0]}", CAP / kind / n.replace(".json", ".request.json"), CAP / kind / n
        asked = read(root / "requests" / n, files.load(FOLDER / "requests.yaml"),
                     [{"input": ref(request), "context": context(root / "ctx-req" / n, request, {"batch": batch})}], 2)
        lookups = store.put((root / "lk").as_uri(), {"version": 2, "input": ref(path), "sets": {"asked": {
            "readings": [asked], "table": "asked", "column": "key", "value_column": "id",
            "max_input_bytes": 1 << 20, "max_input_rows": 1000}}})
        arts.append({"input": ref(path), "lookups": lookups, "context": context(
            root / "ctx-ans" / n, path, {"batch": batch, "id_type": word})})
    return f"answers_{g}", read(root / "answers", answers_body, arts, 3)


# All 16 readings at once, one process each (8 cores): each reading is independent, with its own
# files under OUT; the verifier still replays every one.
jobs, names_of = [], {}
for kind, (word, _, _) in KINDS.items():
    names = sorted(p.name.replace(".request", "") for p in (CAP / kind).glob("*.request.json"))
    names_of[kind] = names = names[:LIMIT] if LIMIT else names
    jobs += [(kind, word, g, names[g - 1::8]) for g in range(1, 9)]
# fork: the script's top level must not run again in each worker (macOS defaults to spawn).
with ProcessPoolExecutor(max_workers=os.cpu_count(), mp_context=multiprocessing.get_context("fork")) as pool:
    done = list(pool.map(answers_reading, jobs))
by_kind = {word: dict(done[i * 8:(i + 1) * 8]) for i, (_, (word, _, _)) in enumerate(KINDS.items())}
stage(f"read {sum(len(v) for v in names_of.values())} files, 16 readings in parallel")
for kind, (word, _, code) in KINDS.items():
    names, readings = names_of[kind], by_kind[word]
    counts = combine(OUT / word / "reduce", files.load(FOLDER / "reduce.yaml"), readings)
    combined = combine(OUT / word / "combine", files.load(FOLDER / "combine.yaml"), {"counts": counts})
    stage(f"{word}: reduce, combine")
    index = store.json(combined)
    root = OUT / word / "record"
    # A large output is in pieces (version 2); a small one holds its tables inline, given here as one piece.
    pieces = ([p["receipt"] for a in index["artifacts"] for p in a["partitions"]] if index.get("version") == 2
              else [store.put(root.as_uri(), {"tables": a["tables"]}) for a in index["artifacts"]])
    records = read(root, files.load(FOLDER / "record.yaml"),
                   [{"input": p, "context": store.put(root.as_uri(), {"version": 1, "input": p, "values": {}})}
                    for p in pieces], 2)
    root = OUT / word / "mdm"
    task = {"input": records, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
            "keys": {"table": "security", "record_column": "record", "dataset": code, "policy": "0" * 64,
                     "consumer": "trial", "batch_id": f"openfigi-{word}-trial", "as_of": "2026-10-15T00:00:00+00:00"}}
    prepared = mdm_prepare.execute(task, store)
    assert mdm_prepare.verify({**task, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    contract = doc["mdm"][code]["contract"]
    # The cross-references each identifier should get, counted directly from the files by position.
    expected = {}
    for n in names:
        for job, answer in zip(json.loads((CAP / kind / n.replace(".json", ".request.json")).read_text()),
                               json.loads((CAP / kind / n).read_text())):
            listings = answer.get("data") or []
            pairs = {(x["figi"], x["ticker"]) for x in listings}
            classes = {x["shareClassFIGI"] for x in listings if x.get("shareClassFIGI")}
            us = {(x["figi"], x["ticker"]) for x in listings if x.get("exchCode") == "US" and x["figi"] == x.get("compositeFIGI")}
            want = {}
            if len(classes) == 1:
                want["share_class_figi"] = next(iter(classes))
            if len(us) == 1:
                want["composite_figi"], want["openfigi_ticker"] = next(iter(us))
            if len(pairs) == 1:
                want["figi"] = next(iter(pairs))[0]
                want.setdefault("openfigi_ticker", next(iter(pairs))[1])
            expected[job["idValue"].upper()] = want if listings else None
    differences = 0
    outcome, filled = Counter(), Counter()
    for b in store.json(prepared)["batches"]:
        for rec in map(json.loads, (root / b["input"]["path"]).read_bytes().splitlines()):
            try:
                r = adapters.normalize(rec, source_code=code, contract=contract, publication={
                    **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                    "member": b["input"]["path"]})
                outcome["accepted"] += 1
                differences += (r.get("cross_references") or {}) != expected.pop(rec["id"])
                for ns in r.get("identifiers") or {}:
                    filled["id:" + ns] += 1
                for ns in r.get("cross_references") or {}:
                    filled["xref:" + ns] += 1
            except adapters.UnsupportedRecord as refused:
                outcome[refused.reason] += 1
                differences += refused.reason == "not_found_by_openfigi" and expected.pop(rec["id"]) is not None
    report["contracts"][code] = {"files": len(names), "outcome": dict(outcome), "filled": dict(filled),
                                 "differences_from_direct_count": differences, "identifiers_not_prepared": len(expected)}
    stage(f"{word}: record, prepare, contract")
print(json.dumps(report, indent=1))
(OUT / "report.json").write_text(json.dumps(report, indent=1))
