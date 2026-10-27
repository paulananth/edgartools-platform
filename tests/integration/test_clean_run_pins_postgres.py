"""Shared fixture builders; retired calculation tests are catalogued in ticket 08."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from edgar_warehouse.mdm.clean.store import register_policy
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
