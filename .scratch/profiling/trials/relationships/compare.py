"""Ticket 04, check on real data, step 3: MDM's outcome per entity against the source's own direct chain.

    python .scratch/profiling/trials/relationships/compare.py <slice folder> <chain-check.json> <out compare.json>

Walks each sampled entity's direct consolidating chain in the slice's own
relationship records (the source), and cross-tabulates where it ends against
MDM's outcome for the same entity (chain-check.json, per_child).
"""

import collections
import json
import sys
from pathlib import Path

folder, check, out = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text()), Path(sys.argv[3])
chosen = json.loads((folder / "slice.json").read_text())
direct = {}
for line in (folder / "relationships.jsonl").open():
    rel = json.loads(line)["RelationshipRecord"]["Relationship"]
    if rel["RelationshipType"]["$"] == "IS_DIRECTLY_CONSOLIDATED_BY":
        direct[rel["StartNode"]["NodeID"]["$"]] = rel["EndNode"]["NodeID"]["$"]
table, ends = collections.Counter(), {}
for child in chosen["sample"]:
    node, seen = child, set()
    while node in direct and node not in seen:
        seen.add(node)
        node = direct[node]
    ends[child] = node
    source = "source chain ends at the stated ultimate parent" if node == chosen["stated_ultimate"][child] \
        else "source chain ends elsewhere"
    mdm = check["per_child"][child]
    same = "" if mdm["end"] is None else (" (same end as the source)" if mdm["end"] == node else " (DIFFERENT end)")
    table[f"{source} | MDM: {mdm['outcome']}{same}"] += 1
out.write_text(json.dumps({"cross_tab": dict(sorted(table.items())), "source_chain_end": ends}, indent=1))
print(json.dumps(dict(sorted(table.items())), indent=1))
