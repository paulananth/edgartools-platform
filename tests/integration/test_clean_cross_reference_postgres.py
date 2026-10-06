"""Real PG16: cross-reference ids are written, read back, and never join records
(profiling ticket 03; operator, 2026-09-26: lookup only).

Each test has a control that can fail: the same value under `identifiers`, with
an active identifier rule, binds the records; under `cross_references` it does
not.
"""

from __future__ import annotations

import time

from sqlalchemy import text


from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_identifier_binding import (
    APPLE_CIK,
    companies,
    load,
    matching_policy,
)

postgres = core.postgres
database = core.database

TAX_ID = "12-3456789"


def record(key, source_code="fixture.primary", identifiers=None, cross_references=None):
    return core.source(key=key, source_code=source_code, fields={"name": f"Company {key}"},
                       identifiers=identifiers or {}, cross_references=cross_references)


def lookup(database, namespace, value):
    with database.application.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(
            text("SELECT * FROM mdm.cross_reference_lookup(:n, :v)"), {"n": namespace, "v": value})]


def bound_entity(database, key, source_code="fixture.primary"):
    with database.application.connect() as conn:
        found = conn.scalar(text("SELECT entity_id::text FROM mdm.stage_record WHERE source_code = :s "
                                 "AND record_key = :k"), {"s": source_code, "k": key})
    return found


def index_scans(database):
    with database.admin.connect() as conn:
        return conn.scalar(text("SELECT idx_scan FROM pg_stat_user_indexes "
                                "WHERE indexrelname = 'stage_record_cross_references'"))


def test_the_same_value_binds_as_an_identifier_but_not_as_a_cross_reference(database):
    policy = matching_policy(database)
    load(database, policy, "b1", record("a", identifiers={"cik": APPLE_CIK}))
    (company,) = companies(database).values()
    # Control: under `identifiers`, a second source's record joins the Company.
    load(database, policy, "b2", record("b", "fixture.secondary", identifiers={"cik": APPLE_CIK}), checkpoint=2)
    assert len(companies(database)[company["entity_id"]]["subjects"]) == 2
    # Under `cross_references`, the same namespace and value join nothing: the
    # record waits for binding, and the Company keeps its two records.
    load(database, policy, "b3", record("c", "fixture.secondary", cross_references={"cik": APPLE_CIK}),
         checkpoint=3)
    after = companies(database)
    assert list(after) == [company["entity_id"]] and len(after[company["entity_id"]]["subjects"]) == 2
    assert bound_entity(database, "c", "fixture.secondary") is None


def test_two_records_sharing_only_a_cross_reference_stay_two_companies(database):
    policy = matching_policy(database)
    load(database, policy, "b1",
         record("a", identifiers={"cik": "0000000001"}, cross_references={"tax_id": TAX_ID}),
         record("b", identifiers={"cik": "0000000002"}, cross_references={"tax_id": TAX_ID}))
    assert len(companies(database)) == 2
    found = lookup(database, "tax_id", TAX_ID)
    assert [(r["source_code"], r["record_key"]) for r in found] == [("fixture.primary", "a"), ("fixture.primary", "b")]
    assert {r["entity_id"] for r in found} == set(companies(database))


def test_a_record_waiting_for_binding_is_found_with_no_entity(database):
    policy = matching_policy(database)
    load(database, policy, "b1", record("w", "fixture.secondary", cross_references={"tax_id": TAX_ID}))
    (found,) = lookup(database, "tax_id", TAX_ID)
    assert found["record_key"] == "w" and found["entity_id"] is None and found["bound_entity_id"] is None
    assert lookup(database, "tax_id", "00-0000000") == []


def test_a_merged_record_is_found_at_its_survivor(database):
    a, b = record("a"), record("b", cross_references={"tax_id": TAX_ID})
    pairs = [core.identity_and_binding(r) for r in (a, b)]
    core.apply(database, 1, assertions=[a, b], identities=[i for i, _ in pairs], decisions=[d for _, d in pairs])
    left, right = (i["entity_id"] for i, _ in pairs)
    core.apply(database, 2, decisions=[core.decision(
        "merge", actor="steward", reason="same company", at=core.AT, left=left, right=right)])
    # The Merge Stage chooses the survivor; read which one it chose.
    with database.application.connect() as conn:
        canonical = dict(conn.execute(text(
            "SELECT object_id, canonical_id FROM mdm.current_entity WHERE object_id = ANY(:ids)"),
            {"ids": [left, right]}).all())
    survivor = canonical[right] or right
    (found,) = lookup(database, "tax_id", TAX_ID)
    assert found["bound_entity_id"] == right and found["entity_id"] == survivor
    assert (canonical[left] or left) == (canonical[right] or right) == survivor  # both now read as one entity


def test_the_lookup_is_served_by_its_index(database):
    policy = matching_policy(database)
    records = [record(f"r{n}", identifiers={"cik": f"{n:010d}"}, cross_references={"tax_id": f"{n:02d}-{n:07d}"})
               for n in range(1, 401)]
    load(database, policy, "b1", *records)
    with database.admin.connect() as conn:
        conn.execute(text("ANALYZE mdm.stage_record"))
        conn.commit()
    before = index_scans(database)
    with database.admin.connect() as conn:
        conn.execute(text("SET enable_seqscan = off"))  # a full read now means no index serves the lookup
        rows = conn.execute(text("SELECT record_key FROM mdm.cross_reference_lookup('tax_id', '07-0000007')")).all()
        conn.commit()
    # A backend reports its index use when its transaction ends; wait until it shows.
    deadline = time.monotonic() + 10
    while (after := index_scans(database)) == before and time.monotonic() < deadline:
        time.sleep(0.2)
    assert [r[0] for r in rows] == ["r7"]
    # With the planner's own settings, on 400 records, the lookup's query reads the index.
    with database.admin.connect() as conn:
        plan = "\n".join(r[0] for r in conn.execute(text(
            "EXPLAIN SELECT s.record_key FROM mdm.stage_record s "
            "WHERE s.reading -> 'cross_references' @> jsonb_build_object('tax_id', '07-0000007')")))
    assert "stage_record_cross_references" in plan, plan
    assert after > before


def test_a_populated_store_at_004_takes_005_and_finds_its_records(database):
    """A store with records carrying cross-references, built before 005, takes
    005 on the next migrate: its rows are kept and the lookup finds them."""
    from edgar_warehouse.mdm.clean.store import migrate

    policy = matching_policy(database)
    load(database, policy, "b1", record("a", identifiers={"cik": "0000000001"}, cross_references={"tax_id": TAX_ID}))
    with database.admin.begin() as conn:
        conn.execute(text("DROP FUNCTION mdm.cross_reference_lookup(text, text)"))
        conn.execute(text("DROP VIEW mdm.cross_reference"))
        conn.execute(text("DROP INDEX mdm.stage_record_cross_references"))
        # The migration ledger is append-only; only this simulation of an older
        # store goes around that, as the database owner.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM mdm.migration WHERE name='005_cross_reference.sql'"))
        conn.execute(text("SET LOCAL session_replication_role = origin"))
        count = conn.scalar(text("SELECT count(*) FROM mdm.stage_record"))
    migrate(database.admin, application_role="clean_application")
    assert [r["record_key"] for r in lookup(database, "tax_id", TAX_ID)] == ["a"]
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.stage_record")) == count == 1
