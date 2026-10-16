"""ISSUED_BY for ISIN-only Securities (ticket 102): the one count, counts only.

issuers.yaml (with the `isin` pair set from the kept identifiers reading) ->
issuer-reduce.yaml -> combine.yaml (with the kept period reduction and OpenFIGI
attachment) -> mdm.prepare (table security_isin, dated by `period`) -> the ISIN
Dataset Contract. A direct count from the same file checks which ISINs get a
link. Usage: isin_issuer_run.py ZIP TNPORT FIGI_ATTACH OUT"""
import csv, hashlib, io, json, re, resource, sys, time, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
from edgar_warehouse.mdm.clean import adapters

ZIP, TN, FIGI, OUT = (Path(a) for a in sys.argv[1:5])
NAME, CODE = "sec.nport.security", "sec.nport.security_isin.v1"
FOLDER = Path("rules/sources") / NAME
store = Artifacts(); clock = time.monotonic(); times = {}
def stage(label):
    global clock
    now = time.monotonic(); times[label] = round(now - clock)
    print(f"{label}: {now - clock:.0f}s, peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.2f} GB", flush=True)
    clock = now
def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
def ref(path):
    return {"uri": path.as_uri(), "sha256": sha(path)}
def combine(root, body, readings):
    root.mkdir(parents=True, exist_ok=True)
    m = store.put(root.as_uri(), {"version": 1, "contract": store.put(root.as_uri(), body), "readings": readings})
    work = {"input": m, "output": (root / "output/combined.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
    out = source_combine.execute(work, store)
    assert source_combine.verify({**work, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    return out

capture = {"uri": ZIP.as_uri(), "sha256": sha(ZIP)}
root = OUT / "issuers"; root.mkdir(parents=True, exist_ok=True)
lookups = store.put(root.as_uri(), {"version": 2, "input": capture, "sets": {"isin": {
    "readings": [ref(TN / "identifiers/reading.json")], "table": "isin", "column": "holding", "value_column": "isin",
    "max_input_bytes": 16 * 1024**3, "max_input_rows": 100_000_000}}})
body = {"source": NAME, **files.load(FOLDER / "issuers.yaml")}
manifest = store.put(root.as_uri(), {"version": 3, "contract": store.put(root.as_uri(), body), "artifacts": [
    {"input": capture, "context": store.put(root.as_uri(), {"version": 1, "input": capture, "values": {}}),
     "lookups": lookups}]})
issuers = source_read.execute({"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}, store)
stage("issuers reading")
reduced = combine(OUT / "issuer-reduce", files.load(FOLDER / "issuer-reduce.yaml"), {"issuers": issuers})
stage("issuer-reduce")
combined = combine(OUT / "combine", files.load(FOLDER / "combine.yaml"), {
    "securities": ref(TN / "reduce/output/combined.json"),
    "attached": ref(FIGI / "figi-attach/output/combined.json"), "issuers": reduced})
stage("combine")
root = OUT / "mdm-security-isin"
work = {"input": combined, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
        "keys": {"table": "security_isin", "dataset": CODE, "policy": "0" * 64, "consumer": "trial",
                 "batch_id": "nport-security-isin-issuer-trial", "as_of": "2026-10-16T00:00:00+00:00",
                 "effective_column": "period"}}
prepared = mdm_prepare.execute(work, store)
assert mdm_prepare.verify({**work, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
contract = files.source(NAME)["mdm"][CODE]["contract"]
outcome, linked, dated = Counter(), {}, Counter()
for b in store.json(prepared)["batches"]:
    dated[b["input"]["publication"].get("effective_at")] += 1
    for rec in map(json.loads, (root / b["input"]["path"]).read_bytes().splitlines()):
        try:
            r = adapters.normalize(rec, source_code=CODE, contract=contract, publication={
                **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                "member": b["input"]["path"]})
            outcome["accepted"] += 1
            links = [l for l in r.get("relationships") or [] if l.get("type") == "ISSUED_BY"]
            if links:
                linked[rec["isin"]] = len(links)
        except adapters.UnsupportedRecord as x:
            outcome[x.reason] += 1
stage("prepare + contract")
# Direct count: ISINs of holdings with no usable CUSIP whose holdings state exactly
# one LEI-shaped issuer LEI; a holding's ISIN is its one ISIN-shaped identifier.
LEI = re.compile(r"[A-Z0-9]{18}[0-9]{2}")
ISIN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")
csv.field_size_limit(10**8)
isins_of = defaultdict(set)
with zipfile.ZipFile(ZIP) as z:
    for row in csv.DictReader(io.TextIOWrapper(z.open("IDENTIFIERS.tsv"), "utf-8"), delimiter="\t"):
        i = (row["IDENTIFIER_ISIN"] or "").upper()
        if ISIN.fullmatch(i):
            isins_of[row["HOLDING_ID"]].add(i)
    by_isin = defaultdict(set)
    for row in csv.DictReader(io.TextIOWrapper(z.open("FUND_REPORTED_HOLDING.tsv"), "utf-8"), delimiter="\t"):
        c = (row["ISSUER_CUSIP"] or "").upper()
        l = (row["ISSUER_LEI"] or "").upper()
        held = isins_of.get(row["HOLDING_ID"], ())
        if (not c or c in ("000000000", "999999999")) and len(held) == 1 and LEI.fullmatch(l) and set(l) != {"0"}:
            by_isin[next(iter(held))].add(l)
once = {i for i, ls in by_isin.items() if len(ls) == 1}
stage("direct count")
report = {"contract": dict(outcome), "batches_by_effective_at": dict(dated),
          "securities_with_issued_by": len(linked), "links_per_security": dict(Counter(linked.values())),
          "direct": {"isins_with_an_issuer_lei": len(by_isin), "isins_with_one": len(once),
                     "isins_with_several": len(by_isin) - len(once)},
          "linked_and_direct_agree": sum(1 for i in linked if i in once),
          "linked_not_direct": sum(1 for i in linked if i not in once),
          "direct_not_linked": sum(1 for i in once if i not in linked), "seconds": times}
print(json.dumps(report, indent=1))
(OUT / "report.json").write_text(json.dumps(report, indent=1))
