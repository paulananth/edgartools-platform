"""Real PG16: every lookup a save repeats is served by an index (platform
validation 05b, part 2; operator: "agreed", 2026-10-01).

Every read of a save (its masters, their links, the links it retires) is by
key through an index (migration 003; ticket 77, `scope`). With sequential
scans switched off, PostgreSQL still reads a table in full when no index can
serve the query, so a full read here is a lookup with no index.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from edgar_warehouse.mdm.clean.scope import link_ends
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

TABLES = ("source_reading", "decision", "master_entity", "current_record", "company", "company_alias")
INDEXES = ("source_reading_link_subjects", "source_reading_subject", "master_entity_pkey", "decision_retired_source",
           "decision_subject", "decision_entity", "decision_left", "decision_right", "decision_target",
           "current_record_link_start", "current_record_link_end", "current_record_review_entity",
           "current_record_review_subject", "current_record_review_affected_subjects",
           # record_company_version: is this Company the one stored now (017 asks it)?
           "company_current_entity",
           # A link's far end, as stored; an affected master's records.
           "stage_record_subject_key", "stage_record_entity")


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


def test_a_save_reads_no_table_in_full(database):
    owner, *_ = populate(database)
    # A role setting, not a session one: `apply` opens its own connections.
    # Each module has its own PostgreSQL container, so nothing else shares it.
    with database.admin.begin() as conn:
        conn.execute(text("ANALYZE"))
        conn.execute(text("ALTER ROLE clean_application SET enable_seqscan = off"))
    try:
        database.application.dispose()
        before = scans(database)
        # A save through one child (its master, its links, the save itself),
        # and a new Company linking to the family (the links into a master
        # whose identity is new).
        apply(database, 3, assertions=[source("child-9", revision=2, fields={"name": "Renamed"},
                                              relationships=[parent(owner)])])
        newcomer = source("newcomer", relationships=[parent(owner)])
        identity, bind = identity_and_binding(newcomer)
        apply(database, 4, assertions=[newcomer], identities=[identity], decisions=[bind])
        database.application.dispose()  # a backend reports its counts on exit
        after = scans(database)
    finally:
        with database.admin.begin() as conn:
            conn.execute(text("ALTER ROLE clean_application RESET enable_seqscan"))
    # No table was read in full, and each lookup went through its own index
    # (a lookup could otherwise read every review through the primary key).
    assert after[0] == before[0]
    assert {i for i in INDEXES if after[1][i] > before[1][i]} == set(INDEXES)


def test_sql_and_python_agree_on_the_records_a_reading_links_to(database):
    """`mdm.reading_link_subjects` (the index) and `scope.link_ends` (a save
    following a reading's links) must name the same records."""
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
            python = (
                {end for _, start, target in link_ends({"subject": None, "relationships": links})
                 for end in (start, target) if end}
                if isinstance(links, list) else set()
            )
            assert sorted(sql) == sorted(python), body
