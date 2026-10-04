"""Constructed native records cross immutable worker boundaries unchanged."""
import json
from pathlib import Path

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers import mdm_prepare, source_read

CONTRACT = files.load(Path(__file__).parent / "fixtures/object-records.yaml")


def test_constructed_record_survives_worker_receipts_and_preparation(tmp_path):
    store = Artifacts()
    contract = store.put(tmp_path.as_uri(), CONTRACT)
    raw = store.put_bytes((tmp_path / "source.json").as_uri(), json.dumps({
        "cik": 9007199254740993, "code": "DE", "street": "  x  ",
        "evidence": [True, None, {"unknown": 18446744073709551615}]}).encode())
    context = store.put(tmp_path.as_uri(), {"version": 1, "input": raw, "values": {"run": "trial"}})
    manifest = store.put(tmp_path.as_uri(), {"version": 2, "contract": contract,
                                           "artifacts": [{"input": raw, "context": context}]})
    read = {"input": manifest, "output": (tmp_path / "reading.json").as_uri(), "checks": ["source.output"]}
    receipt = source_read.execute(read, store)
    assert source_read.verify({**read, "candidate": receipt}, store) == ({"source.output": True}, [])
    expected = {"cik": 9007199254740993, "evidence": [True, None, {"unknown": 18446744073709551615}],
                "business_address": {"street": "  x  ", "country": "US"}, "origin": {"run": "trial", "row": 1}}
    assert store.json(receipt)["artifacts"][0]["tables"]["rows"] == [{"record": expected}]
    keys = {"table": "rows", "record_column": "record", "dataset": "fixture.objects", "policy": "0" * 64,
            "consumer": "trial", "batch_id": "objects", "as_of": "2026-10-04T00:00:00Z"}
    prepare = {"input": receipt, "output": (tmp_path / "mdm/manifest.json").as_uri(),
               "checks": ["mdm.prepared"], "keys": keys}
    prepared = mdm_prepare.execute(prepare, store)
    assert mdm_prepare.verify({**prepare, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    batch = store.json(prepared)["batches"][0]
    record_file = tmp_path / "mdm" / batch["input"]["path"]
    assert json.loads(record_file.read_bytes()) == expected
    record_file.write_text(json.dumps({**expected, "cik": 1}))
    with pytest.raises(ValueError):
        mdm_prepare.verify({**prepare, "candidate": prepared}, store)


def test_nested_refusal_leaves_no_source_output(tmp_path):
    store = Artifacts()
    contract = store.put(tmp_path.as_uri(), CONTRACT)
    raw = store.put_bytes((tmp_path / "source.json").as_uri(), b'{"cik":1,"evidence":18446744073709551616}')
    context = store.put(tmp_path.as_uri(), {"version": 1, "input": raw, "values": {"run": "trial"}})
    manifest = store.put(tmp_path.as_uri(), {"version": 2, "contract": contract,
                                           "artifacts": [{"input": raw, "context": context}]})
    output = tmp_path / "reading.json"
    with pytest.raises(SourceRejected) as rejected:
        source_read.execute({"input": manifest, "output": output.as_uri(), "checks": ["source.output"]}, store)
    assert rejected.value.code == "value_number_range"
    assert not output.exists()
