"""A match proposal stores the hash of its effects, not a second copy (013)."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, canonical
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database
MIGRATIONS = Path(__file__).parents[2] / "edgar_warehouse" / "mdm" / "migrations"


def stored(database, key):
    with database.application.connect() as conn:
        return conn.scalar(text("SELECT body FROM mdm.match_proposal WHERE assessment_id=:k"), {"k": key})


def record(conn, body, run_id):
    return conn.scalar(text("SELECT mdm.record_match_proposal(:body,CAST(:run AS uuid))"),
                       {"body": canonical(body), "run": run_id})


def test_a_proposal_keeps_the_hash_of_its_effects_and_applies(database):
    stage = MergeStage(Store(database.application))
    command = core.assessment_command(database)
    candidate = stage.assess(**command)
    body = stored(database, candidate["assessment_id"])
    assert "effects" not in body and len(body["effects_sha256"]) == 64
    assert body["command"] == candidate["command"]
    stage.apply_assessment(candidate["assessment_id"], run_id=command["run_id"])
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 1


def test_a_proposal_stored_before_the_hash_still_applies(database):
    """A populated store: a proposal recorded by the 001 function keeps its
    effects whole and is checked as before once 013 is installed."""
    baseline = (MIGRATIONS / "001_mdm.sql").read_text()
    start = baseline.index("CREATE FUNCTION mdm.record_match_proposal(")
    old = baseline[start:baseline.index("$$;\n", start) + 4].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    with database.admin.begin() as conn:
        conn.exec_driver_sql(old)
    stage = MergeStage(Store(database.application))
    command = core.assessment_command(database)
    candidate = stage.assess(**command)
    assert "effects" in stored(database, candidate["assessment_id"])
    with database.admin.begin() as conn:
        conn.execute(text((MIGRATIONS / "013_proposal_effects_hash.sql").read_text()))
    stage.apply_assessment(candidate["assessment_id"], run_id=command["run_id"])
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 1


def test_effects_that_differ_from_the_request_are_refused(database):
    stage = MergeStage(Store(database.application))
    command = core.assessment_command(database)
    candidate = stage.assess(**command)
    assessed = {**candidate["effects"], "expected_generation": 0, "assessment_id": candidate["assessment_id"]}
    with pytest.raises(DBAPIError, match="differs from assessed"), database.application.begin() as conn:
        stage.store.commit(conn, {**assessed, "projections": []}, command["run_id"])


def test_the_bound_applies_to_the_stored_body(database):
    stage = MergeStage(Store(database.application))
    command = core.assessment_command(database)
    candidate = stage.assess(**command)
    body = {k: v for k, v in candidate.items() if k != "assessment_id"}
    # Large effects are stored as their hash: accepted.
    large = {**body, "rule_version": "large-effects", "effects": {**body["effects"], "pad": "x" * (20 * 1024**2)}}
    with database.application.begin() as conn:
        key = record(conn, large, command["run_id"])
    assert len(canonical(stored(database, key))) < 1024**2
    # A stored body over 16 MB is refused.
    over = {**body, "rule_version": "large-command", "command": {**body["command"], "pad": "x" * (17 * 1024**2)}}
    with pytest.raises(DBAPIError, match="unbounded identity assessment"), database.application.begin() as conn:
        record(conn, over, command["run_id"])
