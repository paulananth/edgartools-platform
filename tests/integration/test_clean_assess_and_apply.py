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


def test_a_store_with_a_ready_proposal_takes_020_and_the_proposal_still_applies(database):
    """Migration 020 (ticket 77) on a populated store: a ready proposal
    recorded with its scope and snapshot before 020 applies once 020 drops the
    snapshot; the store's rows are kept."""
    from pathlib import Path

    from edgar_warehouse.mdm.clean import merge, store
    from edgar_warehouse.mdm.clean.store import canonical, migrate

    folder = Path(store.__file__).parents[1] / "migrations"

    def body(file, name):
        sql = (folder / file).read_text()
        start = sql.index(f"FUNCTION mdm.{name}(")
        start = sql.rindex("CREATE", 0, start)
        text_ = sql[start:sql.index("$$;", start) + 3]
        return text_.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)

    core.apply(database, 1, assertions=[core.source("other")])
    with database.admin.begin() as conn:
        for file, name in (("019_merge_stage_no_limit.sql", "match_proposal_snapshot"),
                           ("019_merge_stage_no_limit.sql", "record_match_proposal"),
                           ("013_proposal_effects_hash.sql", "save_batch"),
                           ("001_mdm.sql", "supersede_match_proposal")):
            conn.execute(text(body(file, name)))
        conn.execute(text("GRANT EXECUTE ON FUNCTION mdm.match_proposal_snapshot(jsonb) TO clean_application"))
        # The migration ledger is append-only; only this simulation of an older
        # store goes around that, as the database owner.
        conn.execute(text("SET LOCAL session_replication_role = replica"))
        conn.execute(text("DELETE FROM mdm.migration WHERE name='020_merge_record_by_record.sql'"))
        conn.execute(text("SET LOCAL session_replication_role = origin"))
    stage = MergeStage(Store(database.application))
    command = core.assessment_command(database, expected_checkpoint=0, checkpoint=1, consumer="old")
    candidate = stage.apply(**command, preview=True)["assessment"]
    scope = {"keys": [command["assertions"][0]["subject"]], "sources": [], "consumer": "old"}
    with database.application.begin() as conn:
        snapshot = conn.scalar(text("SELECT mdm.match_proposal_snapshot(CAST(:s AS jsonb))"), {"s": canonical(scope)})
        key = conn.scalar(text("SELECT mdm.record_match_proposal(:b,CAST(:run AS uuid))"), {
            "b": canonical({**candidate, "command": merge._proposal(command), "scope": scope, "snapshot": snapshot}),
            "run": command["run_id"]})
    with database.admin.connect() as conn:
        counts = {t: conn.scalar(text(f"SELECT count(*) FROM mdm.{t}")) for t in ("batch", "source_reading", "match_proposal")}
    migrate(database.admin, application_role="clean_application")
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT to_regprocedure('mdm.match_proposal_snapshot(jsonb)')")) is None
        assert {t: conn.scalar(text(f"SELECT count(*) FROM mdm.{t}")) for t in counts} == counts
    assert stage.apply_assessment(key, run_id=command["run_id"])["generation"] == 2
    assert [p["events"] for p in proposals(database)] == [["ready", "observed", "applied"]]
