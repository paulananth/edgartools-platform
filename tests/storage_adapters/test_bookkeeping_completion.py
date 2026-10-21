"""The same prepared completion is checked atomically on every real engine.

This qualifies this write capability, not claims, leases or a complete native
non-PostgreSQL workflow. Rows are invented and created in the fixture's isolated
database; the runtime can save checks only through the restricted capability.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
from uuid import uuid4

import edgar_control
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean import run_storage, storage
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.control_contract import canonical
from tests.storage_adapters.test_bookkeeping_reads import control_tables, add_run, add_work


def execution_grant(owner, role, verb, capability="record_run_checks"):
    kind = owner.dialect.name
    principal = f"'{role}'@'%'" if kind == "mysql" else owner.dialect.identifier_preparer.quote(role)
    target = {"postgresql": f"FUNCTION bookkeeping.{capability}(text)",
              "mysql": f"PROCEDURE bookkeeping_{capability}",
              "mssql": f"OBJECT::bookkeeping.{capability}"}[kind]
    return f"{verb} EXECUTE ON {target} {'FROM' if verb == 'REVOKE' else 'TO'} {principal}"


@pytest.fixture(scope="module")
def completion(control_tables):
    owner, runtime, models = control_tables
    role = runtime.url.username
    with owner.begin() as conn:
        for statement in run_storage.statements(owner):
            run_storage.execute_ddl(conn, statement)
        conn.execute(text(execution_grant(owner, role, "GRANT")))
    try:
        yield owner, runtime, models
    finally:
        drop = {"postgresql": "DROP FUNCTION bookkeeping.record_run_checks(text)",
                "mysql": "DROP PROCEDURE bookkeeping_record_run_checks",
                "mssql": "DROP PROCEDURE bookkeeping.record_run_checks"}[owner.dialect.name]
        with owner.begin() as conn:
            conn.execute(text(drop))


def ready_run(completion):
    owner, runtime, models = completion
    rid, _ = add_run(owner, models, state="running")
    add_work(owner, models, rid, key="invented", ordinal=0, state="verified",
             receipt={"uri": "s3://invented/output", "sha256": "a" * 64})
    with owner.begin() as conn:
        conn.execute(models["pipeline_run"].update().where(models["pipeline_run"].c.run_id == rid).values(expected_count=1))
    return rid


def prepared(runtime, rid, checks=None):
    return edgar_control.prepare_run_completion(canonical({
        **storage.completion_observations(runtime, rid), "run_id": rid,
        "checks": {"work.accounting": True} if checks is None else checks,
    }))


def test_real_completion_and_retry_preserve_the_original_completion_time(completion):
    owner, runtime, models = completion
    rid = ready_run(completion)
    wire = prepared(runtime, rid)
    run_storage.record_run_checks(runtime, wire)
    first = Bookkeeping(runtime)._run(rid)
    assert first["state"] == "complete" and first["completed_at"] is not None
    assert first["summary"] == {"expected": 1, "verified": 1, "pending_deliveries": 0}
    run_storage.record_run_checks(runtime, wire)
    assert Bookkeeping(runtime)._run(rid) == first


@pytest.mark.parametrize("cause", ["unfinished", "pending_delivery", "unsealed_expansion", "failed_check"])
def test_runtime_cannot_forge_a_completion_with_missing_prerequisites(completion, cause):
    owner, runtime, models = completion
    rid = ready_run(completion)
    with owner.begin() as conn:
        if cause == "unfinished":
            conn.execute(models["work_item"].update().where(models["work_item"].c.run_id == rid).values(state="pending"))
        elif cause == "pending_delivery":
            conn.execute(models["journal_outbox"].insert(), dict(event_id=str(uuid4()), run_id=rid,
                         step="read", unit_key="invented", payload={}, attempts=0,
                         event_type="work.verified", created_at=datetime.now(UTC)))
        elif cause == "unsealed_expansion":
            conn.execute(models["work_item"].update().where(models["work_item"].c.run_id == rid).values(
                unit={"input": {}, "cursor": {"generated_step": None}}))
    checks = {"work.accounting": cause != "failed_check"}
    intent = json.loads(prepared(runtime, rid, checks))
    assert intent["state"] == "waiting"
    before = Bookkeeping(runtime)._run(rid)
    intent["state"] = "complete"  # Deliberately bypass the native preparer.
    with pytest.raises(DBAPIError, match="unverified_control_completion"):
        run_storage.record_run_checks(runtime, canonical(intent))
    assert Bookkeeping(runtime)._run(rid) == before
    intent["state"] = "waiting"
    run_storage.record_run_checks(runtime, canonical(intent))
    assert Bookkeeping(runtime)._run(rid)["state"] == "waiting"


def test_changed_observations_rollback_without_overwriting_run_metadata(completion):
    owner, runtime, models = completion
    rid = ready_run(completion)
    wire = prepared(runtime, rid)
    before = Bookkeeping(runtime)._run(rid)
    with owner.begin() as conn:
        conn.execute(models["work_item"].update().where(models["work_item"].c.run_id == rid).values(state="pending"))
    with pytest.raises(run_storage.StaleObservation):
        run_storage.record_run_checks(runtime, wire)
    assert Bookkeeping(runtime)._run(rid) == before


def test_prepared_state_cannot_demote_a_completed_run(completion):
    owner, runtime, models = completion
    rid = ready_run(completion)
    wire = prepared(runtime, rid)
    run_storage.record_run_checks(runtime, wire)
    before = Bookkeeping(runtime)._run(rid)
    forged = json.loads(wire)
    forged["state"] = "waiting"
    with pytest.raises(DBAPIError, match="invalid_control_state"):
        run_storage.record_run_checks(runtime, canonical(forged))
    assert Bookkeeping(runtime)._run(rid) == before


@pytest.mark.parametrize("field,body", [
    ("checks", '{"work.accounting":"true"}'),
    ("checks", '{"work.accounting":true,"work.accounting":false}'),
    ("summary", '{"expected":9,"pending_deliveries":0,"verified":1}'),
    ("summary", '{"expected":"1","pending_deliveries":0,"verified":1}'),
    ("summary", '{"expected":1,"expected":9,"pending_deliveries":0,"verified":1}'),
])
def test_malformed_or_forged_prepared_metadata_is_refused(completion, field, body):
    owner, runtime, models = completion
    rid = ready_run(completion)
    wire = json.loads(prepared(runtime, rid))
    before = Bookkeeping(runtime)._run(rid)
    wire[field] = body.encode("utf-8").hex()
    with pytest.raises(DBAPIError, match="invalid_control_(checks|summary)"):
        run_storage.record_run_checks(runtime, canonical(wire))
    assert Bookkeeping(runtime)._run(rid) == before


def test_compacted_run_and_ungranted_runtime_cannot_save_new_checks(completion):
    owner, runtime, models = completion
    rid = ready_run(completion)
    wire = prepared(runtime, rid)
    with owner.begin() as conn:
        conn.execute(models["pipeline_run"].update().where(models["pipeline_run"].c.run_id == rid).values(
            compacted_at=datetime.now(UTC)))
    with pytest.raises(DBAPIError, match="compacted_control_run"):
        run_storage.record_run_checks(runtime, wire)
    rid = ready_run(completion)
    wire = prepared(runtime, rid)
    with owner.begin() as conn:
        conn.execute(text(execution_grant(owner, runtime.url.username, "REVOKE")))
    try:
        with pytest.raises(DBAPIError):
            run_storage.record_run_checks(runtime, wire)
    finally:
        with owner.begin() as conn:
            conn.execute(text(execution_grant(owner, runtime.url.username, "GRANT")))
    assert Bookkeeping(runtime)._run(rid)["state"] == "running"


def test_concurrent_completions_share_one_durable_result(completion):
    owner, runtime, models = completion
    rid = ready_run(completion)

    def finish(_):
        for _ in range(20):
            try:
                run_storage.record_run_checks(runtime, prepared(runtime, rid))
                return
            except run_storage.StaleObservation:
                continue
        pytest.fail("Concurrent completion did not settle within its bounded retries")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(finish, range(12)))
    first = Bookkeeping(runtime)._run(rid)
    assert first["state"] == "complete"
    run_storage.record_run_checks(runtime, prepared(runtime, rid))
    assert Bookkeeping(runtime)._run(rid) == first


def test_destination_failure_rolls_back_and_the_same_intent_can_retry(completion):
    owner, runtime, models = completion
    rid = ready_run(completion)
    wire = prepared(runtime, rid)
    before = Bookkeeping(runtime)._run(rid)
    kind = owner.dialect.name
    if kind == "postgresql":
        install = ["""CREATE FUNCTION bookkeeping.reject_completion() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'invented_completion_failure'; END $$""",
            """CREATE TRIGGER reject_completion AFTER UPDATE ON bookkeeping.pipeline_run
            FOR EACH ROW EXECUTE FUNCTION bookkeeping.reject_completion()"""]
        remove = ["DROP TRIGGER reject_completion ON bookkeeping.pipeline_run",
                  "DROP FUNCTION bookkeeping.reject_completion()"]
    elif kind == "mysql":
        install = ["""CREATE TRIGGER reject_completion AFTER UPDATE ON bookkeeping_pipeline_run
            FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invented_completion_failure'"""]
        remove = ["DROP TRIGGER reject_completion"]
    else:
        install = ["""CREATE TRIGGER bookkeeping.reject_completion ON bookkeeping.pipeline_run
            AFTER UPDATE AS BEGIN; THROW 50001,'invented_completion_failure',1; END"""]
        remove = ["DROP TRIGGER bookkeeping.reject_completion"]
    with owner.begin() as conn:
        for statement in install:
            run_storage.execute_ddl(conn, statement)
    try:
        with pytest.raises(DBAPIError, match="invented_completion_failure"):
            run_storage.record_run_checks(runtime, wire)
        assert Bookkeeping(runtime)._run(rid) == before
    finally:
        with owner.begin() as conn:
            for statement in remove:
                run_storage.execute_ddl(conn, statement)
    run_storage.record_run_checks(runtime, wire)
    assert Bookkeeping(runtime)._run(rid)["state"] == "complete"
