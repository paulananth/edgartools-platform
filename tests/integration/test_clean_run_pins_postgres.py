"""Real PG16: a run keeps the mappings it started with (rebuild ticket 103).

A corrected mapping registered while a run is part way through applies to the
next run, never to the rest of this one: every batch, and every resume, reads
under the mapping version the run's frozen scope names.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.mdm.clean.execution import execute_manifest
from edgar_warehouse.mdm.clean.store import Conflict, Store, register_policy
from tests.support.rules_authority import register_dataset

FIXTURE = Path(__file__).parents[1] / "fixtures" / "clean_mdm" / "v1"
CODE = "fixture.representative"
SECOND = {"key": "second", "kind": "company", "name": "Synthetic Second Company",
          "valid_from": "2026-01-01T00:00:00+00:00"}


def manifest(folder: Path) -> Path:
    """The representative batch, then a second batch of the same source."""
    folder.mkdir()
    body = json.loads((FIXTURE / "manifest.json").read_text())
    first = body["batches"][0]
    (folder / "records.jsonl").write_bytes((FIXTURE / "records.jsonl").read_bytes())
    raw = (json.dumps(SECOND, sort_keys=True) + "\n").encode()
    (folder / "second.jsonl").write_bytes(raw)
    second = {"batch_id": "representative-second", "stage": "mastering", "consumer": "fixture/second",
              "expected_checkpoint": 0, "checkpoint": 1,
              "input": {**first["input"], "path": "second.jsonl", "sha256": hashlib.sha256(raw).hexdigest()}}
    body["batches"] = [first, second]
    path = folder / "manifest.json"
    path.write_text(json.dumps(body))
    return path


@pytest.fixture
def registered(database):
    contract = json.loads((FIXTURE / "dataset.json").read_text())
    with database.admin.begin() as conn:
        register_policy(conn, json.loads((FIXTURE / "policy.json").read_text()))
        register_dataset(conn, CODE, database.registry, contract)
    return contract


def correct_mapping(database, contract):
    with database.admin.begin() as conn:
        register_dataset(conn, CODE, database.registry, {**contract, "semantics": "snapshot"})


def run(database, path, run_id, limit):
    store = Store(database.application)
    return execute_manifest(store, path=str(path), run_id=run_id,
                            stage="mastering", limit=limit)


def versions(database, batch_id):
    with database.admin.connect() as conn:
        return set(conn.scalars(text("SELECT mapping_version FROM mdm.source_reading WHERE batch_id=:b"),
                                {"b": batch_id}))


def test_a_resumed_run_reads_its_later_batches_under_the_mapping_it_started_with(database, registered,
                                                                                    tmp_path):
    path, run_id = manifest(tmp_path / "run"), str(uuid4())
    # Ten records: the first batch alone fits, so the run stops part way.
    assert run(database, path, run_id, limit=10)["missing_batches"] == ["representative-second"]
    correct_mapping(database, registered)

    resumed = run(database, path, run_id, limit=10)

    assert resumed["missing_batches"] == []
    assert versions(database, "representative-v1") == {1}
    assert versions(database, "representative-second") == {1}
    with database.admin.connect() as conn:
        scope = conn.scalar(text("SELECT scope FROM mdm.run WHERE run_id=CAST(:r AS uuid)"), {"r": run_id})
    assert scope["mapping_versions"] == {CODE: 1}


def test_a_new_run_reads_under_the_mapping_registered_since(database, registered, tmp_path):
    run(database, manifest(tmp_path / "first"), str(uuid4()), limit=10)
    correct_mapping(database, registered)
    later = manifest(tmp_path / "later")
    body = json.loads(later.read_text())
    for batch in body["batches"]:  # a later delivery, its own batches
        batch["batch_id"] += "-later"
        batch["expected_checkpoint"], batch["checkpoint"] = 1, 2
    body["batches"][1]["expected_checkpoint"], body["batches"][1]["checkpoint"] = 0, 1
    body["batches"][0].pop("decisions")
    body["batches"][0].pop("identities")
    later.write_text(json.dumps(body))

    assert run(database, later, str(uuid4()), limit=20)["missing_batches"] == []

    assert versions(database, "representative-v1-later") == {2}
    assert versions(database, "representative-second-later") == {2}


def test_a_run_refuses_to_start_when_a_source_it_reads_is_not_registered(database, tmp_path):
    with database.admin.begin() as conn:
        register_policy(conn, json.loads((FIXTURE / "policy.json").read_text()))
    run_id = str(uuid4())
    with pytest.raises(Conflict, match="Unregistered dataset"):
        run(database, manifest(tmp_path / "run"), run_id, limit=10)
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.run WHERE run_id=CAST(:r AS uuid)"), {"r": run_id}) == 0
