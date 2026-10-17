"""The silver table spec (findings spec section 6): numbers, identifiers, and material commentary.

Profiling writes it for each part; the catalog summary rebuilds it for findings
approved before every part had one.
"""

from __future__ import annotations

import hashlib

from . import profile

SILVER_INTEGER = "BIGINT"  # count-derived integers are never narrower (CLAUDE.md, schema conventions)

# How each class lands in silver, and why (findings spec section 6).
LOAD = {
    "transaction": ("append", "events are appended and never changed"),
    "reference": ("snapshot", "a published code-set version replaces the previous one"),
    "master": ("upsert", "a record keeps its key and its values change; MDM masters it, silver keeps the source's copy"),
    "relationship": ("upsert", "a link keeps its key and its dates change"),
    "metadata": ("upsert", "a delivery's own facts change only when the delivery is corrected"),
    "silver": ("append", "numbers and identifiers kept for silver"),
}


IDENTIFYING_ROLES = {"link", "code", "identifier", "name", "date"}


def keep(column: dict, role: str, key_columns: list[str]) -> bool:
    """A silver field is a number, an identifier, or material commentary.

    Commentary is text that is not an identifier. It is material when it is
    filled on at least half the rows, takes at least two values, and its most
    common value is under nine tenths of the filled rows.
    """
    if column["name"] in key_columns:
        return True
    if role in IDENTIFYING_ROLES:
        return True
    if role == "measure" or profile.is_numeric(column) or profile.is_temporal(column):
        return column.get("fill", 0) > 0
    commentary = role == "text" or (profile.is_text(column) and column.get("tokens", 0) > 6)
    if not commentary:
        return column.get("fill", 0) > 0
    if column.get("fill", 0) < 0.5 or column.get("distinct", 0) < 2:
        return False
    top = column.get("top") or []
    non_null = column.get("non_null") or 0
    if top and non_null and top[0]["rows"] / non_null >= 0.9:
        return False
    return True


def spec(f: dict, relationships: list[dict], parts: dict) -> dict:
    """The silver table spec (findings spec section 6): numbers, identifiers, and
    material commentary. Links point to masters only: a link to another transaction or reference
    part stays a relationship finding. A master part with a one-column key also links to
    itself, so each row carries its own MDM id. Each link's kind and Dataset Contract are
    filled by data-onboarding."""
    links = [r for r in relationships if r["from"]["part"] == f["part"]
             and parts.get(r["to"]["part"], {}).get("class") == "master"]
    key = f["record_key"]["columns"]
    if f["class"] == "master" and len(key) == 1:
        links = [{"from": {"part": f["part"], "columns": key}, "to": {"part": f["part"], "columns": key},
                  "inclusion": 1.0, "self": True}, *links]
    taken = [r["from"]["columns"][0] for r in links]

    columns = [c for c in f["columns"] if c.get("silver_field", True)]

    def id_column(r):
        column = r["from"]["columns"][0]
        if r.get("self"):  # the row's own MDM id, under a name no source column takes
            name = "mdm_id" if "mdm_id" not in {c["name"] for c in f["columns"]} else f"{f['part']}_mdm_id"
        else:
            name = f"{column}_mdm_id" if taken.count(column) == 1 else f"{column}_{r['to']['part']}_mdm_id"
        if len(name.encode()) <= 63:  # PostgreSQL's longest name
            return name
        short = hashlib.sha256(name.encode()).hexdigest()[:8]
        return f"{column.encode()[:40].decode(errors='ignore')}_{short}_mdm_id"

    return {
        "table": f["part"].replace(".", "_").lower(),
        "grain": f"one row per {' + '.join(f['record_key']['columns'])}",
        "columns": [{"name": c["name"], "type": SILVER_INTEGER if c["type"] in profile.INTEGERS else c["type"],
                     "nullable": c["fill"] < 1.0, "definition": None,
                     "source": f"{f['part']}.{c['name']}", "sensitivity": c["sensitivity"]} for c in columns],
        "key": f["record_key"]["columns"],
        "links": [{"columns": r["from"]["columns"], "kind": None, "source_code": None, "to_part": r["to"]["part"],
                   "source_key": r["from"]["columns"][0], "mdm_id_column": id_column(r),
                   "inclusion": r["inclusion"]} for r in links],
        "time": {"as_of": f["time"]["as_of"]["from"], "as_at": f["time"]["as_at"] or "loaded_at",
                 "event_time": f["time"]["event_time"]},
        "partition": [f["time"]["event_time"]] if f["time"]["event_time"] else [],
        "load_mode": LOAD[f["class"]][0],
        "why": LOAD[f["class"]][1],
    }
