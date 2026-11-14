"""The links stored records state, calculated after mastering from current masters.

Links stay out of the merge. Each run calculates all of them, so a link waiting for its other end
appears once that end is mastered and needs no stored queue.
"""

from __future__ import annotations

import json
from collections import Counter
from types import SimpleNamespace

from sqlalchemy import text

from edgar_warehouse.mdm import relationships
from edgar_warehouse.mdm.survivorship import current_claims


def _ends(claims: dict) -> list[str]:
    found = set(claims)
    for subject, claim in claims.items():
        for link in claim["relationships"]:
            found.add(link.get("source_subject") or subject)
            if link.get("target_subject"):
                found.add(link["target_subject"])
    return sorted(found)


def calculate(store, policy: dict, as_of: str, stored: dict) -> tuple[list[dict], Counter]:
    """Every link, and how many reported links have no result yet, by reason. `stored` holds the links
    of the last run by id, so a link keeps a start its current record no longer shows."""
    claims = current_claims(store.linked_records(), as_of, set())
    bound = store.bound(_ends(claims))
    masters = store.master_states(sorted(set(bound.values())))
    store.commit()
    state = SimpleNamespace(bindings=bound, canonical={entity: entity for entity in bound.values()})
    edges, reviews = relationships.project(claims, state, masters, as_of,
                                           types=relationships.types_of(policy), stored=stored)
    return edges, Counter(review["reason"] for review in reviews)


def rows_of(edges: list[dict]) -> list[dict]:
    """One silver row for each period of each link."""
    return [{"relationship_id": edge["relationship_id"], "relationship_type": edge["type"], "scope": edge["scope"],
             "source_master_id": edge["source_id"], "target_master_id": edge["target_id"],
             "valid_from": period["valid_from"], "valid_from_basis": period["valid_from_basis"],
             "valid_to": period.get("valid_to"), "valid_to_basis": period.get("valid_to_basis"),
             "capacity": edge.get("capacity"), "derived": bool(edge.get("derived")), "last_seen": edge.get("last_seen"),
             "ended_by": period.get("ended_by"), "path": period.get("path"),
             "properties": period.get("properties") or {},
             "evidence": sorted(item["assertion_id"] for item in edge["evidence"])}
            for edge in edges for period in edge["periods"]]


def around(silver, ids: list[str], relationship_type: str = "") -> list[dict]:
    """The links touching these masters, each with all its periods."""
    names = {f"id{number}": entity for number, entity in enumerate(ids)}
    marks = ",".join(f":{name}" for name in names)
    wanted = f"(source_master_id in ({marks}) or target_master_id in ({marks}))"
    if relationship_type:
        wanted += " and relationship_type=:relationship_type"
        names["relationship_type"] = relationship_type
    links: dict = {}
    for row in silver.execute(text(f"select * from silver.relationship where {wanted}"), names).mappings():
        link = links.setdefault(row["relationship_id"], {
            "relationship_id": row["relationship_id"], "type": row["relationship_type"], "scope": row["scope"],
            "source_id": row["source_master_id"], "target_id": row["target_master_id"], "capacity": row["capacity"],
            "derived": row["derived"], "last_seen": row["last_seen"], "evidence": _json(row["evidence"]), "periods": []})
        link["periods"].append({key: row[key] for key in ("valid_from", "valid_from_basis", "valid_to", "ended_by")}
                               | {"path": _json(row["path"])})
    return [links[key] for key in sorted(links)]


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def stored_of(rows) -> dict:
    """The links of the last run, in the form `calculate` takes."""
    found = {}
    for row in rows:
        period = {"valid_from": row["valid_from"], "valid_from_basis": row["valid_from_basis"],
                  "valid_to": row["valid_to"], "valid_to_basis": row["valid_to_basis"],
                  "properties": json.loads(row["properties"]) if isinstance(row["properties"], str) else row["properties"]}
        if period["valid_to_basis"] is None:
            del period["valid_to_basis"]
        found.setdefault(row["relationship_id"], {"periods": []})["periods"].append(period)
    return found
