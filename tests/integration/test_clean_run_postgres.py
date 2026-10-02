"""Real PG16: a Merge Stage run kept in MDM itself (migration 043).

The run's frozen scope and reconciled outcome were kept in the retired
legacy Bookkeeping `pipeline_run`; they are now `mdm.run`, written by the
application login only through `start_run` and `finish_run` (platform
validation slice 2a).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean.run import RunCoordinator
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Conflict, Store
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database


def load(database, run_id, batch, checkpoint):
    return MergeStage(Store(database.application)).apply(
        batch_id=batch,
        run_id=run_id,
        policy_digest=database.policy,
        consumer="load",
        expected_checkpoint=checkpoint - 1,
        checkpoint=checkpoint,
        as_of=core.AS_OF,
        assertions=[core.source(key=batch)],
    )


def run_row(database, run_id):
    with database.admin.connect() as conn:
        return conn.execute(
            text("SELECT status, report, completed_at FROM mdm.run WHERE run_id=CAST(:r AS uuid)"),
            {"r": run_id},
        ).mappings().one()


def test_a_run_is_registered_once_and_its_scope_never_changes(database):
    coordinator = RunCoordinator(Store(database.application))
    run_id = str(uuid4())
    coordinator.start(run_id, ["b1", "b2"], manifest_digest="d" * 64)
    # The same scope again is a no-op; a different one is refused.
    coordinator.start(run_id, ["b2", "b1"], manifest_digest="d" * 64)
    with pytest.raises(Conflict, match="Root run scope changed"):
        coordinator.start(run_id, ["b1"], manifest_digest="d" * 64)
    assert run_row(database, run_id)["status"] == "running"


def test_reconcile_reports_missing_batches_and_keeps_the_run_open(database):
    store = Store(database.application)
    coordinator = RunCoordinator(store)
    run_id = str(uuid4())
    coordinator.start(run_id, ["b1", "b2"], manifest_digest="d" * 64)
    load(database, run_id, "b1", 1)
    report = coordinator.reconcile(run_id)
    assert report["observed_batches"] == 1
    assert report["missing_batches"] == ["b2"]
    assert report["end_to_end_complete"] is False
    row = run_row(database, run_id)
    assert row["status"] == "running" and row["completed_at"] is None
    assert row["report"]["missing_batches"] == ["b2"]


def test_a_succeeded_run_stays_succeeded(database):
    # A reconcile that saw an older, incomplete view and commits last never
    # sets a succeeded run back to running.
    coordinator = RunCoordinator(Store(database.application))
    run_id = str(uuid4())
    coordinator.start(run_id, ["b1"], manifest_digest="d" * 64)
    with database.application.begin() as conn:
        for body, complete in (('{"end_to_end_complete": true}', True), ('{"end_to_end_complete": false}', False)):
            conn.execute(text("SELECT mdm.finish_run(CAST(:r AS uuid),CAST(:b AS jsonb),:c)"),
                         {"r": run_id, "b": body, "c": complete})
    row = run_row(database, run_id)
    assert row["status"] == "succeeded" and row["completed_at"] is not None
    assert row["report"] == {"end_to_end_complete": True}


def test_an_unregistered_run_cannot_be_reconciled(database):
    coordinator = RunCoordinator(Store(database.application))
    with pytest.raises(Conflict, match="not registered"):
        coordinator.reconcile(str(uuid4()))
    assert coordinator.pinned_readings(str(uuid4())) == {}


def test_the_application_login_cannot_write_the_run_table(database):
    with pytest.raises(DBAPIError):
        with database.application.begin() as conn:
            conn.execute(
                text("INSERT INTO mdm.run(run_id,scope) VALUES(CAST(:r AS uuid),'{}'::jsonb)"),
                {"r": str(uuid4())},
            )




def test_a_waiting_link_is_counted_and_does_not_hold_the_run_open(database):
    # Mastering to-do 13: a link waiting for its other end is reported, not
    # an unresolved review, so the run can complete.
    store = Store(database.application)
    coordinator = RunCoordinator(store)
    run_id = str(uuid4())
    coordinator.start(run_id, ["w1"], manifest_digest="w" * 64)
    child = core.source(key="w1", relationships=[{
        "type": "IS_DIRECTLY_CONSOLIDATED_BY", "target_subject": "not-a-company-yet",
        "valid_from": core.AT, "valid_to": None, "scope": "consolidated"}])
    identity, binding = core.identity_and_binding(child)
    MergeStage(store).apply(
        batch_id="w1", run_id=run_id, policy_digest=database.policy, consumer="load",
        expected_checkpoint=0, checkpoint=1, as_of=core.AS_OF, assertions=[child],
        identities=[identity], decisions=[binding])
    with database.admin.connect() as conn:
        reasons = conn.execute(text(
            "SELECT body->>'reason', body->>'open' FROM mdm.current_record WHERE object_type='review'")).all()
    assert reasons == [("unresolved_endpoint", "false")], reasons
    report = coordinator.reconcile(run_id)
    assert report["waiting_links"] == 1
    assert report["unresolved_reviews"] == 0
