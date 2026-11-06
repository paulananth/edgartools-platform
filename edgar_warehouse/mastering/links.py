"""The links stored records state, calculated after mastering from current masters.

Links stay out of the merge. Each run calculates all of them, so a link waiting for its other end
appears once that end is mastered and needs no stored queue.
"""

from __future__ import annotations

import json
from collections import Counter
from types import SimpleNamespace

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
    masters = store.master_bodies(sorted(set(bound.values())))
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
             "properties": period.get("properties") or {},
             "evidence": sorted(item["assertion_id"] for item in edge["evidence"])}
            for edge in edges for period in edge["periods"]]


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
