"""Write rows of configured readings' tables to one JSON Lines file (ticket 84), for rank_sources.py.

    uv run python dump_readings.py OUT.jsonl TABLE[,TABLE] READING [READING ...]

READING is a reading's `reading.json`, or a reduce or combine manifest whose `readings` it walks.
Reads the engine's saved outputs only; the rows hold values, so OUT stays outside the repository.
"""
import json
import sys
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts

store = Artifacts()


def readings(path: Path):
    body = json.loads(path.read_text())
    if "readings" in body:
        for ref in body["readings"].values():
            yield store.json(ref)
    else:
        yield body


def rows(index: dict, tables: set[str]):
    for artifact in index["artifacts"]:
        for part in artifact.get("partitions", []):
            piece = store.json(part["receipt"])
            for table in tables:
                yield from piece["tables"].get(table, [])


out, tables = Path(sys.argv[1]), set(sys.argv[2].split(","))
count = 0
with out.open("w", encoding="utf-8") as sink:
    for path in sys.argv[3:]:
        for index in readings(Path(path)):
            for row in rows(index, tables):
                sink.write(json.dumps(row) + "\n")
                count += 1
print(f"{count:,} rows of {sorted(tables)} to {out}")
