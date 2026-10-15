"""What approved findings put in the Data Catalog: `rules/sources/<source>/profile.yaml`.

The catalog is published one way from the rules files (`edgar_warehouse/rules/catalog.py`),
so the findings reach it through a rules file. The repository is public: this
file keeps names, types and counts only, never a value from the data. Examples,
top values, distributions, check arguments (a code list's values, a pattern) and
hierarchy samples are left out; the full findings stay beside the data.

For every part: its class and rows, its record key, its silver table (every
column a field) and the data quality rules it needs (each with the rows that
failed it in the profiled delivery). For the data set: the RDM code sets it needs.
"""

from __future__ import annotations

VERSION = 1


def code_set_name(part: dict, code: dict) -> str:
    """A code list's code set: the existing one, else the proposed name, else the part's column."""
    return code["code_set"] or code["proposed_code_set"] or f"{part['part']}.{code['column']}"


def code_sets(parts: list[dict]) -> list[dict]:
    """The RDM code sets the data set needs: one per existing or proposed code set, naming
    every column that uses it (findings spec section 2). Counts and names only: the codes
    themselves go to RDM as a draft (data-profiling, "Reference data")."""
    sets: dict[str, dict] = {}
    for f in parts:
        for code in f["code_lists"]:
            name = code_set_name(f, code)
            entry = sets.setdefault(name, {"code_set": name, "existing": bool(code["code_set"]),
                                           "columns": [], "codes": 0, "label_columns": []})
            entry["columns"].append(f"{f['part']}.{code['column']}")
            entry["codes"] = max(entry["codes"], code["distinct"])
            if code["label_column"]:
                entry["label_columns"].append(f"{f['part']}.{code['label_column']}")
    return sorted(sets.values(), key=lambda s: s["code_set"])


def summary(findings: dict) -> dict:
    """The public summary of approved findings."""
    approval = findings.get("approval") or {}
    if approval.get("status") != "approved":
        raise ValueError("the findings are not approved: approve them before they reach the catalog")
    dataset = findings["dataset"]
    return {
        "version": VERSION,
        "dataset": dataset["name"],
        "profiled_at": dataset["profiled_at"],
        "approved_at": approval["approved_at"],
        "parts": [_part(p, findings) for p in findings["parts"]],
        # Rebuilt from the parts, as profiling builds them, so findings approved before
        # `code_sets` and silver for every part existed give the same catalog.
        "code_sets": [{"code_set": s["code_set"], "existing": s["existing"], "codes": s["codes"],
                       "columns": s["columns"]} for s in code_sets(findings["parts"])],
    }


def _part(part: dict, findings: dict) -> dict:
    from .run import silver_spec  # the spec profiling writes, for findings made before every part had one
    by_name = {p["part"]: p for p in findings["parts"]}
    silver = part.get("silver") or silver_spec(part, findings.get("relationships") or [], by_name)
    codes = {c["column"]: code_set_name(part, c) for c in part.get("code_lists") or []}
    return {
        "part": part["part"],
        "class": part["class"],
        "kind": part.get("kind") or (part.get("proposed_kind") or {}).get("kind"),
        "rows": part["rows"],
        "record_key": list(part["record_key"]["columns"]),
        "silver": {
            "table": silver.get("table"),
            "load_mode": silver.get("load_mode"),
            "key": list(silver.get("key") or []),
            "fields": [{"name": c["name"], "type": c["type"], "nullable": c["nullable"],
                        "sensitivity": c["sensitivity"], **({"code_set": codes[c["name"]]} if c["name"] in codes else {})}
                       for c in silver.get("columns") or []],
            "links": [{"source_key": link["source_key"], "to_part": link["to_part"],
                       "mdm_id_column": link["mdm_id_column"]} for link in silver.get("links") or []],
        },
        "quality": [{"check": q["check"], "column": q["column"], "failed_rows": q["rows"],
                     "proposal": q["proposal"], "why": q["why"]} for q in part.get("quality") or []],
    }
