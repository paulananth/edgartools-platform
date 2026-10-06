"""Ticket 04, check on real data, step 1: a slice of the local GLEIF golden copies.

    uv run --extra mdm python .scratch/profiling/trials/relationships/slice_gleif.py <out folder> [--sample 300]

Reads the local copies only (no request to any provider). Picks a seeded sample
of entities that state both a current direct consolidating parent and a
current ultimate one, walks each direct chain, and keeps every relationship
record and every Level 1 record those chains touch. Writes
`relationships.jsonl`, `level1.jsonl` and `slice.json` (the sample, and each
child's stated ultimate parent).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import zipfile
from pathlib import Path

from edgar_warehouse.mdm.clean.gleif_source import _BoundedReader, _json_records

G = Path.home() / ".local/share/edgartools/clean-mdm/research/gleif-20260911-1600"
DIRECT, ULTIMATE = "IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY"
BOUND = 64 * 1024 ** 3


def records(path: Path, wrapper: str):
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as raw:
        yield from _json_records(_BoundedReader(raw, BOUND, 64 * 1024 ** 2), wrapper)


def text(node, *path):
    for part in path:
        node = node.get(part) if isinstance(node, dict) else None
    return node.get("$") if isinstance(node, dict) else node


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--sample", type=int, default=300)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    direct, ultimate, kept = {}, {}, {}
    for row in records(next(G.glob("*rr-golden*.zip")), "relations"):
        rel = row["RelationshipRecord"]["Relationship"]
        kind, status = text(rel, "RelationshipType"), text(rel, "RelationshipStatus")
        if kind not in {DIRECT, ULTIMATE} or status != "ACTIVE":
            continue
        start, end = text(rel, "StartNode", "NodeID"), text(rel, "EndNode", "NodeID")
        (direct if kind == DIRECT else ultimate)[start] = end
        kept[(start, kind)] = row
    print(f"active direct {len(direct)}, ultimate {len(ultimate)}", flush=True)
    both = sorted(set(direct) & set(ultimate))
    sample = random.Random(0).sample(both, min(args.sample, len(both)))
    leis, rows = set(), []
    for child in sample:
        node, seen = child, set()
        while node in direct and node not in seen and len(seen) < 50:
            seen.add(node)
            rows.append(kept[(node, DIRECT)])
            leis.update({node, direct[node]})
            node = direct[node]
        rows.append(kept[(child, ULTIMATE)])
        leis.update({child, ultimate[child]})
    unique = {json.dumps(r, sort_keys=True): r for r in rows}
    with (args.out / "relationships.jsonl").open("w") as handle:
        for r in unique.values():
            handle.write(json.dumps(r) + "\n")
    print(f"sample {len(sample)}, relationship records {len(unique)}, entities {len(leis)}", flush=True)
    found = 0
    with (args.out / "level1.jsonl").open("w") as handle:
        for row in records(next(G.glob("*lei2*.zip")), "records"):
            if text(row, "LEI") in leis:
                handle.write(json.dumps(row) + "\n")
                found += 1
    print(f"level1 records found {found} of {len(leis)}", flush=True)
    (args.out / "slice.json").write_text(json.dumps(
        {"sample": sample, "stated_ultimate": {c: ultimate[c] for c in sample}, "leis": sorted(leis)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
