"""Ticket 138, the Listing: each listing's MIC on the 2026 Q2 OpenFIGI capture. Counts only.
Runs requests.yaml, the answers reading, line-counts.yaml, lines.yaml and listing.yaml
through the same engine as the run (B3's proof, its listing read as the run reads its
pieces), then counts the listings with a MIC."""
import collections
import hashlib
import os
import sys
import time
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read
from tests.support import source_chain as chain

CAP = Path(os.path.expanduser("~/.local/share/edgartools/clean-mdm/captures/openfigi/2026q2-nport"))
FOLDER = files.ROOT / "sources" / "openfigi"
root = Path(sys.argv[1])
store = Artifacts()
started = time.time()


def ref(path: Path) -> dict:
    return {"uri": path.as_uri(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def context(where: Path, path: Path, values: dict) -> dict:
    where.mkdir(parents=True, exist_ok=True)
    return store.put(where.as_uri(), {"version": 1, "input": ref(path), "values": values})


answers_body = {k: v for k, v in files.source("openfigi").items() if k in ("source", "execution", "read")}
requests_body = files.load(FOLDER / "requests.yaml")
readings = []
for kind in ("id_cusip", "id_isin"):
    names = sorted(n for n in os.listdir(CAP / kind) if not n.endswith(".request.json"))
    for start in range(0, len(names), 64):
        chunk = names[start:start + 64]
        where = root / f"{kind}_{start:05d}"
        asked = chain.read(store, where / "requests", requests_body, [
            {"input": ref(CAP / kind / n.replace(".json", ".request.json")),
             "context": context(where / "rq" / n, CAP / kind / n.replace(".json", ".request.json"),
                                {"batch": f"{kind}/{n.split('.')[0]}"})} for n in chunk], 2)
        artifacts = []
        for n in chunk:
            answer = CAP / kind / n
            lookups = store.put((where / "lk").as_uri(), {"version": 2, "input": ref(answer), "sets": {"asked": {
                "readings": [asked], "table": "asked", "column": "key", "value_column": "id",
                "max_input_bytes": 1 << 26, "max_input_rows": 1 << 20}}})
            artifacts.append({"input": ref(answer), "lookups": lookups,
                              "context": context(where / "an" / n, answer,
                                                 {"batch": f"{kind}/{n.split('.')[0]}", "id_type": kind})})
        readings.append(chain.read(store, where / "answers", answers_body, artifacts, 3))
    print(f"{kind} read, {len(readings)} readings, {time.time() - started:.0f}s", flush=True)

line_counts = chain.combine(store, root / "line_counts", FOLDER / "line-counts.yaml", {"answers": readings})
print(f"line counts, {time.time() - started:.0f}s", flush=True)
lines = chain.combine(store, root / "lines", FOLDER / "lines.yaml", {"counts": line_counts, "answers": readings})
print(f"lines, {time.time() - started:.0f}s", flush=True)
where = root / "listing"
where.mkdir(parents=True, exist_ok=True)
contract = store.put(where.as_uri(), files.load(FOLDER / "listing.yaml"))
manifest = store.put(where.as_uri(), {"version": 4, "contract": contract, "pieces": lines})
listing = source_read.execute({"input": manifest, "output": (where / "reading.json").as_uri(),
                               "checks": ["source.output"]}, store)
print(f"listing, {time.time() - started:.0f}s", flush=True)

c, figis = collections.Counter(), {}
for artifact in store.json(listing)["artifacts"]:
    for part in artifact["partitions"]:
        for row in store.json(part["receipt"])["tables"]["listings"]:
            d = row["detail"]
            c["lines"] += 1
            c["lines with a MIC"] += "mic" in d
            c["lines with an exchange code and no MIC"] += "exchange" in d and "mic" not in d
            c["lines without an exchange code"] += "exchange" not in d
            figis[d.get("figi")] = "mic" in d
c["listing FIGIs"] = len(figis)
c["listing FIGIs with a MIC"] = sum(figis.values())
for k, v in c.items():
    print(f"{k}: {v:,}")
print(f"elapsed {time.time() - started:.0f}s")
