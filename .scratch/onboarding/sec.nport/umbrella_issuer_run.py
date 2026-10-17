"""ISSUED_BY with each filed LEI counted as its umbrella trust's (ticket 23): the one count.

issuers.yaml (with the `isin` pair set from the kept identifiers reading and
the `umbrella` pair set from gleif/subfund-pairs.yaml's reading) ->
issuer-reduce.yaml -> combine.yaml (with the kept period reduction and OpenFIGI
attachment) -> mdm.prepare (table security) -> the CUSIP Dataset Contract. A
direct count from the same files checks it. Counts only.
Usage: umbrella_issuer_run.py ZIP TNPORT FIGI_ATTACH PAIRS_READING GLEIF_RR_ZIP OUT"""
import csv, hashlib, io, json, re, sys, time, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read

ZIP, TN, FIGI, PAIRS, RR, OUT = (Path(a) for a in sys.argv[1:7])
NAME, CODE, GLEIF = "sec.nport.security", "sec.nport.security.v1", "gleif.level1.v1"
FOLDER = Path("rules/sources") / NAME
store = Artifacts(); start = time.monotonic()
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
lookups = store.put(root.as_uri(), {"version": 2, "input": capture, "sets": {
    "isin": {"readings": [ref(TN / "identifiers/reading.json")], "table": "isin", "column": "holding",
             "value_column": "isin", "max_input_bytes": 16 * 1024**3, "max_input_rows": 100_000_000},
    "umbrella": {"readings": [ref(PAIRS)], "table": "subfund", "column": "fund", "value_column": "umbrella",
                 "max_input_bytes": 16 * 1024**3, "max_input_rows": 100_000_000}}})
body = {"source": NAME, **files.load(FOLDER / "issuers.yaml")}
manifest = store.put(root.as_uri(), {"version": 3, "contract": store.put(root.as_uri(), body), "artifacts": [
    {"input": capture, "context": store.put(root.as_uri(), {"version": 1, "input": capture, "values": {}}),
     "lookups": lookups}]})
issuers = source_read.execute({"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}, store)
reduced = combine(OUT / "issuer-reduce", files.load(FOLDER / "issuer-reduce.yaml"), {"issuers": issuers})
combined = combine(OUT / "combine", files.load(FOLDER / "combine.yaml"), {
    "securities": ref(TN / "reduce/output/combined.json"),
    "attached": ref(FIGI / "figi-attach/output/combined.json"), "issuers": reduced})
root = OUT / "mdm-security"
work = {"input": combined, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"],
        "keys": {"table": "security", "dataset": CODE, "policy": "0" * 64, "consumer": "trial",
                 "batch_id": "nport-umbrella-trial", "as_of": "2026-10-17T00:00:00+00:00", "effective_column": "period"}}
prepared = mdm_prepare.execute(work, store)
contract = files.source(NAME)["mdm"][CODE]["contract"]
linked = {}
for b in store.json(prepared)["batches"]:
    for rec in map(json.loads, (root / b["input"]["path"]).read_bytes().splitlines()):
        try:
            r = adapters.normalize(rec, source_code=CODE, contract=contract, publication={
                **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                "member": b["input"]["path"]})
        except adapters.UnsupportedRecord:
            continue
        links = [l["target_subject"] for l in r.get("relationships") or [] if l["type"] == "ISSUED_BY"]
        if links:
            linked[rec["cusip"]] = links[0]
chain_seconds = round(time.monotonic() - start)
# Direct: each filed LEI-shaped LEI mapped to its active umbrella; CUSIPs left with one.
umbrella = {}
with zipfile.ZipFile(RR) as z:
    data = z.open(z.namelist()[0]).read().decode("utf-8")
for s, e, t, st in re.findall(r'"StartNode"\s*:\s*\{\s*"NodeID"\s*:\s*\{\s*"\$"\s*:\s*"(\w{20})".*?"EndNode"\s*:\s*\{\s*"NodeID"\s*:\s*\{\s*"\$"\s*:\s*"(\w{20})".*?"RelationshipType"\s*:\s*\{\s*"\$"\s*:\s*"([A-Z_-]+)".*?"RelationshipStatus"\s*:\s*\{\s*"\$"\s*:\s*"(\w+)"', data, re.S):
    if t == "IS_SUBFUND_OF" and st == "ACTIVE":
        umbrella[s.upper()] = e.upper()
del data
LEI = re.compile(r"[A-Z0-9]{18}[0-9]{2}")
by, filed = defaultdict(set), defaultdict(set)
csv.field_size_limit(10**8)
with zipfile.ZipFile(ZIP) as z:
    for row in csv.DictReader(io.TextIOWrapper(z.open("FUND_REPORTED_HOLDING.tsv"), "utf-8"), delimiter="\t"):
        c = (row["ISSUER_CUSIP"] or "").upper(); l = (row["ISSUER_LEI"] or "").upper()
        if c and c not in ("000000000", "999999999") and LEI.fullmatch(l) and set(l) != {"0"}:
            by[c].add(umbrella.get(l, l)); filed[c].add(l)
once = {c: next(iter(v)) for c, v in by.items() if len(v) == 1}
from edgar_warehouse.mdm.clean.evidence import subject_key
report = {"securities_with_issued_by": len(linked),
          "direct_cusips_with_one_issuer": len(once),
          "linked_and_direct_agree": sum(1 for c, t in linked.items() if c in once and t == subject_key(GLEIF, once[c])),
          "linked_not_direct": sum(1 for c in linked if c not in once),
          "direct_not_linked": sum(1 for c in once if c not in linked),
          "newly_one_issuer": sum(1 for c in once if len(filed[c]) > 1),
          "moved_to_an_umbrella": sum(1 for c in once if len(filed[c]) == 1 and once[c] not in filed[c]),
          "still_several": sum(1 for v in by.values() if len(v) > 1),
          "seconds": {"chain": chain_seconds, "all": round(time.monotonic() - start)}}
print(json.dumps(report, indent=1))
(OUT / "report.json").write_text(json.dumps(report, indent=1))
