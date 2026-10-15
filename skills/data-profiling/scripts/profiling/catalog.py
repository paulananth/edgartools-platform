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

from . import codes, silver

VERSION = 1


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
                       "columns": s["columns"]} for s in codes.code_sets(findings["parts"])],
    }


def _part(part: dict, findings: dict) -> dict:
    by_name = {p["part"]: p for p in findings["parts"]}
    table = part.get("silver") or silver.spec(part, findings.get("relationships") or [], by_name)
    code_of = {c["column"]: codes.code_set_name(part, c) for c in part.get("code_lists") or []}
    return {
        "part": part["part"],
        "class": part["class"],
        "kind": part.get("kind") or (part.get("proposed_kind") or {}).get("kind"),
        "rows": part["rows"],
        "record_key": list(part["record_key"]["columns"]),
        "silver": {
            "table": table.get("table"),
            "load_mode": table.get("load_mode"),
            "key": list(table.get("key") or []),
            "fields": [{"name": c["name"], "type": c["type"], "nullable": c["nullable"],
                        "sensitivity": c["sensitivity"], **({"code_set": code_of[c["name"]]} if c["name"] in code_of else {})}
                       for c in table.get("columns") or []],
            "links": [{"source_key": link["source_key"], "to_part": link["to_part"],
                       "mdm_id_column": link["mdm_id_column"]} for link in table.get("links") or []],
        },
        "quality": [{"check": q["check"], "column": q["column"], "failed_rows": q["rows"],
                     "proposal": q["proposal"], "why": q["why"]} for q in part.get("quality") or []],
    }
