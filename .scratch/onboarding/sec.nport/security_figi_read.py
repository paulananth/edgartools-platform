"""OpenFIGI readings over captured files (ticket 80): requests, then answers through the pair set.
Usage: figi_read.py CAPTURE OUT KIND START COUNT. Counts only; checks every answer row against
a direct position match."""
import hashlib, json, sys, time
from pathlib import Path
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read, source_readings

CAP, OUT, KIND, START, COUNT = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
FOLDER = Path("rules/sources/sec.nport.security")
store = Artifacts()
def ref(path):
    return {"uri": path.as_uri(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
names = sorted(p.name for p in (CAP / KIND).glob("*.request.json"))[START:START + COUNT]
def run(root, body, artifacts, version):
    root.mkdir(parents=True, exist_ok=True)
    contract = store.put(root.as_uri(), body)
    manifest = store.put(root.as_uri(), {"version": version, "contract": contract, "artifacts": artifacts})
    return source_read.execute({"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}, store)
def context(root, path, batch):
    root.mkdir(parents=True, exist_ok=True)
    return store.put(root.as_uri(), {"version": 1, "input": ref(path), "values": {"batch": batch}})
t = time.monotonic()
req_root = OUT / f"{KIND}-{START}" / "requests"
arts = []
for n in names:
    path, batch = CAP / KIND / n, f"{KIND}/{n.split('.')[0]}"
    arts.append({"input": ref(path), "context": context(req_root / "ctx" / batch.replace('/', '-'), path, batch)})
requests = run(req_root, files.load(FOLDER / "figi-requests.yaml"), arts, 2)
ans_root = OUT / f"{KIND}-{START}" / "answers"
arts = []
for n in names:
    path, batch = CAP / KIND / n.replace(".request", ""), f"{KIND}/{n.split('.')[0]}"
    lk = store.put(ans_root.as_uri(), {"version": 2, "input": ref(path), "sets": {"asked": {
        "readings": [requests], "table": "asked", "column": "key", "value_column": "id",
        "max_input_bytes": 1 << 30, "max_input_rows": 1_000_000}}})
    arts.append({"input": ref(path), "context": context(ans_root / "ctx" / batch.replace('/', '-'), path, batch), "lookups": lk})
answers = run(ans_root, files.load(FOLDER / "figi-answers.yaml"), arts, 3)
rows = [r for a in source_readings.load(answers, store, max_bytes=1 << 32, max_rows=10**7, allow_lookup_receipts=True)[0]["artifacts"] for r in a["tables"]["found"]]
expected = []
for n in names:
    for job, ans in zip(json.loads((CAP / KIND / n).read_text()), json.loads((CAP / KIND / n.replace(".request", "")).read_text())):
        expected.append((job["idValue"], sorted({d[f] for d in ans.get("data", []) for f in ("figi", "compositeFIGI") if d.get(f)}) if "data" in ans else None))
got = [(r["id"], sorted(set(r["figis"])) if r["figis"] is not None else None) for r in rows]
print(json.dumps({"files": len(names), "rows": len(rows), "with_figis": sum(r["figis"] is not None for r in rows),
                  "id_null": sum(r["id"] is None for r in rows), "mismatch": sum(a != b for a, b in zip(got, expected)) + abs(len(got) - len(expected)),
                  "seconds": round(time.monotonic() - t, 1), "requests": requests, "answers": answers}))
