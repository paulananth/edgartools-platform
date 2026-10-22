"""Ticket 130 dry run on the local captured files: the committed 13F and N-PORT
chains to their Dataset Contracts, share_class counted and compared with
oracle.py's letters per CUSIP. Counts only; no database, no provider request.

    THIRTEENF_UNITS=~/edgar-local-tmp/t13f NPORT_ZIP=<2026q2_nport.zip> OUT=<folder> \
      uv run --no-sync python .scratch/onboarding/security-share-class/dry_run.py

N-PORT runs without OpenFIGI's answers and without issuer facts (they give the
ISSUED_BY link, never the class), so no ISIN-only holding folds into a
CUSIP here (the fold is covered by tests/integration/test_security_share_class.py).
"""
import csv, hashlib, io, json, os, re, resource, sys, time, zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.getcwd())
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import adapters, quality
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read, source_readings

OUT = Path(os.environ["OUT"]).expanduser()
store = Artifacts()
clock = time.monotonic()


def stage(label):
    global clock
    now = time.monotonic()
    print(f"{label}: {now - clock:.0f}s, peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.2f} GB", flush=True)
    clock = now


def letter(t):
    s = t.strip().upper(); s = re.sub('[^A-Z]+', ' ', s); s = ' ' + s + ' '
    s = re.sub('^.* (CL|CLASS|CLS) ', '#', s); s = re.sub('^[^#].*$', '', s); s = re.sub(' .*$', '', s)
    s = re.sub('^#[A-Z][A-Z]+$', '', s); return s.replace('#', '')


def ref(path: Path) -> dict:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return {"uri": path.as_uri(), "sha256": h.hexdigest()}


def context(root, raw, values=None):
    root.mkdir(parents=True, exist_ok=True)
    return store.put(root.as_uri(), {"version": 1, "input": raw, "values": values or {}})


def reading(root, body, artifacts, version=2):
    root.mkdir(parents=True, exist_ok=True)
    contract = store.put(root.as_uri(), body)
    manifest = store.put(root.as_uri(), {"version": version, "contract": contract, "artifacts": artifacts})
    return source_read.execute({"input": manifest, "output": (root / "reading.json").as_uri(),
                                "checks": ["source.output"]}, store)


def combine(root, contract, readings):
    root.mkdir(parents=True, exist_ok=True)
    c = store.put(root.as_uri(), files.load(contract))
    m = store.put(root.as_uri(), {"version": 1, "contract": c, "readings": readings})
    work = {"input": m, "output": (root / "output/combined.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
    out = source_combine.execute(work, store)
    assert source_combine.verify({**work, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    return out


def records(root, prepared_input, keys, code, contract):
    work = {"input": prepared_input, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"], "keys": keys}
    prepared = mdm_prepare.execute(work, store)
    assert mdm_prepare.verify({**work, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    out, refused = [], Counter()
    for b in store.json(prepared)["batches"]:
        for n, rec in enumerate(map(json.loads, (root / b["input"]["path"]).read_bytes().splitlines())):
            try:
                out.append(adapters.normalize(rec, source_code=code, contract=contract, publication={
                    **b["input"]["publication"], "semantics": "patch", "artifact_sha256": b["input"]["sha256"],
                    "member": b["input"]["path"], "record_locator": f"{b['input']['sha256']}:{n}"}))
            except adapters.UnsupportedRecord as x:
                refused[x.reason] += 1
    return out, refused


def compare(found, expected_letters, conflicts):
    """found: record key -> (letter or None, flagged)."""
    both = sum(1 for v, f in found.values() if v and f)
    return {
        "records": len(found),
        "share_class_filled": sum(1 for v, _ in found.values() if v),
        "flagged": sum(1 for _, f in found.values() if f),
        "filled_and_flagged": both,
        "oracle_lettered": len(expected_letters), "oracle_two_letters": len(conflicts),
        "filled_differs_from_oracle": sum(1 for k, (v, _) in found.items() if v != expected_letters.get(k)),
        "flagged_not_oracle_conflict": sum(1 for k, (_, f) in found.items() if f and k not in conflicts),
    }


def found_of(recs):
    return {r["provenance"]["record_key"]: ((r["fields"].get("share_class") or {}).get("value"),
            "share_class_one_letter" in ((r["provenance"].get("quality") or {}).get("flags") or [])) for r in recs}


report = {}

# ---- 13F
if not os.environ.get("SKIP_13F"):
    name = "sec.thirteenf.information_table"; code = f"{name}.security.v1"; folder = files.ROOT / "sources" / name
    doc = files.source(name)
    body = {k: doc[k] for k in ("source", "execution", "read")}
    units, oracle = {}, defaultdict(set)
    cu = re.compile(r'<(?:\w+:)?cusip>\s*([^<]*?)\s*</', re.I); ti = re.compile(r'<(?:\w+:)?titleOfClass>\s*([^<]*?)\s*</', re.I)
    it = re.compile(r'<(?:\w+:)?infoTable>(.*?)</(?:\w+:)?infoTable>', re.S | re.I)
    dirs = sorted(Path(os.environ["THIRTEENF_UNITS"]).expanduser().glob("unit*"))
    for n, d in enumerate(dirs, 1):
        paths = sorted(p for p in d.iterdir() if p.is_file() and not p.name.endswith(".json"))
        arts = []
        for p in paths:
            raw = ref(p)
            arts.append({"input": raw, "context": context(OUT / f"13f-ctx/{n}", raw)})
            x = p.read_text(errors="ignore")
            for b in it.findall(x):
                c, t = cu.search(b), ti.search(b)
                if c and t and t.group(1) and letter(t.group(1)):
                    oracle[c.group(1).upper()].add(letter(t.group(1)))
        units[f"units_{n}"] = reading(OUT / f"13f-read-{n}", body, arts)
        stage(f"13F unit {n} read ({len(arts)} files)")
    empty_xml = OUT / "13f-empty.xml"; empty_xml.write_text("<informationTable></informationTable>")
    for n in range(len(dirs) + 1, 9):
        raw = ref(empty_xml)
        units[f"units_{n}"] = reading(OUT / f"13f-read-{n}", body, [{"input": raw, "context": context(OUT / f"13f-ctx/{n}", raw)}])
    securities = combine(OUT / "13f-reduce", folder / "reduce.yaml", units)
    combined = combine(OUT / "13f-combine", folder / "combine.yaml", {"securities": securities})
    stage("13F reduce and combine")
    recs, refused = records(OUT / "13f-mdm", combined, {"table": "security", "dataset": code, "policy": "0" * 64, "consumer": "dry",
                            "batch_id": "13f-dry", "as_of": "2026-10-22T00:00:00+00:00"}, code, doc["mdm"][code]["contract"])
    found = found_of(recs)
    report["thirteenf"] = {**compare(found, {c: next(iter(s)) for c, s in oracle.items() if len(s) == 1},
                                     {c for c, s in oracle.items() if len(s) > 1}),
                           "refused": dict(refused), "quality_counts": {k: v for k, v in quality.counts(recs, []).items() if "share_class" in k}}
    stage("13F contract")
    print(json.dumps(report["thirteenf"]), flush=True)

# ---- N-PORT
name = "sec.nport.security"; code = f"{name}.v2"; folder = files.ROOT / "sources" / name
doc = files.source(name)
zpath = Path(os.environ["NPORT_ZIP"]).expanduser()
raw = ref(zpath)
q2 = "2026-06-30T00:00:00+00:00"
ids = reading(OUT / "np-identifiers", {"source": name, **files.load(folder / "identifiers.yaml")},
              [{"input": raw, "context": context(OUT / "np-identifiers", raw)}])
stage("N-PORT identifiers read")
def lookups(root, sets):
    root.mkdir(parents=True, exist_ok=True)
    return store.put(root.as_uri(), {"version": 2, "input": raw, "sets": sets})
isin_set = {"readings": [ids], "table": "isin", "column": "holding", "value_column": "isin",
            "max_input_bytes": 16 * 1024**3, "max_input_rows": 100_000_000}
holdings = reading(OUT / "np-holdings", {k: doc[k] for k in ("source", "execution", "read")},
                   [{"input": raw, "context": context(OUT / "np-holdings", raw, {"period": q2}),
                     "lookups": lookups(OUT / "np-holdings", {"isin": isin_set})}], version=3)
stage("N-PORT holdings read")
# The issuer facts give only the ISSUED_BY link, never the class: empty here.
(OUT / "np-issuers").mkdir(parents=True, exist_ok=True)
issuer_reduced = store.put((OUT / "np-issuers").as_uri(), {"version": 1, "artifacts": [{"input": raw, "tables": {
    "cusip_issuers": [], "cusip_filed": [], "isin_filed": [], "isin_issuers": []}, "deferred": []}]})
reduced = combine(OUT / "np-reduce", folder / "reduce.yaml", {"holdings": holdings})
(OUT / "np-attached").mkdir(parents=True, exist_ok=True)
attached = store.put((OUT / "np-attached").as_uri(), {"version": 1, "artifacts": [{"input": raw, "tables": {"attached": []}, "deferred": []}]})
folded = combine(OUT / "np-fold", folder / "fold.yaml", {"securities": reduced, "attached": attached, "issuers": issuer_reduced})
combined = combine(OUT / "np-combine", folder / "combine.yaml",
                   {"securities": reduced, "attached": attached, "issuers": issuer_reduced, "folded": folded})
stage("N-PORT reduce and combines")
pieces = []
(OUT / "np-record").mkdir(parents=True, exist_ok=True)
for a in store.json(combined)["artifacts"]:
    for part in a.get("partitions") or [{"receipt": store.put((OUT / "np-record").as_uri(), {"tables": a["tables"]})}]:
        pieces.append(part["receipt"])
recorded = reading(OUT / "np-record", {"source": name, **files.load(folder / "record.yaml")},
                   [{"input": p, "context": context(OUT / "np-record-ctx", p)} for p in pieces])
stage("N-PORT record")
recs, refused = records(OUT / "np-mdm", recorded, {"table": "security", "record_column": "record", "dataset": code,
                        "policy": "0" * 64, "consumer": "dry", "batch_id": "np-dry", "as_of": "2026-10-22T00:00:00+00:00"},
                        code, doc["mdm"][code]["contract"])
# The oracle by CUSIP: equity holdings with a usable CUSIP.
oracle = defaultdict(set)
with zipfile.ZipFile(zpath) as z, z.open("FUND_REPORTED_HOLDING.tsv") as fh:
    r = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", errors="ignore", newline=""), delimiter="\t", quoting=csv.QUOTE_NONE)
    csv.field_size_limit(10**9); h = next(r)
    ic, itl, ia = h.index("ISSUER_CUSIP"), h.index("ISSUER_TITLE"), h.index("ASSET_CAT")
    for row in r:
        if len(row) <= ia or row[ia] != "EC":
            continue
        c = row[ic].strip().upper()
        if not c or c in ("000000000", "999999999") or not letter(row[itl]):
            continue
        oracle[c].add(letter(row[itl]))
found = found_of(recs)
cusip_found = {k: v for k, v in found.items() if len(k) == 9}
isin_found = {k: v for k, v in found.items() if len(k) == 12}
report["nport"] = {"by_cusip": compare(cusip_found, {c: next(iter(s)) for c, s in oracle.items() if len(s) == 1},
                                       {c for c, s in oracle.items() if len(s) > 1}),
                   "isin_only": {"records": len(isin_found), "share_class_filled": sum(1 for v, _ in isin_found.values() if v),
                                 "flagged": sum(1 for _, f in isin_found.values() if f),
                                 "filled_and_flagged": sum(1 for v, f in isin_found.values() if v and f)},
                   "refused": dict(refused), "quality_counts": {k: v for k, v in quality.counts(recs, []).items() if "share_class" in k}}
stage("N-PORT contract")
print(json.dumps(report, indent=1))
(OUT / "report.json").write_text(json.dumps(report, indent=1))
