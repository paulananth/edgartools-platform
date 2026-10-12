"""mdm.prepare over a list of readings, as one caller publication (Issue 20 slice 20c)."""
import json
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_read

CONTRACT = files.load(Path(__file__).parent / "fixtures/object-records.yaml")
KEYS = {"table": "rows", "record_column": "record", "dataset": "fixture.objects", "policy": "0" * 64,
        "consumer": "bundle", "batch_id": "company:bundle", "as_of": "2026-10-04T00:00:00Z"}


def reading(store, root, cik):
    contract = store.put(root.as_uri(), CONTRACT)
    raw = store.put_bytes((root / f"source-{cik}.json").as_uri(), json.dumps({"cik": cik, "street": "x"}).encode())
    context = store.put(root.as_uri(), {"version": 1, "input": raw, "values": {"run": "trial"}})
    manifest = store.put(root.as_uri(), {"version": 2, "contract": contract,
                                         "artifacts": [{"input": raw, "context": context}]})
    task = {"input": manifest, "output": (root / f"reading-{cik}.json").as_uri(), "checks": ["source.output"]}
    return source_read.execute(task, store)


def prepare(store, root, keys, ciks=(3, 1, 2)):
    listed = store.put(root.as_uri(), {"version": 1, "readings": [reading(store, root, cik) for cik in ciks]})
    task = {"input": listed, "output": (root / "mdm/manifest.json").as_uri(), "checks": ["mdm.prepared"], "keys": keys}
    candidate = mdm_prepare.execute(task, store)
    assert mdm_prepare.verify({**task, "candidate": candidate}, store) == ({"mdm.prepared": True}, [])
    return store.json(candidate)


def test_a_readings_list_with_a_publication_is_one_publication_in_reading_order(tmp_path):
    store = Artifacts()
    manifest = prepare(store, tmp_path, {**KEYS, "publication_key": "capture:bundle", "revision": "7"})
    (batch,) = manifest["batches"]
    assert batch["batch_id"] == "company:bundle:0" and batch["input"]["path"] == "records.0.jsonl"
    assert batch["input"]["publication"] == {"publication_key": "capture:bundle", "revision": 7, "effective_at": None}
    rows = [json.loads(line) for line in (tmp_path / "mdm/records.0.jsonl").read_text().splitlines()]
    assert [row["cik"] for row in rows] == [3, 1, 2]


def test_a_readings_list_without_a_publication_keeps_one_per_artifact(tmp_path):
    manifest = prepare(Artifacts(), tmp_path, KEYS)
    assert len(manifest["batches"]) == 3
    assert {b["input"]["publication"]["revision"] for b in manifest["batches"]} == {1}
    assert len({b["input"]["publication"]["publication_key"] for b in manifest["batches"]}) == 3


@pytest.mark.parametrize("edit", [{"publication_key": "p"}, {"revision": "1"}, {"publication_key": "p", "revision": "-1"},
                                  {"publication_key": "p", "revision": 1}, {"publication_key": "p", "revision": "01"},
                                  {"publication_key": "", "revision": "1"},
                                  {"publication_key": "p", "revision": "1", "effective_column": "at"}])
def test_a_publication_needs_its_key_and_revision_and_states_one_time(tmp_path, edit):
    with pytest.raises(ValueError):
        prepare(Artifacts(), tmp_path, {**KEYS, **edit})


@pytest.mark.parametrize("listed", [[], "x", [{"uri": "file:///x", "sha256": "0" * 64}] * 257])
def test_a_readings_list_is_bounded(tmp_path, listed):
    store = Artifacts()
    document = store.put(tmp_path.as_uri(), {"version": 1, "readings": listed})
    task = {"input": document, "output": (tmp_path / "mdm/manifest.json").as_uri(), "checks": ["mdm.prepared"],
            "keys": KEYS}
    with pytest.raises(ValueError):
        mdm_prepare.execute(task, store)
