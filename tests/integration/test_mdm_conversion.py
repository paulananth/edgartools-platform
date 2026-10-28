"""Ticket 146: a populated native MDM store converts to governed storage.

The native store is the six tables the conversion reads, as native MDM kept
them (each batch's whole command in `mdm.batch.effects`), in a database of
their own. Invented records only.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from edgar_warehouse.mdm.clean import conversion
from edgar_warehouse.mdm.clean.evidence import decision, deferred_record
from edgar_warehouse.mdm.clean.relationships import types_of
from edgar_warehouse.mdm.clean.store import digest, storage_adapter
from tests.integration import test_clean_mdm_postgres as core

NATIVE = """
CREATE SCHEMA mdm;
CREATE TABLE mdm.policy (digest text PRIMARY KEY, body jsonb);
CREATE TABLE mdm.dataset_mapping (source_code text, mapping_version bigint, body jsonb,
                                  registry_version uuid, registered_at timestamptz);
CREATE TABLE mdm.batch (batch_id text PRIMARY KEY, request_hash text, run_id uuid, policy_digest text,
                        generation bigint, consumer text, checkpoint bigint, effects jsonb, created_at timestamptz);
CREATE TABLE mdm.master_entity (entity_id uuid, kind text, published_at timestamptz, batch_id text);
CREATE TABLE mdm.stage_record (subject text, entity_id uuid);
CREATE TABLE mdm.decision (decision_id text, operation text, body jsonb, batch_id text);
CREATE TABLE mdm.current_record (object_type text, object_id text, body jsonb, batch_id text);
"""


def rule_bind(record, entity_id):
    """A bind as a native matching rule recorded it."""
    return decision("bind", actor="rule:invented-key@1", reason="identifier_match invented",
                    at=core.AT, subject=record["subject"], entity_id=entity_id,
                    evidence=[record["assertion_id"]], rule_id="invented-key", rule_version="1")


@pytest.fixture
def native(database):
    """A native store beside the fresh governed one: two batches of one consumer."""
    name = f"native_{uuid4().hex[:12]}"
    server = database.admin.execution_options(isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name}"))
    engine = create_engine(database.admin.url.set(database=name))
    with database.admin.connect() as conn:
        policy = storage_adapter().registered_policy(conn, database.policy)
        readings = conn.execute(text("""SELECT source_code, mapping_version, body, registry_version
            FROM mdm.dataset_mapping""")).all()
    # Native policies listed their relationship types inline (before ticket 132).
    inline = {k: v for k, v in policy.items() if k not in ("relationships", "reference_pins")}
    inline["relationships"] = {"version": "invented-types-v1", "types": types_of(policy)}
    first, second, unbound = (core.source(key) for key in ("one", "two", "unbound"))
    later = core.source("one-again", source_code="fixture.secondary")
    one, two = str(uuid4()), str(uuid4())
    held = deferred_record(source_code="fixture.primary", publication_key="p1", record_locator="held",
                           schema_version="1", reason="invented_missing_key", raw_record={"amount": 7}, provenance={})
    batches = [
        {"assertions": [first, second, unbound], "deferred": [held],
         "identities": [{"entity_id": e, "kind": "company", "published_at": core.AT} for e in (one, two)],
         "decisions": [rule_bind(first, one), rule_bind(second, two)]},
        # A later record joins a master an earlier batch made.
        {"assertions": [later], "identities": [], "decisions": [rule_bind(later, one)]},
    ]
    with engine.begin() as conn:
        conn.exec_driver_sql(NATIVE)
        conn.execute(text("INSERT INTO mdm.policy VALUES (:d, :b)"),
                     {"d": digest(inline), "b": json.dumps(inline)})
        for code, version, body, registry in readings:
            conn.execute(text("INSERT INTO mdm.dataset_mapping VALUES (:c, :v, :b, :r, now())"),
                         {"c": code, "v": version, "b": json.dumps(body), "r": registry})
        for n, part in enumerate(batches, 1):
            command = {"batch_id": f"native-{n}", "policy_digest": digest(inline), "consumer": "fixture",
                       "expected_checkpoint": n - 1, "checkpoint": n, "as_of": core.AS_OF,
                       "deferred": [], **part}
            conn.execute(text("""INSERT INTO mdm.batch VALUES (:b, '', :r, :p, :n, 'fixture', :n, :e, now())"""),
                         {"b": command["batch_id"], "r": str(uuid4()), "p": digest(inline), "n": n,
                          "e": json.dumps(command)})
            for i in part["identities"]:
                conn.execute(text("INSERT INTO mdm.master_entity VALUES (:e, 'company', :a, :b)"),
                             {"e": i["entity_id"], "a": core.AT, "b": command["batch_id"]})
            for d in part["decisions"]:
                conn.execute(text("INSERT INTO mdm.decision VALUES (:i, 'bind', :d, :b)"),
                             {"i": d["decision_id"], "d": json.dumps(d), "b": command["batch_id"]})
        for record, entity in ((first, one), (second, two), (unbound, None), (later, one)):
            conn.execute(text("INSERT INTO mdm.stage_record VALUES (:s, :e)"),
                         {"s": record["subject"], "e": entity})
    try:
        yield engine
    finally:
        engine.dispose()
        with server.connect() as conn:
            conn.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))


def native_state(engine):
    with engine.connect() as conn:
        return {table: conn.scalar(text(f"SELECT md5(string_agg(t::text, '' ORDER BY t::text)) FROM mdm.{table} t"))
                for table in ("policy", "dataset_mapping", "batch", "master_entity", "stage_record", "decision")}


def test_masters_keep_their_ids_and_records_their_bindings(database, native):
    before = native_state(native)
    report = conversion.convert(native, database.admin)
    assert {k: report[k] for k in ("policies", "batches", "already_saved", "readings", "decisions", "masters",
                                   "set_aside")} == {"policies": 1, "batches": 2, "already_saved": 0, "readings": 4, "decisions": 3, "masters": 2, "set_aside": 1}
    assert conversion.verify(native, database.admin, page=3) == {
        "masters": 2, "masters_kept": 2, "masters_added": 0, "records": 4, "records_present": 4,
        "bindings_kept": 4, "decisions": 3, "decisions_lost": 0, "fields_differing": {}, "passed": True}
    assert native_state(native) == before


def test_a_second_run_changes_nothing(database, native):
    conversion.convert(native, database.admin)
    entities = core.documents(database, "entity")
    conversion.convert(native, database.admin)
    assert core.documents(database, "entity") == entities
    assert conversion.verify(native, database.admin)["bindings_kept"] == 4


def test_a_stopped_conversion_resumes(database, native):
    assert conversion.convert(native, database.admin, limit=1)["batches"] == 1
    again = conversion.convert(native, database.admin, limit=1)
    assert (again["already_saved"], again["batches"]) == (1, 1)
    assert conversion.convert(native, database.admin)["already_saved"] == 2
    assert conversion.verify(native, database.admin)["masters_kept"] == 2


def test_a_lost_binding_fails_the_checks(database, native):
    conversion.convert(native, database.admin)
    with native.begin() as conn:
        conn.execute(text("UPDATE mdm.stage_record SET entity_id=:e WHERE entity_id IS NULL"), {"e": str(uuid4())})
    checked = conversion.verify(native, database.admin)
    assert (checked["bindings_kept"], checked["passed"]) == (3, False)


def test_the_native_store_is_read_on_sessions_that_refuse_writes(native):
    from sqlalchemy.exc import InternalError

    with pytest.raises(InternalError, match="read-only transaction"):
        with conversion._read_only(native) as conn:
            conn.execute(text("DELETE FROM mdm.decision"))
