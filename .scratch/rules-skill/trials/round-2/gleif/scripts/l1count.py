"""Count Level 1 records from a `grep -F -A1` stream of key/value line pairs.

Keys: "LEI" (starts a record), "EntityCategory", "EntityStatus",
"RegistrationStatus". Checks each LEI with the reader's own format_value.
"""
import json, sys
from collections import Counter
from edgar_warehouse.mdm.clean.adapters import format_value, UnsupportedRecord

c = {k: Counter() for k in ("category", "entity_status", "registration_status", "bad", "bad_by")}
seen, dups, n, examples, rec, key = set(), 0, 0, [], None, None

def flush(r):
    global dups
    if r is None: return
    cat, es, rs = r.get("EntityCategory"), r.get("EntityStatus"), r.get("RegistrationStatus")
    c["category"][cat] += 1; c["entity_status"][es] += 1; c["registration_status"][rs] += 1
    lei = r["LEI"]
    if lei in seen: dups += 1
    seen.add(lei)
    try:
        format_value(lei, "lei")
    except UnsupportedRecord as e:
        c["bad"][e.reason] += 1; c["bad_by"][f"{cat}|{es}|{rs}"] += 1
        if len(examples) < 20: examples.append([lei, cat, es, rs])

for line in sys.stdin:
    s = line.strip()
    if s.startswith('"$"'):
        if key:
            v = s.split(":", 1)[1].strip().strip('"')
            if key == "LEI":
                flush(rec); n += 1; rec = {"LEI": v}
            elif rec is not None and key not in rec:
                rec[key] = v
        key = None
    elif s.endswith("{") and s.startswith('"'):
        key = s.split('"')[1]
flush(rec)
out = {"records": n, "duplicate_leis": dups, **{k: dict(v.most_common()) for k, v in c.items()}, "examples": examples}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(json.dumps({k: out[k] for k in ("records", "duplicate_leis", "bad", "bad_by", "category")}))
