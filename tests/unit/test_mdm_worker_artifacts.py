"""Immutable preparation and staging boundaries without database effects."""
import hashlib
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import mdm_merge, mdm_prepare


def test_preparation_chunks_rows_and_verifies_every_records_file(tmp_path):
    store = Artifacts()
    source = hashlib.sha256(b"captured").hexdigest()
    reading = store.put(tmp_path.as_uri(), {"version": 1, "artifacts": [
        {"input": {"sha256": source}, "tables": {"company": [{"id": n} for n in range(1001)]}}
    ]})
    envelope = {"input": reading, "output": (tmp_path / "prepared" / "manifest.json").as_uri(),
                "checks": ["mdm.prepared"], "keys": {
                    "table": "company", "dataset": "fixture.company", "policy": "a" * 64,
                    "consumer": "fixture", "batch_id": "fixture", "as_of": "2026-01-01T00:00:00Z"}}
    candidate = mdm_prepare.execute(envelope, store)
    assert mdm_prepare.execute(envelope, store) == candidate
    manifest = store.json(candidate)
    assert [b["input"]["record_count"] for b in manifest["batches"]] == [1000, 1]
    assert [(b["expected_checkpoint"], b["checkpoint"]) for b in manifest["batches"]] == [(0, 1), (1, 2)]
    assert mdm_prepare.verify({**envelope, "candidate": candidate}, store) == ({"mdm.prepared": True}, [])
    (tmp_path / "prepared" / manifest["batches"][1]["input"]["path"]).write_bytes(b"corrupted\n")
    with pytest.raises(ValueError, match="records file.*differs"):
        mdm_prepare.verify({**envelope, "candidate": candidate}, store)


@pytest.mark.parametrize("name", ["../escape.jsonl", "/absolute.jsonl", "manifest.json"])
def test_staging_refuses_input_paths_that_escape_or_replace_the_manifest(tmp_path, name):
    store = Artifacts()
    ref = store.put(tmp_path.as_uri(), {"batches": [{"input": {"path": name, "sha256": "a" * 64}}]})
    staging = tmp_path / "staging"
    staging.mkdir()
    with pytest.raises(ValueError, match="file beside the manifest"):
        mdm_merge._stage({"input": ref}, store, staging)
    assert (staging / "manifest.json").read_bytes() == store.verified(ref)
