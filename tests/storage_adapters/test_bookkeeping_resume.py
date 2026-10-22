"""Native-prepared recovery rechecks current storage on every selected engine."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
import time
from uuid import uuid4

import edgar_control
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean import run_storage, storage
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.control_contract import Blocked, canonical
from tests.storage_adapters.test_bookkeeping_completion import execution_grant
from tests.storage_adapters.test_bookkeeping_reads import control_tables, add_run, add_work


@pytest.fixture(scope="module")
def recovery(control_tables):
    owner, runtime, models = control_tables
    with owner.begin() as conn:
        for statement in run_storage.resume_statements(owner):
            run_storage.execute_ddl(conn, statement)
        conn.execute(text(execution_grant(owner, runtime.url.username, "GRANT", "resume_run_prepared")))
    try:
        yield owner, runtime, models
    finally:
        drop = {"postgresql": "DROP FUNCTION bookkeeping.resume_run_prepared(text)",
                "mysql": "DROP PROCEDURE bookkeeping_resume_run_prepared",
                "mssql": "DROP PROCEDURE bookkeeping.resume_run_prepared"}[owner.dialect.name]
        with owner.begin() as conn:
            conn.exec_driver_sql(drop)


def observed_wire(runtime, rid):
    return edgar_control.prepare_run_resume(canonical(storage.resume_observations(runtime, rid)))


@pytest.mark.parametrize("state", ["running", "waiting", "blocked", "complete"])
def test_resume_preserves_work_and_summary_and_identical_retry_is_unchanged(recovery, state):
    owner, runtime, models = recovery
    rid, _ = add_run(owner, models, state=state)
    add_work(owner, models, rid, key="invented", ordinal=0, state="verified")
    with owner.begin() as conn:
        conn.execute(models["pipeline_run"].update().where(models["pipeline_run"].c.run_id == rid).values(
            checks={"work.accounting": True}, summary={"invented": 10**50}))
    book = Bookkeeping(runtime)
    before = book.status(rid)
    wire = observed_wire(runtime, rid)
    run_storage.record_run_resume(runtime, wire)
    after = book.status(rid)
    expected = {**before["run"], "state": "running", "checks": {}, "completed_at": None}
    assert after == {**before, "run": expected}
    run_storage.record_run_resume(runtime, wire)
    assert book.status(rid) == after


def test_resume_refuses_changed_state_and_preserves_newer_metadata(recovery):
    owner, runtime, models = recovery
    rid, _ = add_run(owner, models, state="complete")
    wire = observed_wire(runtime, rid)
    with owner.begin() as conn:
        conn.execute(models["pipeline_run"].update().where(models["pipeline_run"].c.run_id == rid).values(
            state="waiting", checks={"manifest.hash": False}))
    before = Bookkeeping(runtime)._run(rid)
    with pytest.raises(run_storage.StaleObservation):
        run_storage.record_run_resume(runtime, wire)
    assert Bookkeeping(runtime)._run(rid) == before


def test_resume_refuses_newer_checks_without_a_state_change(recovery):
    owner, runtime, models = recovery
    rid, _ = add_run(owner, models, state="waiting")
    wire = observed_wire(runtime, rid)
    with owner.begin() as conn:
        conn.execute(models["pipeline_run"].update().where(models["pipeline_run"].c.run_id == rid).values(
            checks={"blocked": "invented é漢字😀", "large": 10**50}))
    before = Bookkeeping(runtime)._run(rid)
    with pytest.raises(run_storage.StaleObservation):
        run_storage.record_run_resume(runtime, wire)
    assert Bookkeeping(runtime)._run(rid) == before
    # A newly observed explicit resume can still clear the exact stored checks.
    run_storage.record_run_resume(runtime, observed_wire(runtime, rid))
    assert Bookkeeping(runtime)._run(rid)["checks"] == {}


def test_old_resume_cannot_reopen_a_new_completion(recovery):
    owner, runtime, models = recovery
    rid, _ = add_run(owner, models, state="complete")
    original = Bookkeeping(runtime)._run(rid)
    wire = observed_wire(runtime, rid)
    run_storage.record_run_resume(runtime, wire)
    with owner.begin() as conn:
        conn.execute(models["pipeline_run"].update().where(models["pipeline_run"].c.run_id == rid).values(
            state="complete", completed_at=original["completed_at"] + timedelta(seconds=1)))
    before = Bookkeeping(runtime)._run(rid)
    with pytest.raises(run_storage.StaleObservation):
        run_storage.record_run_resume(runtime, wire)
    assert Bookkeeping(runtime)._run(rid) == before


def test_resume_timestamp_guard_keeps_the_destinations_full_precision(recovery):
    owner, runtime, models = recovery
    rid, _ = add_run(owner, models, state="complete")
    wire = observed_wire(runtime, rid)
    changed = {"postgresql": "completed_at + interval '1 microsecond'",
               "mysql": "DATE_ADD(completed_at,INTERVAL 1 MICROSECOND)",
               "mssql": "DATEADD(NANOSECOND,100,completed_at)"}[owner.dialect.name]
    with owner.begin() as conn:
        conn.execute(models["pipeline_run"].update().where(models["pipeline_run"].c.run_id == rid).values(
            completed_at=text(changed)))
    newer = storage.resume_observations(runtime, rid)
    assert newer["completion_token"] != json.loads(wire)["expected_completion"]
    with pytest.raises(run_storage.StaleObservation):
        run_storage.record_run_resume(runtime, wire)
    assert storage.resume_observations(runtime, rid) == newer


def test_compacted_resume_is_refused_by_preparer_caller_and_destination(recovery):
    owner, runtime, models = recovery
    rid, _ = add_run(owner, models)
    wire = observed_wire(runtime, rid)
    with owner.begin() as conn:
        conn.execute(models["pipeline_run"].update().where(models["pipeline_run"].c.run_id == rid).values(
            compacted_at=datetime.now(UTC)))
    before = Bookkeeping(runtime)._run(rid)
    with pytest.raises(ValueError, match="audit-only"):
        observed_wire(runtime, rid)
    with pytest.raises(Blocked, match="audit-only"):
        Bookkeeping(runtime).resume(rid)
    with pytest.raises(DBAPIError, match="compacted_control_run"):
        run_storage.record_run_resume(runtime, wire)
    assert Bookkeeping(runtime)._run(rid) == before


@pytest.mark.parametrize("field,value", [("state", "complete"), ("checks", "7b22696e76656e746564223a747275657d")])
def test_resume_refuses_forged_prepared_metadata(recovery, field, value):
    owner, runtime, models = recovery
    rid, _ = add_run(owner, models)
    before = Bookkeeping(runtime)._run(rid)
    wire = json.loads(observed_wire(runtime, rid))
    wire[field] = value
    with pytest.raises(DBAPIError, match="invalid_control_resume"):
        run_storage.record_run_resume(runtime, canonical(wire))
    assert Bookkeeping(runtime)._run(rid) == before


def test_unknown_resume_does_not_create_a_run(recovery):
    owner, runtime, models = recovery
    rid = str(uuid4())
    wire = edgar_control.prepare_run_resume(canonical({"run_id": rid, "state": "running", "compacted": False,
                                                     "checks_token": "{}", "completion_token": ""}))
    with pytest.raises(DBAPIError, match="unknown_control_run"):
        run_storage.record_run_resume(runtime, wire)
    with pytest.raises(Blocked, match="Unknown run"):
        Bookkeeping(runtime)._run(rid)


def test_ungranted_runtime_cannot_resume(recovery):
    owner, runtime, models = recovery
    rid, _ = add_run(owner, models)
    wire = observed_wire(runtime, rid)
    before = Bookkeeping(runtime)._run(rid)
    with owner.begin() as conn:
        conn.execute(text(execution_grant(owner, runtime.url.username, "REVOKE", "resume_run_prepared")))
    try:
        with pytest.raises(DBAPIError):
            run_storage.record_run_resume(runtime, wire)
    finally:
        with owner.begin() as conn:
            conn.execute(text(execution_grant(owner, runtime.url.username, "GRANT", "resume_run_prepared")))
    assert Bookkeeping(runtime)._run(rid) == before


def test_concurrent_identical_resumes_settle_on_one_unchanged_result(recovery):
    owner, runtime, models = recovery
    rid, _ = add_run(owner, models)
    wire = observed_wire(runtime, rid)

    def resume(_):
        for attempt in range(20):
            try:
                run_storage.record_run_resume(runtime, wire)
                return
            except run_storage.StaleObservation:
                # NOWAIT refuses an occupied row immediately. Yield between
                # attempts so the lock holder can commit on a busy runner.
                time.sleep(min(0.01 * (attempt + 1), 0.05))
        pytest.fail("Concurrent resume did not settle within bounded retries")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(resume, range(12)))
    before = Bookkeeping(runtime)._run(rid)
    assert before["state"] == "running" and before["completed_at"] is None
    run_storage.record_run_resume(runtime, wire)
    assert Bookkeeping(runtime)._run(rid) == before
