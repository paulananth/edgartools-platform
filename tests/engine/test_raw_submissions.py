"""Complete typed source evidence through native parsing and immutable preparation."""
import json
from pathlib import Path

import pytest

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.workers import source_read, mdm_prepare
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean.adapters import normalize, UnsupportedRecord

PERSON = files.source("sec.submissions.person")


def outcome(row, publication):
    code = "sec.submissions.person.v1"
    try:
        return {"assertion": normalize(row, source_code=code, contract=files.mdm_contract("sec.submissions.person", code),
                                       policy=files.policy(), publication=publication)}
    except UnsupportedRecord as error:
        return {"deferred": error.reason, "detail": error.detail, "probable_kind": error.probable_kind}


@pytest.mark.parametrize("payload", [
    {"cik": "1", "name": "JOHN DOE", "entityType": "other", "tickers": [], "sic": ""},
    {"cik": "320193", "name": "Apple Inc.", "entityType": "operating", "tickers": ["AAPL"]},
    {"cik": "2", "name": "ALICE DOE", "entityType": "other", "tickers": ["X"], "sic": ""},
    {"cik": "3", "name": "JOHN DOE", "entityType": "other", "ownerOrg": True, "ein": "000000000"},
    {"cik": "4", "name": "é🦀", "addresses": {"business": {}}, "formerNames": [], "filings": {"recent": {"form": ["4", "6-K"]}}},
    {"n": 9007199254740993, "u": 18446744073709551615, "float": 1.0, "zero": -0.0, "flag": True,
     "x": [[], {}, None, False, {"$": "x", "@lang": "en", "item": [1]}]},
])
def test_native_record_preserves_complete_json_and_governed_outcomes(payload):
    actual = SourceEngine(PERSON).read(json.dumps(payload).encode()).tables["submissions"][0]["record"]
    assert json.dumps(actual, sort_keys=True) == json.dumps(payload, sort_keys=True)
    publication = {"publication_key": "pinned", "revision": 1, "artifact_sha256": "0"*64, "member": "raw.json"}
    assert outcome(actual, publication) == outcome(payload, publication)


def test_worker_prepares_unmodified_records_and_verifier_binds_selection(tmp_path):
    store = Artifacts()
    payload = {"cik": "1", "name": "JOHN DOE", "tickers": [], "sic": "", "unknown": {"x": [None, True]}}
    contract = store.put(tmp_path.as_uri(), PERSON)
    data = store.put_bytes((tmp_path / "raw.json").as_uri(), json.dumps(payload).encode())
    manifest = store.put(tmp_path.as_uri(), {"version": 1, "contract": contract, "artifacts": [data]})
    envelope = {"input": manifest, "output": (tmp_path / "reading.json").as_uri(), "checks": ["source.output"]}
    reading = source_read.execute(envelope, store)
    assert source_read.verify({**envelope, "candidate": reading}, store) == ({"source.output": True}, [])
    keys = {"record_column": "record", "table": "submissions", "dataset": "sec.submissions.person.v1", "policy": "0"*64,
            "consumer": "qualified", "batch_id": "raw", "as_of": "2026-10-04T00:00:00Z"}
    prepare = {"input": reading, "output": (tmp_path / "mdm" / "manifest.json").as_uri(), "checks": ["mdm.prepared"], "keys": keys}
    result = mdm_prepare.execute(prepare, store)
    assert mdm_prepare.verify({**prepare, "candidate": result}, store) == ({"mdm.prepared": True}, [])
    batch = store.json(result)["batches"][0]
    assert json.loads((tmp_path / "mdm" / batch["input"]["path"]).read_bytes()) == payload
    with pytest.raises(ValueError):
        mdm_prepare.verify({**prepare, "keys": {k: v for k, v in keys.items() if k != "record_column"}, "candidate": result}, store)


@pytest.mark.parametrize("record", [None, [], "text", 1, True])
def test_invalid_record_column_is_refused_before_preparation_writes(tmp_path, record):
    store = Artifacts()
    reading = store.put(tmp_path.as_uri(), {"version": 1, "artifacts": [{"input": {"sha256": "0"*64},
                       "tables": {"rows": [{"record": record}]}}]})
    output = tmp_path / "mdm" / "manifest.json"
    keys = {"table": "rows", "record_column": "record", "dataset": "test", "policy": "0"*64, "consumer": "test",
            "batch_id": "test", "as_of": "2026-10-04T00:00:00Z"}
    with pytest.raises(ValueError, match="record_column must hold an object"):
        mdm_prepare.execute({"input": reading, "output": output.as_uri(), "keys": keys, "checks": ["mdm.prepared"]}, store)
    assert not output.parent.exists()


@pytest.mark.parametrize("number", [-9223372036854775809, 18446744073709551616])
def test_raw_number_range_is_refused_rather_than_rounded(number):
    with pytest.raises(SourceRejected) as error:
        SourceEngine(PERSON).read(json.dumps({"cik": number}).encode())
    assert error.value.code == "value_number_range"


@pytest.mark.parametrize("stage", ["source", "records", "manifest"])
def test_worker_byte_budgets_fail_before_writing_unverifiable_output(tmp_path, monkeypatch, stage):
    store = Artifacts()
    payload = {"cik": "1", "name": "JOHN DOE", "nested": {"text": "x" * 256}}
    contract = store.put(tmp_path.as_uri(), PERSON)
    data = store.put_bytes((tmp_path / "raw.json").as_uri(), json.dumps(payload).encode())
    manifest = store.put(tmp_path.as_uri(), {"version": 1, "contract": contract, "artifacts": [data]})
    output = tmp_path / "reading.json"
    source = {"input": manifest, "output": output.as_uri(), "checks": ["source.output"]}
    if stage == "source":
        monkeypatch.setattr(source_read, "OUTPUT_BYTES", 128)
        with pytest.raises(ValueError, match="verifier byte budget"):
            source_read.execute(source, store)
        assert not output.exists()
        return
    reading = source_read.execute(source, store)
    monkeypatch.setattr(mdm_prepare, "RECORD_BYTES" if stage == "records" else "MANIFEST_BYTES", 128)
    keys = {"record_column": "record", "table": "submissions", "dataset": "person", "policy": "0"*64,
            "consumer": "qualified", "batch_id": "raw", "as_of": "2026-10-04T00:00:00Z"}
    target = tmp_path / "mdm" / "manifest.json"
    with pytest.raises(ValueError, match="verifier byte budget"):
        mdm_prepare.execute({"input": reading, "output": target.as_uri(), "checks": ["mdm.prepared"], "keys": keys}, store)
    assert not target.parent.exists()
