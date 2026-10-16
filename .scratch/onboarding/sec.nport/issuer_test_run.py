"""ISSUED_BY by the issuer's LEI (ticket 22): the one test run, counts only.

issuers.yaml (read FUND_REPORTED_HOLDING once, for the issuer table only) ->
issuer-reduce.yaml -> combine.yaml (with part 1's kept reduction and OpenFIGI
attachment) -> mdm.prepare -> the Dataset Contract. A direct count from the
same file checks which CUSIPs get a link.
Usage: issuer_test_run.py ZIP TNPORT FIGI_ATTACH OUT"""
import csv, hashlib, io, json, os, re, resource, sys, time, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_combine, mdm_prepare
from edgar_warehouse.mdm.clean import adapters

ZIP, TN, FIGI, OUT = (Path(a) for a in sys.argv[1:5])
NAME, CODE = "sec.nport.security", "sec.nport.security.v1"
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
    c = store.put(root.as_uri(), body)
    m = store.put(root.as_uri(), {"version": 1, "contract": c, "readings": readings})
    work = {"input": m, "output": (root / "output/combined.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
    out = source_combine.execute(work, store)
    assert source_combine.verify({**work, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    return out

capture = {"uri": ZIP.as_uri(), "sha256": sha(ZIP)}
root = OUT / "issuers"; root.mkdir(parents=True, exist_ok=True)
body = {"source": NAME, **files.load(FOLDER / "issuers.yaml")}
manifest = store.put(root.as_uri(), {"version": 2, "contract": store.put(root.as_uri(), body), "artifacts": [
    {"input": capture, "context": store.put(root.as_uri(), {"version": 1, "input": capture, "values": {}})}]})
issuers = source_read.execute({"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}, store)
stage("issuers reading")
reduced = combine(OUT / "issuer-reduce", files.load(FOLDER / "issuer-reduce.yaml"), {"issuers": issuers})
stage("issuer-reduce")
combined = combine(OUT / "combine", files.load(FOLDER / "combine.yaml"), {
    "securities": ref(TN / "reduce/output/combined.json"),
    "attached": ref(FIGI / "figi-attach/output/combined.json"), "issuers": reduced})
stage("combine")
root = OUT / "mdm-security"
work = {"input": combined, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
        "keys": {"table": "security", "dataset": CODE, "policy": "0" * 64, "consumer": "trial",
                 "batch_id": "nport-security-issuer-trial", "as_of": "2026-10-16T00:00:00+00:00",
                 **({"effective_column": "period"} if os.environ.get("PERIOD") else {})}}
prepared = mdm_prepare.execute(work, store)
assert mdm_prepare.verify({**work, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
contract = files.source(NAME)["mdm"][CODE]["contract"]
outcome, linked = Counter(), {}
for b in store.json(prepared)["batches"]:
    for rec in map(json.loads, (root / b["input"]["path"]).read_bytes().splitlines()):
        try:
            r = adapters.normalize(rec, source_code=CODE, contract=contract, publication={
                **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                "member": b["input"]["path"]})
            outcome["accepted"] += 1
            links = [l for l in r.get("relationships") or [] if l.get("type") == "ISSUED_BY"]
            if links:
                linked[rec["cusip"]] = len(links)
        except adapters.UnsupportedRecord as x:
            outcome[x.reason] += 1
stage("prepare + contract")
# Direct count: CUSIPs whose holdings state exactly one LEI-shaped issuer LEI.
LEI = re.compile(r"[A-Z0-9]{18}[0-9]{2}")
by_cusip = defaultdict(set)
csv.field_size_limit(10**8)
with zipfile.ZipFile(ZIP) as z:
    for row in csv.DictReader(io.TextIOWrapper(z.open("FUND_REPORTED_HOLDING.tsv"), "utf-8"), delimiter="\t"):
        c = (row["ISSUER_CUSIP"] or "").strip().upper()
        l = (row["ISSUER_LEI"] or "").strip().upper()
        if c and c not in ("000000000", "999999999") and LEI.fullmatch(l) and set(l) != {"0"}:
            by_cusip[c].add(l)
once = {c for c, ls in by_cusip.items() if len(ls) == 1}
stage("direct count")
report = {"contract": dict(outcome), "securities_with_issued_by": len(linked),
          "links_per_security": dict(Counter(linked.values())),
          "direct": {"cusips_with_an_issuer_lei": len(by_cusip), "cusips_with_one": len(once),
                     "cusips_with_several": len(by_cusip) - len(once)},
          "linked_and_direct_agree": sum(1 for c in linked if c in once), "linked_not_direct": sum(1 for c in linked if c not in once),
          "direct_not_linked_among_accepted": None, "seconds": times}
print(json.dumps(report, indent=1))
(OUT / "report.json").write_text(json.dumps(report, indent=1))
