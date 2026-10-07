"""Real PG16: mdm.relationship_context and mdm.relationship_chain (profiling ticket 04).

Relationships come back with both ends named, their role and their dates, one
row per period; the chain of direct parents ends at the ultimate parent the
source states, and a planted entity whose chain does not is caught; a cycle
stops the walk; the hop limit holds.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_clean_person_links_postgres as person_links

postgres = core.postgres
database = core.database

DIRECT, ULTIMATE = "IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY"


def link(kind, target, **more):
    return {"type": kind, "target_subject": target["subject"], "valid_from": core.AT, "valid_to": None,
            "scope": "consolidated", **more}


def load(database, links: dict[str, list[tuple[str, str]]]):
    """Companies named by key; `links` maps a child key to its (type, parent key) links."""
    keys = sorted({k for k in links} | {p for pairs in links.values() for _, p in pairs})
    plain = {k: core.source(k, fields={"name": f"Company {k}"}) for k in keys}
    records = [core.source(k, fields={"name": f"Company {k}"},
                           relationships=[link(kind, plain[p]) for kind, p in links.get(k, [])]) for k in keys]
    pairs = [core.identity_and_binding(r) for r in records]
    core.apply(database, 1, assertions=records, identities=[i for i, _ in pairs], decisions=[d for _, d in pairs])
    return {r["record_key"]: i["entity_id"] for r, (i, _) in zip(records, pairs)}


def rows(database, sql, **params):
    with database.application.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def chain(database, entity, kind=DIRECT, hops=10):
    return rows(database, "SELECT * FROM mdm.relationship_chain(:e, :t, :h)", e=entity, t=kind, h=hops)


def test_relationships_come_back_named_with_their_dates_and_sources(database):
    ids = load(database, {"a": [(DIRECT, "b")], "b": [(DIRECT, "c")]})
    found = rows(database, "SELECT * FROM mdm.relationship_context WHERE type = :t ORDER BY from_name", t=DIRECT)
    assert [(r["from_name"], r["to_name"], r["from_kind"], r["to_kind"]) for r in found] == [
        ("Company a", "Company b", "company", "company"), ("Company b", "Company c", "company", "company")]
    first = found[0]
    assert first["from_entity_id"] == ids["a"] and first["period"] == 1 and first["valid_to"] is None
    assert first["valid_from"] is not None and first["scope"] == "consolidated" and not first["derived"]
    assert first["sources"] == [{"source_code": "fixture.primary", "record_key": "a"}]
    assert first["valid_from_basis"] == "stated" and first["ended_by"] is None
    # The engine derives each record's ultimate parent from the direct chain.
    # This fixture's policy has no types section, so it runs accounting-chain-v1:
    # calculated, with no dates (v2's history: test_fresh_mastering_postgres).
    derived = rows(database, "SELECT * FROM mdm.relationship_context WHERE derived")
    assert {(r["from_name"], r["to_name"]) for r in derived} == {("Company a", "Company c"), ("Company b", "Company c")}
    assert all(r["valid_from"] is None and r["period"] is None and r["basis"] == "calculated" for r in derived)


def test_a_person_link_comes_back_with_its_role_and_observed_start(database):
    person, issuer, _ = person_links.setup(database)
    person_links.apply(database, 2, assertions=[
        person_links.filing(1, person, issuer, person_links.sighting(person_links.D1, "director"))])
    (row,) = rows(database, "SELECT * FROM mdm.relationship_context WHERE type = 'EMPLOYED_BY'")
    assert row["role"] == "director" and row["from_kind"] == "person" and row["to_kind"] == "company"
    assert row["valid_from_basis"] == "observed" and row["to_name"]


def ultimate_mismatches(database, ids):
    """Each entity whose direct-parent chain does not end at the ultimate parent the source states."""
    stated = {r["from_entity_id"]: r["to_entity_id"] for r in rows(
        database, "SELECT from_entity_id, to_entity_id FROM mdm.relationship_context WHERE type = :t", t=ULTIMATE)}
    found = []
    for entity, ultimate in sorted(stated.items()):
        walked = chain(database, entity)
        end = walked[-1]["to_entity_id"] if walked else None
        if end != ultimate:
            found.append((entity, end, ultimate))
    return found


def test_the_direct_chain_ends_at_the_stated_ultimate_parent_and_a_planted_mismatch_is_caught(database):
    ids = load(database, {
        "a": [(DIRECT, "b"), (ULTIMATE, "d")], "b": [(DIRECT, "c"), (ULTIMATE, "d")], "c": [(DIRECT, "d"), (ULTIMATE, "d")],
        # Planted: x's direct parent is y, but the source states z as its ultimate parent.
        "x": [(DIRECT, "y"), (ULTIMATE, "z")],
    })
    assert [r["to_entity_id"] for r in chain(database, ids["a"])] == [ids["b"], ids["c"], ids["d"]]
    assert ultimate_mismatches(database, ids) == [(ids["x"], ids["y"], ids["z"])]


def test_the_hop_limit_holds(database):
    ids = load(database, {"a": [(DIRECT, "b")], "b": [(DIRECT, "c")], "c": [(DIRECT, "d")]})
    assert [r["depth"] for r in chain(database, ids["a"], hops=2)] == [1, 2]
    assert [r["depth"] for r in chain(database, ids["a"], hops=500)] == [1, 2, 3]  # capped at 50, ends at d
    assert chain(database, ids["a"], hops=0) == []
    assert {r["scope"] for r in chain(database, ids["a"])} == {"consolidated"}


def test_a_cycle_ends_the_walk(database):
    # Ownership-parent cycles are mastered and reviewed, not held back, so the chain meets one.
    ids = load(database, {"p": [("OWNERSHIP_PARENT", "q")], "q": [("OWNERSHIP_PARENT", "p")]})
    walked = chain(database, ids["p"], kind="OWNERSHIP_PARENT")
    assert [(r["to_entity_id"], r["cycle"]) for r in walked] == [(ids["q"], False), (ids["p"], True)]


def test_a_populated_store_at_005_takes_006_and_keeps_its_rows(database):
    from edgar_warehouse.mdm.clean.store import migrate

    load(database, {"a": [(DIRECT, "b")]})
    with database.admin.begin() as conn:
        # 007 builds on 006: a store at 005 has neither.
        conn.execute(text("DROP FUNCTION mdm.entity_search(text, text, integer)"))
        conn.execute(text("DROP VIEW mdm.entity_context"))
        conn.execute(text("DROP INDEX mdm.stage_record_identifiers, mdm.current_record_entity_name_search, "
                          "mdm.company_name_search"))
        conn.execute(text("DROP FUNCTION mdm.relationship_chain(text, text, integer, timestamp with time zone)"))
        conn.execute(text("DROP FUNCTION mdm.relationship_holds(jsonb, timestamp with time zone)"))
        conn.execute(text("DROP VIEW mdm.relationship_context"))
        conn.execute(text("DROP FUNCTION mdm.entity_name(jsonb)"))
        # The migration ledger is append-only; only this simulation of an older
        # store goes around that, as the database owner.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM mdm.migration WHERE name IN "
                          "('006_relationship_context.sql', '007_entity_context.sql', '008_relationship_names.sql', "
                          "'009_parent_history.sql')"))
        conn.execute(text("SET LOCAL session_replication_role = origin"))
        count = conn.scalar(text("SELECT count(*) FROM mdm.current_record"))
    migrate(database.admin, application_role="clean_application")
    assert rows(database, "SELECT from_name, to_name FROM mdm.relationship_context WHERE NOT derived") == [
        {"from_name": "Company a", "to_name": "Company b"}]
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.current_record")) == count


def test_a_populated_store_at_007_takes_008_and_009_and_each_link_says_its_basis(database):
    """Profiling ticket 04b: the view's basis column, stated or calculated, and
    the succession that ended a period, on a store holding links."""
    from edgar_warehouse.mdm.clean import store
    from edgar_warehouse.mdm.clean.store import migrate

    load(database, {"a": [(DIRECT, "b")]})
    view_at_007 = (Path(store.__file__).parents[1] / "migrations" / "006_relationship_context.sql").read_text()
    view_at_007 = view_at_007[view_at_007.index("CREATE VIEW mdm.relationship_context"):]
    view_at_007 = view_at_007[:view_at_007.index(";") + 1]
    with database.admin.begin() as conn:
        conn.execute(text("DROP VIEW mdm.relationship_context"))
        conn.execute(text(view_at_007))
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM mdm.migration WHERE name IN ('008_relationship_names.sql', "
                          "'009_parent_history.sql')"))
        conn.execute(text("SET LOCAL session_replication_role = origin"))
        count = conn.scalar(text("SELECT count(*) FROM mdm.current_record"))
    migrate(database.admin, application_role="clean_application")
    found = {(r["derived"], r["basis"]) for r in rows(database, "SELECT derived, basis FROM mdm.relationship_context")}
    assert (False, "stated") in found and found <= {(False, "stated"), (True, "calculated")}
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.current_record")) == count
        assert conn.scalar(text("SELECT col_description('mdm.relationship_context'::regclass, "
                                "(SELECT attnum FROM pg_attribute WHERE attrelid = 'mdm.relationship_context'::regclass "
                                "AND attname = 'basis'))")).startswith("stated")
        assert conn.scalar(text("SELECT col_description('mdm.relationship_context'::regclass, "
                                "(SELECT attnum FROM pg_attribute WHERE attrelid = 'mdm.relationship_context'::regclass "
                                "AND attname = 'ended_by'))")).startswith("The succession")
