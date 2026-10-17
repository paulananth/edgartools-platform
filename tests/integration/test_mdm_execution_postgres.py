"""The execution interface owns complete, bounded and preview mastering."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.mdm.clean.connections import engine_from_env
from edgar_warehouse.mdm.clean.execution import execute_manifest
from edgar_warehouse.mdm.clean.store import Conflict, Store
from tests.integration.test_clean_run_pins_postgres import manifest, registered  # noqa: F401


def test_complete_execution_commits_every_batch_and_retry_has_no_new_effects(database, registered, tmp_path):
    path, run_id = manifest(tmp_path / "run"), str(uuid4())
    store = Store(database.application)

    result = execute_manifest(store, path=str(path), run_id=run_id)

    assert result["records_processed"] == 11
    assert len(result["commits"]) == 2
    assert result["missing_batches"] == []
    # Publication and stewardship are separate from committing the manifest.
    assert result["end_to_end_complete"] is False
    assert execute_manifest(store, path=str(path), run_id=run_id)["commits"] == []
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 2
        assert conn.scalar(text("SELECT count(*) FROM mdm.run")) == 1


def test_a_bound_stops_between_atomic_batches_and_can_resume(database, registered, tmp_path):
    path, run_id = manifest(tmp_path / "run"), str(uuid4())
    store = Store(database.application)
    with pytest.raises(ValueError, match="Next atomic batch requires --limit at least 10"):
        execute_manifest(store, path=str(path), run_id=run_id, limit=9)
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 0

    first = execute_manifest(store, path=str(path), run_id=run_id, limit=10)
    assert first["records_processed"] == 10
    assert first["missing_batches"] == ["representative-second"]
    resumed = execute_manifest(store, path=str(path), run_id=run_id, limit=1)
    assert resumed["records_processed"] == 1
    assert resumed["missing_batches"] == []


def test_preview_proposes_one_atomic_batch_without_registering_or_committing(database, registered, tmp_path):
    path, run_id = manifest(tmp_path / "run"), str(uuid4())

    result = execute_manifest(Store(database.application), path=str(path), run_id=run_id, preview=True)

    assert result["preview"] is True
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 0
        assert conn.scalar(text("SELECT count(*) FROM mdm.run")) == 0


def test_bounded_stages_preserve_manifest_order(database, registered, tmp_path):
    path, run_id = manifest(tmp_path / "run"), str(uuid4())
    body = json.loads(path.read_text())
    body["batches"][1]["stage"] = "stewardship"
    path.write_text(json.dumps(body))
    store = Store(database.application)
    with pytest.raises(Conflict, match="Complete preceding manifest batches"):
        execute_manifest(store, path=str(path), run_id=run_id, stage="stewardship", limit=10)
    assert execute_manifest(store, path=str(path), run_id=run_id, stage="mastering", limit=10)[
        "missing_batches"] == ["representative-second"]
    assert execute_manifest(store, path=str(path), run_id=run_id, stage="stewardship", limit=1)[
        "missing_batches"] == []


def test_complete_execution_follows_all_stages_in_manifest_order(database, registered, tmp_path):
    path = manifest(tmp_path / "run")
    body = json.loads(path.read_text())
    body["batches"][1]["stage"] = "stewardship"
    path.write_text(json.dumps(body))

    result = execute_manifest(Store(database.application), path=str(path), run_id=str(uuid4()))

    assert result["records_processed"] == 11
    assert result["missing_batches"] == []


@pytest.mark.parametrize("field,value,error,reason", [
    ("path", "../outside.jsonl", ValueError, "inside the manifest directory"),
    ("sha256", "0" * 64, Conflict, "Source artifact digest mismatch"),
    ("record_count", 99, Conflict, "record_count mismatch"),
])
def test_execution_refuses_invalid_source_members_before_committing(database, registered, tmp_path,
                                                                    field, value, error, reason):
    path = manifest(tmp_path / "run")
    body = json.loads(path.read_text())
    body["batches"][0]["input"][field] = value
    path.write_text(json.dumps(body))
    with pytest.raises(error, match=reason):
        execute_manifest(Store(database.application), path=str(path), run_id=str(uuid4()))
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 0


def test_retained_duplicate_batches_spend_no_record_budget(database, registered, tmp_path):
    path = manifest(tmp_path / "run")
    store = Store(database.application)
    execute_manifest(store, path=str(path), run_id=str(uuid4()), limit=10)

    result = execute_manifest(store, path=str(path), run_id=str(uuid4()), limit=1)

    assert result["records_processed"] == 1
    assert [commit["duplicate"] for commit in result["commits"]] == [True, False]
    assert result["missing_batches"] == []


def test_complete_execution_refuses_no_progress_instead_of_looping(database, registered, tmp_path):
    path = manifest(tmp_path / "run")
    with pytest.raises(ValueError, match="MDM made no progress"):
        execute_manifest(Store(database.application), path=str(path), run_id=str(uuid4()),
                         stage="derive-relationships")
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 0


@pytest.mark.parametrize("restricted,expected_role", [(True, "clean_application"), (False, "postgres")])
def test_connection_role_selection_is_preserved(database, monkeypatch, restricted, expected_role):
    monkeypatch.setenv("EXECUTION_TEST_CONNECTION", database.admin.url.render_as_string(hide_password=False))
    monkeypatch.setenv("MDM_APPLICATION_ROLE", "clean_application")
    engine = engine_from_env("EXECUTION_TEST_CONNECTION", restricted=restricted)
    try:
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT current_user")) == expected_role
    finally:
        engine.dispose()
