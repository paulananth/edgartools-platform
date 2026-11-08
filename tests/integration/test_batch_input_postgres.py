"""A prepared batch is read under its registered reading, and a member that does not match its manifest is refused."""

import json

import pytest

from edgar_warehouse.mdm.execution import batch_input
from edgar_warehouse.mdm.store import Conflict, Store
from tests.integration.test_run_pins_postgres import manifest, registered  # noqa: F401


def test_a_member_the_manifest_does_not_describe_is_refused_before_any_record_is_read(database, registered, tmp_path):
    path = manifest(tmp_path / "run")
    batch = json.loads(path.read_text())["batches"][0]
    assert batch_input(batch, path.parent.resolve(), Store(database.application))["assertions"]
    for field, value, error, reason in [
        ("path", "../outside.jsonl", ValueError, "inside the manifest directory"),
        ("sha256", "0" * 64, Conflict, "Source artifact digest mismatch"),
        ("record_count", 99, Conflict, "record_count mismatch"),
    ]:
        wrong = {**batch, "input": {**batch["input"], field: value}}
        with pytest.raises(error, match=reason):
            batch_input(wrong, path.parent.resolve(), Store(database.application))
