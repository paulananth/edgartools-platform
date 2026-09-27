"""Count REPEX records from a grep stream of key lines and `"$" :` value lines.

Mirrors gleif_source.record_evidence for reporting_exceptions, scope ignored.
"""
import json, sys
from collections import Counter
from edgar_warehouse.mdm.clean.adapters import format_value, UnsupportedRecord
from edgar_warehouse.mdm.clean.gleif_source import EXCEPTION_REASONS

c = {k: Counter() for k in ("category", "exception_reason", "reasons_per_record", "reason", "keys", "category_x_reason")}
n, rec, key, seen, dups, examples = 0, None, None, set(), 0, []
CATS = {"DIRECT_ACCOUNTING_CONSOLIDATION_PARENT", "ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT"}

def flush(r):
    global dups
    if r is None: return
    cat, reasons = r.get("ExceptionCategory"), r.get("ExceptionReason", [])
    c["category"][cat] += 1; c["reasons_per_record"][len(reasons)] += 1
    for x in reasons: c["exception_reason"][x] += 1; c["category_x_reason"][f"{cat}|{x}"] += 1
    k = (r["LEI"], cat)
    if k in seen: dups += 1
    seen.add(k)
    try:
        format_value(r["LEI"], "lei")
        if cat not in CATS: why = "unsupported_exception_category"
        elif not reasons: why = "missing_exception_reason"
        elif any(x not in EXCEPTION_REASONS for x in reasons): why = "invalid_exception_reason"
        else: why = "reported_parent_exception"
    except UnsupportedRecord as e:
        why = e.reason
        if len(examples) < 20: examples.append([r["LEI"], cat, reasons])
    c["reason"][why] += 1

for line in sys.stdin:
    s = line.strip()
    if s.startswith('"$"'):
        v = s.split(":", 1)[1].strip().strip('"')
        if key == "LEI":
            flush(rec); n += 1; rec = {"LEI": v}
        elif key == "ExceptionCategory":
            rec["ExceptionCategory"] = v
        elif key == "ExceptionReason":
            rec.setdefault("ExceptionReason", []).append(v)
        if key != "ExceptionReason": key = None
    elif s.startswith('"'):
        key = s.split('"')[1]; c["keys"][key] += 1
flush(rec)
out = {"records": n, "duplicate_lei_category": dups, **{k: dict(v.most_common()) for k, v in c.items()}, "examples": examples}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(json.dumps({k: out[k] for k in ("records", "duplicate_lei_category", "reason", "category")}))
