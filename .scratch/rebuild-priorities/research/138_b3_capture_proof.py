"""Ticket 138 part B3: the configured Listing currency steps on the 2026 Q2 OpenFIGI capture.
Counts only. Runs requests.yaml, the answers reading, line-counts.yaml, lines.yaml and
listing.yaml through the same engine as the run, 64 answer files a reading."""
import collections
import hashlib
import os
import sys
import time
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
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
piece_root = root / "listing"
piece_root.mkdir(parents=True, exist_ok=True)
pieces = [store.put(piece_root.as_uri(), {"tables": a["tables"]}) for a in store.json(lines)["artifacts"]]
listing = chain.read(store, piece_root, files.load(FOLDER / "listing.yaml"), [
    {"input": p, "context": store.put(piece_root.as_uri(), {"version": 1, "input": p, "values": {}})}
    for p in pieces], 2)
print(f"listing, {time.time() - started:.0f}s", flush=True)

c = collections.Counter()
for artifact in store.json(listing)["artifacts"]:
    for part in artifact["partitions"]:
        for row in store.json(part["receipt"])["tables"]["listings"]:
            c["lines"] += 1
            c["lines given a currency"] += "currency" in row["detail"]
            c["lines without an exchange"] += "exchange" not in row["detail"]
            c["lines without an exchange given a currency"] += "exchange" not in row["detail"] and "currency" in row["detail"]
for artifact in store.json(lines)["artifacts"]:
    for row in artifact["tables"]["lines"]:
        qualifies = row["lines"] > 1 and row["roots"] == 1 and row["tickers"] == row["lines"]
        c["lines in qualifying groups"] += qualifies
        c["lines in qualifying groups without a code"] += qualifies and row.get("code") is None
for k, v in c.items():
    print(f"{k}: {v:,}")
print(f"elapsed {time.time() - started:.0f}s")


# Finishing step (the large lines output is an index of pieces, read as the run reads it):
# """Ticket 138 part B3: finish the capture proof from the saved lines.yaml output: listing.yaml
# read over its pieces as the run reads them (a version-4 input), then counts only."""
# import collections
# import hashlib
# import sys
# import time
# from pathlib import Path
# 
# from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
# from edgar_warehouse.rules import files
# from edgar_warehouse.workers import source_read
# 
# run = Path(sys.argv[1])
# store = Artifacts()
# started = time.time()
# lines_out = run / "lines" / "out.json"
# lines_ref = {"uri": lines_out.as_uri(), "sha256": hashlib.sha256(lines_out.read_bytes()).hexdigest()}
# where = run / "listing"
# where.mkdir(parents=True, exist_ok=True)
# contract = store.put(where.as_uri(), files.load(files.ROOT / "sources" / "openfigi" / "listing.yaml"))
# manifest = store.put(where.as_uri(), {"version": 4, "contract": contract, "pieces": lines_ref})
# task = {"input": manifest, "output": (where / "reading.json").as_uri(), "checks": ["source.output"]}
# listing = source_read.execute(task, store)
# print(f"listing read, {time.time() - started:.0f}s", flush=True)
# 
# c = collections.Counter()
# for artifact in store.json(listing)["artifacts"]:
#     for part in artifact["partitions"]:
#         for row in store.json(part["receipt"])["tables"]["listings"]:
#             d = row["detail"]
#             c["lines"] += 1
#             c["lines given a currency"] += "currency" in d
#             c["lines without an exchange"] += "exchange" not in d
#             c["lines without an exchange given a currency"] += "exchange" not in d and "currency" in d
# for part in store.json(lines_ref)["artifacts"][0]["partitions"]:
#     for row in store.json(part["receipt"])["tables"]["lines"]:
#         qualifies = row["lines"] > 1 and row["roots"] == 1 and row["tickers"] == row["lines"]
#         c["lines in groups of two or more"] += row["lines"] > 1
#         c["lines in qualifying groups"] += qualifies
#         c["lines in qualifying groups without a code"] += qualifies and row.get("code") is None
#         c["single lines ending in a code (no currency)"] += row["lines"] == 1 and row.get("code") is not None
# for k, v in c.items():
#     print(f"{k}: {v:,}")
# print(f"elapsed {time.time() - started:.0f}s")
