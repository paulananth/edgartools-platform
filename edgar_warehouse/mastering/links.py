"""The links stored records state, calculated after mastering from current masters.

Links stay out of the merge. Each run calculates all of them, so a link waiting for its other end
appears once that end is mastered and needs no stored queue.
"""

from __future__ import annotations

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


def build(silver, mdm, policy_digest: str, as_of: str) -> dict:
    """The links table, built whole from the stored records as they are now, once a load's merges are done. A link
    keeps the start the last build gave it."""
    from edgar_warehouse.mastering.store import open_store
    from edgar_warehouse.rules import registry
    from edgar_warehouse.silver_writer.relational import DatabaseSink
    from edgar_warehouse.silver_writer.writer import land

    rules = registry.engine()
    try:
        with rules.connect() as conn:
            policy = registry.policy(conn, policy_digest)
    finally:
        rules.dispose()
    if policy is None:
        raise ValueError("The merge policy of the rules files is not registered: load or register a source first")
    with silver.connect() as conn:
        last = [dict(row._mapping) for row in conn.execute(text('select * from silver."relationship"'))]
    db = open_store(mdm)
    try:
        edges, waiting = calculate(db, policy, as_of, stored_of(last))
    finally:
        db.close()
    tables = rows_of(edges)
    db = open_store(mdm)
    try:
        bindings = [{"source_code": code, "source_key": key, "kind": kind, "master_id": entity}
                    for code, key, kind, entity in db.bindings()]
    finally:
        db.close()
    sink = DatabaseSink(silver)
    for table in ("relationship", "relationship_evidence", "relationship_path"):
        land(sink, table, tables[table])
    land(sink, "master_binding", bindings)
    return {"table": "relationship", "links": len(edges), "rows": len(tables["relationship"]),
            "bindings": len(bindings), "waiting": dict(sorted(waiting.items()))}


PROPERTIES = ("source_event_type", "source_event_status", "source_entity_status", "source_relationship_status",
              "source_registration_status", "source_start_date_basis", "source_start_date_is_provisional")


def rows_of(edges: list[dict]) -> dict[str, list[dict]]:
    """The silver rows of the links: one row for each period of each link, the stored records that state each
    link once, and each calculated period's chain one step a row."""
    links, evidence, path = [], {}, []
    for edge in edges:
        for assertion in sorted(item["assertion_id"] for item in edge["evidence"]):
            evidence[(edge["relationship_id"], assertion)] = {
                "relationship_type": edge["type"], "relationship_id": edge["relationship_id"], "assertion_id": assertion}
        for period in edge["periods"]:
            declared = period.get("properties") or {}
            if set(declared) - set(PROPERTIES):
                raise ValueError(f"a relationship property no silver column holds: {sorted(set(declared) - set(PROPERTIES))}")
            links.append({"relationship_id": edge["relationship_id"], "relationship_type": edge["type"],
                          "scope": edge["scope"], "source_master_id": edge["source_id"],
                          "target_master_id": edge["target_id"], "valid_from": period["valid_from"],
                          "valid_from_basis": period["valid_from_basis"], "valid_to": period.get("valid_to"),
                          "valid_to_basis": period.get("valid_to_basis"), "capacity": edge.get("capacity"),
                          "derived": bool(edge.get("derived")), "last_seen": edge.get("last_seen"),
                          "ended_by": period.get("ended_by")}
                         | {name: declared.get(name) for name in PROPERTIES})
            for position, step in enumerate(period.get("path") or [], 1):
                path.append({"relationship_type": edge["type"], "relationship_id": edge["relationship_id"],
                             "valid_from": period["valid_from"], "position": position, "step_relationship_id": step})
    return {"relationship": links, "relationship_evidence": list(evidence.values()), "relationship_path": path}


def around(silver, ids: list[str], relationship_type: str = "") -> list[dict]:
    """The links touching these masters, each with all its periods."""
    names = {f"id{number}": entity for number, entity in enumerate(ids)}
    marks = ",".join(f":{name}" for name in names)
    wanted = f"(source_master_id in ({marks}) or target_master_id in ({marks}))"
    if relationship_type:
        wanted += " and relationship_type=:relationship_type"
        names["relationship_type"] = relationship_type
    links: dict = {}
    periods: dict = {}
    for row in silver.execute(text(f"select * from silver.relationship where {wanted}"), names).mappings():
        link = links.setdefault(row["relationship_id"], {
            "relationship_id": row["relationship_id"], "type": row["relationship_type"], "scope": row["scope"],
            "source_id": row["source_master_id"], "target_id": row["target_master_id"], "capacity": row["capacity"],
            "derived": row["derived"], "last_seen": row["last_seen"], "evidence": [], "periods": []})
        period = {key: row[key] for key in ("valid_from", "valid_from_basis", "valid_to", "ended_by")} | {"path": None}
        link["periods"].append(period)
        periods[(row["relationship_id"], row["valid_from"])] = period
    if links:
        found = {f"link{number}": key for number, key in enumerate(links)}
        marks = ",".join(f":{name}" for name in found)
        for row in silver.execute(text("select relationship_id, assertion_id from silver.relationship_evidence "
                                       f"where relationship_id in ({marks}) order by relationship_id, assertion_id"),
                                  found).mappings():
            links[row["relationship_id"]]["evidence"].append(row["assertion_id"])
        for row in silver.execute(text("select relationship_id, valid_from, step_relationship_id "
                                       f"from silver.relationship_path where relationship_id in ({marks}) "
                                       "order by relationship_id, valid_from, position"), found).mappings():
            period = periods.get((row["relationship_id"], row["valid_from"]))
            if period is not None:  # a chain whose period the table no longer holds is not read
                period["path"] = [*(period["path"] or []), row["step_relationship_id"]]
    return [links[key] for key in sorted(links)]


def stored_of(rows) -> dict:
    """The links of the last run, in the form `calculate` takes. A source rule declares the same properties for
    every period of its scope, an empty one as null: those are the names some period of the scope fills."""
    rows = list(rows)
    declared: dict = {}
    for row in rows:
        declared.setdefault((row["relationship_type"], row["scope"]), set()).update(
            name for name in PROPERTIES if row[name] is not None)
    found = {}
    for row in rows:
        names = declared[(row["relationship_type"], row["scope"])]
        period = {"valid_from": row["valid_from"], "valid_from_basis": row["valid_from_basis"],
                  "valid_to": row["valid_to"], "valid_to_basis": row["valid_to_basis"],
                  "properties": {name: row[name] for name in PROPERTIES if name in names}}
        if period["valid_to_basis"] is None:
            del period["valid_to_basis"]
        found.setdefault(row["relationship_id"], {"periods": []})["periods"].append(period)
    return found
