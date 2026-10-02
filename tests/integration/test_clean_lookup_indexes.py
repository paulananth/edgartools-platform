"""Real PG16: every lookup a save repeats is served by an index (platform
validation 05b, part 2; operator: "agreed", 2026-10-01).

The match proposal snapshot, the Merge Stage closure and the retirement of old
links and reviews used to read their tables in full, so each save cost more
than the one before. Migration 003 indexes each lookup. With sequential scans
switched off, PostgreSQL still reads a table in full when no index can serve
the query, so a full read here is a lookup with no index.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from edgar_warehouse.mdm.clean import store
from edgar_warehouse.mdm.clean.merge import linked_subjects, load_closure
from edgar_warehouse.mdm.clean.store import migrate
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_mdm_postgres import (
    AT,
    apply,
    decision,
    identity_and_binding,
    source,
)

postgres = core.postgres
database = core.database

TABLES = ("source_reading", "decision", "master_entity", "current_record")
INDEXES = ("source_reading_link_subjects", "master_entity_id_text", "decision_retired_source",
           "current_record_link_start", "current_record_link_end", "current_record_review_entity",
           "current_record_review_subject", "current_record_review_affected_subjects")


def parent(target, **more):
    return {"type": "ACCOUNTING_PARENT", "target_subject": target["subject"], "valid_from": AT,
            "valid_to": None, "scope": "consolidated", **more}


def populate(database):
    """Companies linked into one family, a link record that starts at its
    child, a record waiting for binding, an override and a merge."""
    owner = source("owner")
    children = [source(f"child-{n}", relationships=[parent(owner)]) for n in range(30)]
    record = source("child-0|owner|ACCOUNTING_PARENT", source_code="fixture.secondary", fields={},
                    relationships=[parent(owner, source_subject=children[0]["subject"])])
    # Records waiting for binding, each with an open review: enough rows that
    # reading every review costs more than an index lookup, as in a real store.
    strays = [source(f"stray-{n}", relationships=[parent(owner)]) for n in range(300)]
    others = [source(f"other-{n}") for n in range(300)]
    records = [owner, *children, *others]
    pairs = [identity_and_binding(r) for r in records]
    override = decision("override", actor="reviewer", reason="verified correction", at=AT,
                        subject=owner["subject"], field="name", value="Owner, corrected",
                        evidence=[owner["assertion_id"]])
    apply(database, 1, assertions=[*records, record, *strays], identities=[i for i, _ in pairs],
          decisions=[d for _, d in pairs] + [override])
    merge = decision("merge", actor="steward", reason="same company", at=AT,
                     left=pairs[-1][0]["entity_id"], right=pairs[-2][0]["entity_id"])
    apply(database, 2, decisions=[merge])
    return owner, children, others, pairs


def scans(database, previous=None):
    """Full reads of each table, and uses of each new index. A closed backend
    reports its counts shortly after it exits, so wait until they settle."""
    import time

    deadline = time.monotonic() + 10
    while True:
        counts = _counts(database)
        if counts == previous or time.monotonic() > deadline:
            return counts
        previous = counts
        time.sleep(0.5)


def _counts(database):
    with database.admin.connect() as conn:
        conn.execute(text("SELECT pg_stat_clear_snapshot()"))
        full = {r[0]: r[1] for r in conn.execute(text(
            "SELECT relname, seq_scan FROM pg_stat_user_tables WHERE schemaname='mdm' AND relname=ANY(:t)"),
            {"t": list(TABLES)})}
        used = {r[0]: r[1] for r in conn.execute(text(
            "SELECT indexrelname, idx_scan FROM pg_stat_user_indexes WHERE schemaname='mdm' AND indexrelname=ANY(:i)"),
            {"i": list(INDEXES)})}
        return full, used


def snapshot(conn, keys, sources=()):
    scope = json.dumps({"keys": sorted(keys), "sources": sorted(sources), "consumer": "fixture"})
    return conn.scalar(text("SELECT mdm.match_proposal_snapshot(CAST(:s AS jsonb))"), {"s": scope})


def test_the_snapshot_closure_and_retirement_read_no_table_in_full(database):
    owner, children, others, pairs = populate(database)
    # A role setting, not a session one: `apply` opens its own connections.
    # Each module has its own PostgreSQL container, so nothing else shares it.
    with database.admin.begin() as conn:
        conn.execute(text("ANALYZE"))
        conn.execute(text("ALTER ROLE clean_application SET enable_seqscan = off"))
    try:
        database.application.dispose()
        before = scans(database)
        keys = {owner["subject"], children[5]["subject"], pairs[0][0]["entity_id"], "no-such-key"}
        with database.application.connect() as conn:
            snapshot(conn, keys, ["fixture.primary"])
            load_closure(conn, [source("child-7", revision=2, relationships=[parent(owner)])], [], limit=10000)
        # A save through one child: its closure, retirement and the save itself.
        apply(database, 3, assertions=[source("child-9", revision=2, fields={"name": "Renamed"},
                                              relationships=[parent(owner)])])
        database.application.dispose()  # a backend reports its counts on exit
        after = scans(database)
    finally:
        with database.admin.begin() as conn:
            conn.execute(text("ALTER ROLE clean_application RESET enable_seqscan"))
    # No table was read in full, and each lookup went through its own index
    # (a lookup could otherwise read every review through the primary key).
    assert after[0] == before[0]
    assert {i for i in INDEXES if after[1][i] > before[1][i]} == set(INDEXES)


def test_a_populated_store_at_002_takes_003_with_the_same_snapshots(database):
    owner, children, others, pairs = populate(database)
    sql = (Path(store.__file__).parents[1] / "migrations" / "002_link_start.sql").read_text()
    old = sql[sql.index("CREATE OR REPLACE FUNCTION mdm.match_proposal_snapshot"):]
    old = old[: old.index("$$;") + 3]
    scopes = [
        ({owner["subject"]}, ()),
        ({children[0]["subject"], pairs[3][0]["entity_id"]}, ("fixture.primary",)),
        ({pairs[-1][0]["entity_id"], pairs[-2][0]["entity_id"]}, ()),
        ({c["subject"] for c in children} | {o["subject"] for o in others}, ("fixture.secondary",)),
    ]
    with database.admin.begin() as conn:
        conn.execute(text(old))
        for name in INDEXES:
            conn.execute(text(f"DROP INDEX mdm.{name}"))
        conn.execute(text("DROP FUNCTION mdm.reading_link_subjects(jsonb)"))
        # The migration ledger is append-only; only this simulation of an older
        # store goes around that, as the database owner.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM mdm.migration WHERE name='003_lookup_indexes.sql'"))
        conn.execute(text("SET LOCAL session_replication_role = origin"))
        before = [snapshot(conn, k, s) for k, s in scopes]
        counts = {t: conn.scalar(text(f"SELECT count(*) FROM mdm.{t}")) for t in TABLES}
    migrate(database.admin, application_role="clean_application")
    with database.application.connect() as conn:
        assert [snapshot(conn, k, s) for k, s in scopes] == before
    with database.admin.connect() as conn:
        assert {t: conn.scalar(text(f"SELECT count(*) FROM mdm.{t}")) for t in TABLES} == counts
        assert conn.scalar(text("SELECT count(*) FROM mdm.migration WHERE name='003_lookup_indexes.sql'")) == 1


def test_the_closure_finds_what_it_found_before_the_indexes(database):
    """`load_closure` reads links through `mdm.reading_link_subjects`; it finds
    the same readings and decisions as the query it replaced."""
    owner, children, others, pairs = populate(database)

    def old_closure(conn, keys):
        readings, decisions = {}, {}
        while True:
            before = set(keys)
            for (body,) in conn.execute(text(
                    """SELECT body FROM mdm.source_reading WHERE body->>'subject'=ANY(:k) OR EXISTS(
                    SELECT 1 FROM jsonb_array_elements(body->'relationships') r
                    WHERE r->>'target_subject'=ANY(:k) OR r->>'source_subject'=ANY(:k))"""), {"k": sorted(keys)}):
                readings[body["assertion_id"]] = body
                keys.add(body["subject"])
                for r in body.get("relationships", []):
                    keys.update(v for v in (r.get("target_subject"), r.get("source_subject")) if v)
            for (body,) in conn.execute(text(
                    """SELECT body FROM mdm.decision WHERE body->>'subject'=ANY(:k) OR body->>'entity_id'=ANY(:k)
                    OR body->>'left'=ANY(:k) OR body->>'right'=ANY(:k) OR body->>'target'=ANY(:k)
                    OR decision_id=ANY(:k)"""), {"k": sorted(keys)}):
                decisions[body["decision_id"]] = body
                keys.update(str(body[f]) for f in ("subject", "entity_id", "left", "right", "target", "decision_id")
                            if body.get(f))
            if keys == before:
                return set(readings), set(decisions)

    for start in (children[3], others[0], owner, pairs[-1][0]["entity_id"]):
        assertions = [start] if isinstance(start, dict) else []
        keys = {start["subject"]} if isinstance(start, dict) else {start}
        decisions = [] if isinstance(start, dict) else [
            decision("quarantine", actor="steward", reason="probe", at=AT, subject="probe", entity_id=start)]
        with database.application.connect() as conn:
            readings, found, identities = load_closure(conn, assertions, decisions, limit=10000)
            if decisions:
                keys |= {"probe", decisions[0]["decision_id"]}
            expected_readings, expected_decisions = old_closure(conn, keys)
        assert {a["assertion_id"] for a in readings} == expected_readings
        assert {d["decision_id"] for d in found} == expected_decisions
        assert {i["entity_id"] for i in identities} == {i["entity_id"] for i, _ in pairs} & (
            expected_keys(readings, found) | keys)


def expected_keys(readings, decisions):
    keys = {a["subject"] for a in readings}
    for a in readings:
        keys |= linked_subjects(a)
    for d in decisions:
        keys |= {str(d[f]) for f in ("subject", "entity_id", "left", "right", "target", "decision_id") if d.get(f)}
    return keys


def test_sql_and_python_agree_on_the_records_a_reading_links_to(database):
    """`mdm.reading_link_subjects` (the index) and `merge.linked_subjects` (the
    closure growing its keys) must name the same records."""
    bodies = [
        {"relationships": [{"target_subject": "b"}]},
        {"relationships": [{"target_subject": "b", "source_subject": "a"}, {"target_subject": "c"}]},
        {"relationships": [{"target_subject": "", "source_subject": None}]},
        {"relationships": []},
        {"relationships": {"target_subject": "x"}},
        {},
    ]
    with database.application.connect() as conn:
        for body in bodies:
            sql = conn.scalar(text("SELECT mdm.reading_link_subjects(CAST(:b AS jsonb))"), {"b": json.dumps(body)})
            links = body.get("relationships")
            # A stored reading always has a list (`validate_assertion`); the SQL
            # also takes anything else, as no links.
            python = linked_subjects({"relationships": links}) if isinstance(links, list) else set()
            assert sorted(sql) == sorted(python), body
