"""compare: approved findings against a new delivery's findings → drift items.

Each item names the skill that handles it: data-quality, refining-rules or rdm.
"""

from __future__ import annotations

FILL_CHANGE = 0.05
ROWS_CHANGE = 0.5


def compare(approved: dict, new: dict) -> list[dict]:
    old_parts = {p["part"]: p for p in approved["parts"]}
    new_parts = {p["part"]: p for p in new["parts"]}
    items = []

    def add(kind, part, detail, skill, column=None):
        items.append({"drift": kind, "part": part, "column": column, "detail": detail, "handled_by": skill})

    for name in sorted(old_parts.keys() - new_parts.keys()):
        add("part_missing", name, "a part of the approved findings is not in the new delivery", "refining-rules")
    for name in sorted(new_parts.keys() - old_parts.keys()):
        add("part_new", name, "a part not in the approved findings: profile and approve it first", "refining-rules")
    for name in sorted(old_parts.keys() & new_parts.keys()):
        old, cur = old_parts[name], new_parts[name]
        if old["class"] != cur["class"]:
            add("class_changed", name, f"{old['class']} → {cur['class']}", "refining-rules")
        if old["record_key"]["columns"] != cur["record_key"]["columns"] or \
                old["record_key"]["found"] != cur["record_key"]["found"]:
            add("key_changed", name, f"{old['record_key']['columns']} → {cur['record_key']['columns']}"
                                     f" (found: {cur['record_key']['found']})", "data-quality")
        if old["rows"] and abs(cur["rows"] - old["rows"]) / old["rows"] > ROWS_CHANGE:
            add("volume_changed", name, f"{old['rows']} → {cur['rows']} rows", "data-quality")
        old_cols = {c["name"]: c for c in old["columns"]}
        new_cols = {c["name"]: c for c in cur["columns"]}
        for col in sorted(old_cols.keys() - new_cols.keys()):
            add("column_missing", name, "an approved column is gone", "refining-rules", col)
        for col in sorted(new_cols.keys() - old_cols.keys()):
            add("column_new", name, "a column not in the approved findings", "refining-rules", col)
        for col in sorted(old_cols.keys() & new_cols.keys()):
            a, b = old_cols[col], new_cols[col]
            if a["type"] != b["type"]:
                add("type_changed", name, f"{a['type']} → {b['type']}", "refining-rules", col)
            if abs(a["fill"] - b["fill"]) > FILL_CHANGE:
                add("fill_changed", name, f"{a['fill']} → {b['fill']}", "data-quality", col)
            if a["sensitivity"] != b["sensitivity"]:
                add("sensitivity_changed", name, f"{a['sensitivity']} → {b['sensitivity']}", "refining-rules", col)
        old_codes = {c["column"]: c for c in old["code_lists"]}
        for code in cur["code_lists"]:
            before = old_codes.get(code["column"])
            if before and code["distinct"] != before["distinct"]:
                add("codes_changed", name, f"{before['distinct']} → {code['distinct']} distinct codes",
                    _codes_owner(cur), code["column"])
        approved_codes = _guarded(old)
        for column, values in sorted(_guarded(cur).items()):
            added = sorted(set(values) - set(approved_codes.get(column, values)))
            if added:
                add("codes_new", name, f"{len(added)} codes not in the approved list: {', '.join(added[:10])}",
                    _codes_owner(cur), column)
    old_links = {_link(r): r for r in approved["relationships"]}
    new_links = {_link(r): r for r in new["relationships"]}
    for key in sorted(old_links.keys() - new_links.keys()):
        add("link_broken", key[0], f"{'+'.join(key[1])} no longer points at {key[2]}", "data-quality")
    for key in sorted(old_links.keys() & new_links.keys()):
        a, b = old_links[key], new_links[key]
        if b["inclusion"] < a["inclusion"] - 0.01:
            add("link_weaker", key[0], f"inclusion {a['inclusion']} → {b['inclusion']}", "data-quality", "+".join(key[1]))
    old_h = {h["hierarchy"]: h for h in approved["hierarchies"]}
    for h in new["hierarchies"]:
        before = old_h.get(h["hierarchy"])
        if before and (h["holds"] < before["holds"] or h["depth"] != before["depth"]):
            add("hierarchy_changed", h["part"], f"holds {before['holds']} → {h['holds']}, depth "
                                                f"{before['depth']} → {h['depth']}", "rdm" if h["type"] == "reference"
                else "refining-rules")
    return items


def _codes_owner(part: dict) -> str:
    """A reference part's codes are RDM's; any other part's are a data quality matter."""
    return "rdm" if part["class"] == "reference" else "data-quality"


def _guarded(part: dict) -> dict[str, list]:
    """The values of each code list the profile guards (its code_list quality items)."""
    return {q["column"]: q["args"]["values"] for q in part.get("quality") or [] if q["check"] == "code_list"}


def _link(r: dict) -> tuple:
    return (r["from"]["part"], tuple(r["from"]["columns"]), r["to"]["part"], tuple(r["to"]["columns"]))
