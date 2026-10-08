"""Real PG16: mdm.entity_context and the `context` command (profiling ticket 05).

Entities come back named, with each value's winning source, their identifiers,
their cross-reference ids kept apart, and their source records; the view
agrees with the version-2 reader; lookups by id and by any identifier, name
search, the two times and the relationship walk each answer in at most 8 KB.
"""

from __future__ import annotations

import argparse
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.context import LIMIT_BYTES, Context, ContextError
from edgar_warehouse.mdm.clean.consumer import ContractReader
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store
from tests.integration import test_clean_mdm_postgres as core
from tests.integration import test_clean_person_links_postgres as person_links

postgres = core.postgres
database = core.database

DIRECT = "IS_DIRECTLY_CONSOLIDATED_BY"


def args(subject, key=None, **more):
    base = dict(search=None, limit=5, as_of=None, as_at=None, hops=1, relationship_type="", detail="brief", page=None)
    return argparse.Namespace(subject=subject, key=key, **{**base, **more})


def ask(database, subject, key=None, **more):
    answer = Context(database.application).answer(args(subject, key, **more))
    assert len(json.dumps(answer, ensure_ascii=False).encode()) <= LIMIT_BYTES
    return answer


def rows(database, sql, **params):
    with database.application.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def company(key, parent=None, **more):
    relationships = [{"type": DIRECT, "target_subject": parent["subject"], "valid_from": core.AT,
                      "valid_to": None, "scope": "consolidated"}] if parent else []
    return core.source(key, fields={"name": f"Company {key}", "description": f"About {key}"},
                       identifiers={"cik": f"000000{key}"}, relationships=relationships, **more)


def load_group(database):
    """Three companies in a parent chain (c -> b -> a), one with a tax cross-reference."""
    a = company("a")
    b = company("b", a, cross_references={"tax": "12-3"})
    c = company("c", b)
    records = [a, b, c]
    pairs = [core.identity_and_binding(r) for r in records]
    core.apply(database, 1, assertions=records, identities=[i for i, _ in pairs], decisions=[d for _, d in pairs])
    return {r["record_key"]: i["entity_id"] for r, (i, _) in zip(records, pairs)}


def test_an_entity_comes_back_named_with_sources_identifiers_and_cross_references_apart(database):
    ids = load_group(database)
    (row,) = rows(database, "SELECT * FROM mdm.entity_context WHERE entity_id = :e", e=ids["b"])
    assert row["name"] == "Company b" and row["kind"] == "company" and row["status"] == "accepted"
    assert row["fields"]["name"] == {"value": "Company b", "source_code": "fixture.primary", "record_key": "b"}
    assert row["identifiers"] == {"cik": ["000000b"]}
    assert row["cross_references"] == {"tax": ["12-3"]}
    assert row["sources"] == {"fixture.primary": ["b"]}
    assert row["valid_from"] is not None and row["valid_to"] is None and row["published_at"] is not None


def test_a_person_comes_back_from_the_entity_rows(database):
    _, _, (person_id, _) = person_links.setup(database)
    (row,) = rows(database, "SELECT * FROM mdm.entity_context WHERE entity_id = :e", e=person_id)
    # The fixture policy masters no person fields, so the person has no name yet.
    assert row["kind"] == "person" and row["name"] is None and row["fields"] == {}
    assert row["sources"] == {"fixture.primary": ["owner"]}


def test_the_view_agrees_with_the_reader(database):
    load_group(database)
    reader = ContractReader(database.application)
    for row in rows(database, "SELECT entity_id, name, identifiers, fields FROM mdm.entity_context"):
        body = reader.entity(row["entity_id"])["identity"]
        assert row["name"] == body["fields"]["name"]["value"]
        assert row["identifiers"] == body["identifiers"]
        expected = {name: {"value": f.get("value"), "source_code": f["winner"]["source_code"],
                           "record_key": f["winner"]["record_key"]}
                    for name, f in body["fields"].items() if not f.get("cleared")}
        assert row["fields"] == expected


def test_every_column_of_every_context_view_says_what_it_holds(database):
    found = rows(database, """
        SELECT c.relname AS view, a.attname AS column, col_description(c.oid, a.attnum) AS comment,
               obj_description(c.oid, 'pg_class') AS view_comment
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
         WHERE n.nspname = 'mdm' AND c.relname IN ('entity_context', 'relationship_context', 'cross_reference')""")
    assert {r["view"] for r in found} == {"entity_context", "relationship_context", "cross_reference"}
    assert [(r["view"], r["column"]) for r in found if not r["comment"] or not r["view_comment"]] == []


def test_lookup_by_id_and_by_any_identifier(database):
    ids = load_group(database)
    by_id = ask(database, "company", ids["b"])
    assert list(by_id)[0] == "name" and by_id["name"] == "Company b"
    assert by_id["definition"] and by_id["trust"]["generation"] == 1 and by_id["trust"]["policy_digest"]
    assert {"field": "name", "value": "Company b", "source": "fixture.primary"} in by_id["fields"]
    assert by_id["cross_references"] == {"tax": ["12-3"]} and by_id["identifiers"] == {"cik": ["000000b"]}
    stated = {(r["from"]["name"], r["to"]["name"]) for r in by_id["related"] if not r.get("derived")}
    assert stated == {("Company b", "Company a"), ("Company c", "Company b")} and by_id["related_count"] >= 2
    assert ask(database, "company", "cik:000000b")["entity_id"] == ids["b"]
    # A cross-reference id finds the record too, for lookup only.
    assert ask(database, "company", "tax:12-3")["entity_id"] == ids["b"]
    with pytest.raises(ContextError) as missing:
        ask(database, "company", "cik:999")
    assert "--search" in missing.value.command
    with pytest.raises(ContextError) as wrong_kind:
        ask(database, "person", ids["b"])
    assert wrong_kind.value.command.endswith(f"company {ids['b']}")


def test_search_finds_words_then_falls_back_to_contains_and_logs_a_miss(database, capsys):
    ids = load_group(database)
    words = ask(database, "company", search="company b")
    assert [(m["entity_id"], m["matched_by"]) for m in words["matches"]][:1] == [(ids["b"], "words")]
    contains = ask(database, "company", search="ompany")
    assert {m["matched_by"] for m in contains["matches"]} == {"contains"} and len(contains["matches"]) == 3
    assert words["trust"]["generation"] == 1
    assert ask(database, "company", search="nothing like it")["matches"] == []
    assert "context-search-miss" in capsys.readouterr().err
    assert ask(database, "person", search="company")["matches"] == []


def apply_at(database, n, as_of, **kw):
    return MergeStage(Store(database.application)).apply(
        batch_id=f"work-{n}", run_id=str(uuid4()), policy_digest=database.policy, consumer="fixture",
        expected_checkpoint=n - 1, checkpoint=n, as_of=as_of, **kw)


def test_as_at_and_as_of_read_the_version_of_that_time(database):
    first = core.source("x", fields={"name": "Old name"})
    identity, binding = core.identity_and_binding(first)
    apply_at(database, 1, "2026-03-01T00:00:00+00:00", assertions=[first], identities=[identity], decisions=[binding])
    (recorded,) = rows(database, "SELECT created_at FROM mdm.batch WHERE generation = 1")
    apply_at(database, 2, "2026-06-01T00:00:00+00:00",
             assertions=[core.source("x", revision=2, fields={"name": "New name"})])
    entity = identity["entity_id"]
    assert ask(database, "company", entity)["name"] == "New name"
    earlier = ask(database, "company", entity, as_at=recorded["created_at"].isoformat())
    assert earlier["name"] == "Old name" and earlier["trust"]["current_parts"] == ["cross_references", "sources", "related_names"]
    assert ask(database, "company", entity, as_of="2026-04-01T00:00:00+00:00")["name"] == "Old name"
    assert ask(database, "company", entity, as_of="2026-07-01T00:00:00+00:00")["name"] == "New name"
    with pytest.raises(ContextError):
        ask(database, "company", entity, as_of="2026-01-01T00:00:00+00:00")
    with pytest.raises(ContextError) as zoneless:
        ask(database, "company", entity, as_of="2026-04-01")
    assert "+00:00" in zoneless.value.command


def test_the_relationship_walk_goes_both_ways_up_to_the_hop_limit(database):
    ids = load_group(database)
    one = ask(database, "relationship", ids["b"])
    assert {(r["from"]["name"], r["to"]["name"]) for r in one["related"] if not r.get("derived")} == {
        ("Company b", "Company a"), ("Company c", "Company b")}
    assert one["definitions"][DIRECT]
    two = ask(database, "relationship", ids["c"], hops=2)
    assert {r["depth"] for r in two["related"]} == {1, 2}
    assert ("Company b", "Company a") in {(r["from"]["name"], r["to"]["name"]) for r in two["related"]}
    assert ask(database, "relationship", ids["c"], as_of="2025-01-01T00:00:00+00:00", relationship_type=DIRECT)["related"] == []
    with pytest.raises(ContextError):
        ask(database, "relationship", ids["c"], hops=4)
    with pytest.raises(ContextError):  # before MDM recorded anything
        ask(database, "relationship", ids["c"], as_at="2026-01-01T00:00:00+00:00")
    full = ask(database, "relationship", ids["b"], detail="full", relationship_type=DIRECT)
    assert all(r["scope"] == "consolidated" for r in full["related"] if not r.get("derived"))
    stated = [r for r in full["related"] if not r.get("derived")]
    assert {(r["from"]["name"], tuple(x["record_key"] for x in r["sources"])) for r in stated} == {
        ("Company b", ("b",)), ("Company c", ("c",))}
    assert one["trust"]["generation"] == 1 and one["trust"]["policy_digest"]


def test_a_long_answer_is_cut_at_a_whole_item_and_pages_on(database):
    parent = company("parent")
    children = [company(f"child-{i:02d}", parent) for i in range(60)]
    records = [parent, *children]
    pairs = [core.identity_and_binding(r) for r in records]
    core.apply(database, 1, assertions=records, identities=[i for i, _ in pairs], decisions=[d for _, d in pairs])
    parent_id = pairs[0][0]["entity_id"]
    first = ask(database, "relationship", parent_id, relationship_type=DIRECT)
    assert first["truncated"] and first["related_count"] == 60
    assert first["next_step"].endswith(f"--page {first['next_page']}")
    pages, page = [first], first
    while page["next_page"]:
        page = ask(database, "relationship", parent_id, relationship_type=DIRECT, page=page["next_page"])
        pages.append(page)
    shown = [r["from"]["name"] for p in pages for r in p["related"]]
    assert len(pages) > 1 and shown == sorted(shown) and len(set(shown)) == 60


def test_a_populated_store_at_006_takes_007_and_keeps_its_rows(database):
    from edgar_warehouse.mdm.clean.store import migrate

    load_group(database)
    with database.admin.begin() as conn:
        conn.execute(text("DROP FUNCTION mdm.entity_search(text, text, integer)"))
        conn.execute(text("DROP VIEW mdm.entity_context"))
        conn.execute(text("DROP INDEX mdm.stage_record_identifiers, mdm.current_record_entity_name_search, "
                          "mdm.company_name_search"))
        # The migration ledger is append-only; only this simulation of an older
        # store goes around that, as the database owner.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM mdm.migration WHERE name='007_entity_context.sql'"))
        conn.execute(text("SET LOCAL session_replication_role = origin"))
        count = conn.scalar(text("SELECT count(*) FROM mdm.current_record"))
    migrate(database.admin, application_role="clean_application")
    assert sorted(r["name"] for r in rows(database, "SELECT name FROM mdm.entity_context")) == [
        "Company a", "Company b", "Company c"]
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.current_record")) == count


def test_a_calculated_ultimate_parent_answers_only_for_the_dates_its_chain_held(database):
    """Profiling ticket 04b, part B: under accounting-chain-v2 the calculated
    link has periods, so `--as-of` before its chain held leaves it out."""
    from edgar_warehouse.mdm.clean.store import register_policy

    ultimate = "IS_ULTIMATELY_CONSOLIDATED_BY"
    hierarchy = {"from": ["company"], "to": ["company"], "hierarchy": True, "cycles": "invalid", "one_parent": True}
    with database.admin.begin() as conn:
        fields = conn.scalar(text("SELECT body FROM mdm.policy WHERE digest = :d"), {"d": database.policy})
        policy = register_policy(conn, {**fields, "relationships": {"version": "test", "types": {
            DIRECT: {**hierarchy, "ultimate_parent": "accounting-chain-v2", "ultimate_type": ultimate},
            ultimate: hierarchy}}})
    a = company("a")
    b = company("b", a)
    pairs = [core.identity_and_binding(r) for r in (a, b)]
    MergeStage(Store(database.application)).apply(
        batch_id="work-1", run_id=str(uuid4()), policy_digest=policy, consumer="fixture",
        expected_checkpoint=0, checkpoint=1, as_of=core.AS_OF,
        assertions=[a, b], identities=[i for i, _ in pairs], decisions=[d for _, d in pairs])
    child = pairs[1][0]["entity_id"]
    now = ask(database, "relationship", child, relationship_type=ultimate, detail="full")["related"]
    assert [(r["basis"], r["valid_from"], len(r["path"])) for r in now] == [("calculated", core.AT, 1)]
    assert ask(database, "relationship", child, relationship_type=ultimate,
               as_of="2025-06-01T00:00:00+00:00")["related"] == []
