"""Score a findings.yaml against a trial's expected.yaml; writes RESULT.md lines to stdout.

    python score.py <findings.yaml> <expected.yaml>
A label/code line names the code column; its label column is not required.
Column names match by whole trailing path segments: the key wrote `StartNode.NodeID`
for the flattened `RelationshipRecord.Relationship.StartNode.NodeID`.
"""

import sys

import yaml


def same(found: str, expected: str) -> bool:
    """A flattened column matches by its whole trailing path segments (a record wrapper may precede it)."""
    return found == expected or found.endswith("." + expected)


def same_list(found, expected) -> bool:
    return len(found) == len(expected) and all(any(same(f, e) for f in found) for e in expected)


def score(found: dict, expected: dict) -> list[tuple[bool, str]]:
    parts = {p["part"]: p for p in found["parts"]}
    lines = []
    for name, want in expected.get("parts", {}).items():
        p = parts.get(name)
        if p is None:
            lines.append((False, f"part {name}: not found"))
            continue
        lines.append((p["class"] in want["class"], f"{name}: class {p['class']} (expected {' or '.join(want['class'])})"))
        if "key" in want:
            lines.append((same_list(p["record_key"]["columns"], want["key"]),
                          f"{name}: key {p['record_key']['columns']} (expected {want['key']})"))
        else:
            lines.append((all(any(same(f, e) for f in p["record_key"]["columns"]) for e in want["key_contains"]),
                          f"{name}: key {p['record_key']['columns']} (expected to contain {want['key_contains']})"))
        lines.append((p["confidence"] >= expected["min_confidence"] or p["class"] not in want["class"],
                      f"{name}: confidence {p['confidence']}"))
    for fp, fc, tp, tc, card, *onboard in expected.get("relationships", []):
        r = next((x for x in found["relationships"] if x["from"]["part"] == fp and x["to"]["part"] == tp
                  and same_list(x["from"]["columns"], fc) and same_list(x["to"]["columns"], tc)), None)
        ok = r is not None and r["inclusion"] >= 0.9 and r["cardinality"] == card
        if ok and onboard:
            ok = r["onboard"] in onboard[0].split("|")
        got = f"inclusion {r['inclusion']}, {r['cardinality']}, {r['onboard']}" if r else "not found"
        lines.append((ok, f"link {fp}.{'+'.join(fc)} → {tp}.{'+'.join(tc)} {card}: {got}"))
    for h in expected.get("hierarchies", []):
        match = [x for x in found["hierarchies"] if x["part"] == h["part"] and x["evidence_kind"] in h["evidence"]
                 and set(h["columns"]) <= {lv["column"] for lv in x["levels"]}
                 and x["type"] == h.get("type", x["type"])]
        lines.append((bool(match), f"hierarchy {h['part']} {' > '.join(reversed(h['columns']))}: "
                                   f"{match[0]['evidence_kind'] if match else 'not found'}"))
    for name, column, family in expected.get("identifiers", []):
        got = next((i["check_digit"] for i in parts.get(name, {}).get("identifiers", []) if same(i["column"], column)), None)
        lines.append((got == family, f"identifier {name}.{column}: check digit {got} (expected {family})"))
    for name, scan in expected.get("scale", {}).items():
        got = parts[name]["scan"] if name in parts else None
        lines.append((got == scan, f"scan of {name}: {got} (expected {scan})"))
    for name, cols in expected.get("code_lists", {}).items():
        listed = {c["column"] for c in parts[name]["code_lists"]} | {c["label_column"] for c in parts[name]["code_lists"]}
        # A list of codes inside the record is its own child part with a code list on `value`.
        listed |= {p.rsplit(".", 1)[1] for p, x in parts.items() if p.startswith(name + ".")
                   and any(c["column"] == "value" for c in x["code_lists"])}
        missing = [c for c in cols if not any(same(str(l), c) for l in listed if l)]
        lines.append((not missing, f"code lists of {name}: missing {missing}" if missing else f"code lists of {name}: all found"))
    for name, cols in expected.get("personal", {}).items():
        tags = {c["name"]: c["sensitivity"] for c in parts[name]["columns"]}
        missing = [c for c in cols if not any(same(n, c) and t != "none" for n, t in tags.items())]
        lines.append((not missing, f"personal in {name}: missing {missing}" if missing else f"personal in {name}: all tagged"))
    for name in expected.get("no_personal", []):
        extra = [c["name"] for c in parts[name]["columns"] if c["sensitivity"] != "none"]
        lines.append((not extra, f"no personal in {name}: {extra or 'none tagged'}"))
    for name, role, cols in expected.get("time", []):
        t = parts[name]["time"]
        got = {"as_of": [t["as_of"]["from"], t["as_of"]["to"]], "event_time": [t["event_time"]], "as_at": [t["as_at"]],
               "series": (t["series"]["key"] + [t["series"]["time"]]) if t["series"] else []}[role]
        lines.append((len(got) == len(cols) and all(g is not None and same(g, c) for g, c in zip(got, cols)),
                      f"time {name} {role}: {got} (expected {cols})"))
    return lines


if __name__ == "__main__":
    found = yaml.safe_load(open(sys.argv[1]))
    expected = yaml.safe_load(open(sys.argv[2]))
    lines = score(found, expected)
    for ok, text in lines:
        print(f"- [{'x' if ok else ' '}] {text}")
    passed = sum(ok for ok, _ in lines)
    print(f"\n{passed} of {len(lines)} lines match.")
