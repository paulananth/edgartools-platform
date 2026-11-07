"""What readers ask of the masters: a source key's master, a master by id, the masters carrying an identifier."""

from __future__ import annotations

from edgar_warehouse.mdm.evidence import subject_key
from edgar_warehouse.mdm.primitives import prepare_matching_value

from . import lookups


def master_ids(store, source_code: str, keys) -> dict:
    """Each source key's current master; a key with no master is left out. A source gives one kind."""
    subjects = {subject_key(source_code, key): key for key in keys}
    return {subjects[subject]: entity for subject, entity in store.bound(subjects).items()}


def master(store, requested: str) -> dict:
    """The current master behind an id: a merged-away id answers with the master it joined."""
    key, seen = requested, set()
    while key not in seen:
        seen.add(key)
        body = store.master_bodies([key]).get(key)
        if body is None:
            raise KeyError(requested)
        if body["canonical_id"] == key:
            return body
        key = body["canonical_id"]
    raise ValueError(f"Merged masters point at each other: {requested}")


def carriers(store, policy: dict, kind: str | None, namespace: str, value: str) -> dict:
    """The masters carrying `namespace:value`, each marked as an identifier or a cross-reference (lookup only)."""
    values = {value} if value else set()
    for block in policy["kinds"].values():
        contract = block.get("identifiers", {}).get(namespace)
        normalized = prepare_matching_value(contract["normalizer"], value, block) if contract else None
        if normalized:
            values.add(normalized)
    found = {entity: "identifier" for entity in (store.identifier_holders(namespace, sorted(values)) if values else [])}
    found = found or {entity: "cross_reference" for entity in lookups.cross_referencing(store, namespace, value)}
    bodies = store.master_bodies(found)
    return {entity: how for entity, how in found.items() if kind is None or bodies[entity]["kind"] == kind}


def splits_of(store, entity: str) -> list[dict]:
    """The splits a master came out of: each merge of it with another master that was later reversed.
    Each is also a Match Exclusion of the pair."""
    decisions = store.decisions_about([entity])
    reversed_by = {d["target"]: d for d in decisions if d["operation"] == "reverse"}
    found = [{"merge": d["decision_id"], "split_from": d["right"] if d["left"] == entity else d["left"],
              "by": reversed_by[d["decision_id"]]["actor"], "reason": reversed_by[d["decision_id"]]["reason"],
              "at": reversed_by[d["decision_id"]]["at"], "excluded": True}
             for d in decisions if d["operation"] == "merge" and d["decision_id"] in reversed_by]
    return sorted(found, key=lambda item: (item["at"], item["merge"]))
