"""A batch with identity work is assessed and saved in one transaction: written once."""

from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean.evidence import decision
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Conflict, Store
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database


def calls(engine) -> list[str]:
    seen = []

    @event.listens_for(engine, "before_cursor_execute")
    def _seen(conn, cursor, statement, parameters, context, executemany):
        for name in ("preview_batch", "save_batch", "record_match_proposal"):
            if f"mdm.{name}(" in statement:
                seen.append(name)
    return seen


def proposals(database):
    with database.application.connect() as conn:
        return [dict(r) for r in conn.execute(text(
            "SELECT a.body->>'outcome' AS outcome, array_agg(e.event ORDER BY e.event_id) AS events "
            "FROM mdm.match_proposal a LEFT JOIN mdm.match_proposal_event e USING(assessment_id) "
            "GROUP BY a.assessment_id, a.body->>'outcome'")).mappings()]


def test_a_batch_that_binds_is_written_once_with_its_proposal(database):
    seen = calls(database.application)
    command = core.assessment_command(database)
    result = MergeStage(Store(database.application)).apply(**command)
    assert result["generation"] == 1
    assert seen == ["record_match_proposal", "save_batch"]
    assert proposals(database) == [{"outcome": "ready", "events": ["ready", "observed", "applied"]}]
    assert len(core.documents(database, "entity")) == 1


def test_a_refused_batch_keeps_a_rejected_proposal_and_saves_nothing(database):
    command = core.assessment_command(database)
    # A Company bound with evidence of another subject is refused under the lock.
    bound = command["decisions"][0]
    other = core.source("c2")
    command["decisions"] = [decision("bind", actor="steward", reason="fixture source reviewed", at=bound["at"],
                                     subject=bound["subject"], entity_id=bound["entity_id"],
                                     evidence=[other["assertion_id"]])]
    with pytest.raises((Conflict, DBAPIError)):
        MergeStage(Store(database.application)).apply(**command)
    found = proposals(database)
    assert [p["outcome"] for p in found] == ["rejected"]
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 0


def test_redelivery_of_a_saved_batch_is_a_duplicate(database):
    stage = MergeStage(Store(database.application))
    command = core.assessment_command(database)
    first = stage.apply(**command)
    again = stage.apply(**{**command, "run_id": str(uuid4())})
    assert again["generation"] == first["generation"] and again.get("duplicate") is True


def test_a_batch_the_database_refuses_at_save_keeps_a_rejected_proposal(database, monkeypatch):
    stage = MergeStage(Store(database.application))
    command = core.assessment_command(database)
    original = stage.store.commit

    def refused(conn, request, run_id):
        return original(conn, {**request, "checkpoint": request["expected_checkpoint"]}, run_id)

    monkeypatch.setattr(stage.store, "commit", refused)
    with pytest.raises(DBAPIError):
        stage.apply(**command)
    # The ready proposal went back with its batch; the refusal is kept.
    assert [p["outcome"] for p in proposals(database)] == ["rejected"]
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 0
