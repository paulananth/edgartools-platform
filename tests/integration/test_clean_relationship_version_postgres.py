"""Real PG16: mdm.relationship_version and `context relationship --as-at` (profiling ticket 05b).

Every recorded state of a relationship is kept, one row per change; the walk at
a past recording time reads the versions open at that generation. Migration 010
back-fills the history of a store that already holds batches.
"""

from __future__ import annotations

from sqlalchemy import text

from tests.integration import test_clean_entity_context_postgres as entity_context
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_entity_context_postgres import DIRECT, ask, company, rows

postgres = core.postgres
database = core.database


def moved_parent(database):
    """c's parent is b in generation 1; c's revision 2 names a instead."""
    ids = entity_context.load_group(database)
    (first,) = rows(database, "SELECT created_at FROM mdm.batch WHERE generation = 1")
    moved = company("c", {"subject": core.source("a")["subject"]}, revision=2)
    core.apply(database, 2, assertions=[moved])
    return ids, first["created_at"]


def parents(answer, child):
    return {r["to"]["name"] for r in answer["related"]
            if r["from"]["entity_id"] == child and r["type"] == DIRECT and not r.get("derived")}


def test_every_change_is_one_version_and_an_unchanged_link_writes_none(database):
    ids, _ = moved_parent(database)
    versions = rows(database, """SELECT relationship_id, from_generation, to_generation, valid_from, valid_to,
                                        source_id, target_id, type, body
                                   FROM mdm.relationship_version ORDER BY relationship_id, from_generation""")
    current = {r["object_id"]: r["body"] for r in rows(
        database, "SELECT object_id, body FROM mdm.current_record WHERE object_type = 'relationship'")}
    # The open version of every relationship is its current state.
    assert {v["relationship_id"]: v["body"] for v in versions if v["to_generation"] is None} == current
    for v in versions:
        assert (v["source_id"], v["target_id"], v["type"]) == (
            v["body"].get("source_id"), v["body"].get("target_id"), v["body"].get("type"))
        assert (v["to_generation"] is None) == (v["valid_to"] is None)
    # b -> a did not change in generation 2: one version only.
    b_to_a = [v for v in versions if v["source_id"] == ids["b"] and v["type"] == DIRECT]
    assert [(v["from_generation"], v["to_generation"]) for v in b_to_a] == [(1, None)]
    # c -> b changed (retired, or its period closed): closed at generation 2.
    c_to_b = [v for v in versions if (v["source_id"], v["target_id"], v["type"]) == (ids["c"], ids["b"], DIRECT)]
    assert c_to_b[0]["from_generation"] == 1 and c_to_b[0]["to_generation"] == 2
    assert c_to_b[0]["valid_to"] == c_to_b[1]["valid_from"]


def test_as_at_reads_the_links_recorded_by_then(database):
    ids, first_recorded = moved_parent(database)
    now = ask(database, "relationship", ids["c"])
    assert parents(now, ids["c"]) == {"Company a"}
    then = ask(database, "relationship", ids["c"], as_at=first_recorded.isoformat())
    assert parents(then, ids["c"]) == {"Company b"}
    assert then["trust"]["generation"] == 1 and "names are as MDM holds them now" in then["trust"]["note"]
    # The entity lookup lists the same links at that time.
    entity = ask(database, "company", ids["c"], as_at=first_recorded.isoformat())
    assert {r["to"]["name"] for r in entity["related"] if r["type"] == DIRECT and not r.get("derived")
            and r["from"]["entity_id"] == ids["c"]} == {"Company b"}


def test_the_migration_back_fills_a_populated_store(database):
    from edgar_warehouse.mdm.clean.store import migrate

    moved_parent(database)
    before = rows(database, """SELECT relationship_id, from_generation, to_generation, body
                                 FROM mdm.relationship_version ORDER BY relationship_id, from_generation""")
    assert len(before) > len(rows(database, "SELECT 1 FROM mdm.current_record WHERE object_type = 'relationship'"))
    with database.admin.begin() as conn:
        conn.execute(text("DROP TRIGGER keep_relationship_version ON mdm.current_record"))
        conn.execute(text("DROP FUNCTION mdm.keep_relationship_version()"))
        conn.execute(text("DROP FUNCTION mdm.record_relationship_version(text, jsonb, text)"))
        conn.execute(text("DROP TABLE mdm.relationship_version"))
        # The migration ledger is append-only; only this simulation of an older
        # store goes around that, as the database owner.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM mdm.migration WHERE name = '010_relationship_version.sql'"))
        conn.execute(text("SET LOCAL session_replication_role = origin"))
    migrate(database.admin, application_role="clean_application")
    after = rows(database, """SELECT relationship_id, from_generation, to_generation, body
                                FROM mdm.relationship_version ORDER BY relationship_id, from_generation""")
    assert after == before
    # The trigger is back: c's revision 3 names b again, a new version.
    core.apply(database, 3, assertions=[company("c", {"subject": core.source("b")["subject"]}, revision=3)])
    assert len(rows(database, "SELECT 1 FROM mdm.relationship_version")) > len(after)
