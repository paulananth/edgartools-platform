"""Score a findings.yaml against a trial's expected.yaml; writes RESULT.md lines to stdout.

    python score.py <findings.yaml> <expected.yaml>
A label/code line names the code column; its label column is not required.
"""

import sys

import yaml


def score(found: dict, expected: dict) -> list[tuple[bool, str]]:
    parts = {p["part"]: p for p in found["parts"]}
    lines = []
    for name, want in expected.get("parts", {}).items():
        p = parts.get(name)
        if p is None:
            lines.append((False, f"part {name}: not found"))
            continue
        lines.append((p["class"] in want["class"], f"{name}: class {p['class']} (expected {' or '.join(want['class'])})"))
        lines.append((set(p["record_key"]["columns"]) == set(want["key"]),
                      f"{name}: key {p['record_key']['columns']} (expected {want['key']})"))
        lines.append((p["confidence"] >= expected["min_confidence"] or p["class"] not in want["class"],
                      f"{name}: confidence {p['confidence']}"))
    rels = {(r["from"]["part"], tuple(r["from"]["columns"]), r["to"]["part"], tuple(r["to"]["columns"])): r
            for r in found["relationships"]}
    for fp, fc, tp, tc, card in expected.get("relationships", []):
        r = rels.get((fp, tuple(fc), tp, tuple(tc)))
        ok = r is not None and r["inclusion"] >= 0.9 and r["cardinality"] == card
        got = f"inclusion {r['inclusion']}, {r['cardinality']}" if r else "not found"
        lines.append((ok, f"link {fp}.{'+'.join(fc)} → {tp}.{'+'.join(tc)} {card}: {got}"))
    for h in expected.get("hierarchies", []):
        match = [x for x in found["hierarchies"] if x["part"] == h["part"] and x["evidence_kind"] in h["evidence"]
                 and set(h["columns"]) <= {lv["column"] for lv in x["levels"]}]
        lines.append((bool(match), f"hierarchy {h['part']} {' > '.join(reversed(h['columns']))}: "
                                   f"{match[0]['evidence_kind'] if match else 'not found'}"))
    for name, cols in expected.get("code_lists", {}).items():
        listed = {c["column"] for c in parts[name]["code_lists"]} | {c["label_column"] for c in parts[name]["code_lists"]}
        missing = [c for c in cols if c not in listed]
        lines.append((not missing, f"code lists of {name}: missing {missing}" if missing else f"code lists of {name}: all found"))
    for name, cols in expected.get("personal", {}).items():
        tags = {c["name"]: c["sensitivity"] for c in parts[name]["columns"]}
        missing = [c for c in cols if tags.get(c, "none") == "none"]
        lines.append((not missing, f"personal in {name}: missing {missing}" if missing else f"personal in {name}: all tagged"))
    for name in expected.get("no_personal", []):
        extra = [c["name"] for c in parts[name]["columns"] if c["sensitivity"] != "none"]
        lines.append((not extra, f"no personal in {name}: {extra or 'none tagged'}"))
    for name, role, cols in expected.get("time", []):
        t = parts[name]["time"]
        got = {"as_of": [t["as_of"]["from"], t["as_of"]["to"]], "event_time": [t["event_time"]], "as_at": [t["as_at"]],
               "series": (t["series"]["key"] + [t["series"]["time"]]) if t["series"] else []}[role]
        lines.append((list(got) == cols, f"time {name} {role}: {got} (expected {cols})"))
    return lines


if __name__ == "__main__":
    found = yaml.safe_load(open(sys.argv[1]))
    expected = yaml.safe_load(open(sys.argv[2]))
    lines = score(found, expected)
    for ok, text in lines:
        print(f"- [{'x' if ok else ' '}] {text}")
    passed = sum(ok for ok, _ in lines)
    print(f"\n{passed} of {len(lines)} lines match.")
