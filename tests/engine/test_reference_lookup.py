"""Frozen reference conversion, compared with the retained jurisdiction oracle."""
import copy
import json

import pytest

from edgar_warehouse.rules import files
from tests.support import place_codes
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from edgar_warehouse.mdm.clean.names import edgar_jurisdiction
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import source_read


def contract():
    return {"execution": {"profile": "source.read", "workers": 1, "max_artifacts": 1}, "read": {
        "format": "jsonl", "limits": {"max_bytes": 1048576, "max_records": 2000},
        "references": {"places": place_codes.table()},
        "tables": {"rows": {"each": "record", "columns": {"jurisdiction": {"lookup": {
            "reference": "places", "column": "iso", "key": {"text": {"path": "code", "coerce": "python", "case": "upper"}}}}}}}}}


def test_all_sec_place_codes_and_conversion_cases_match_retained_jurisdiction():
    codes = place_codes.table()
    values = [v for code in codes for v in (code, code.lower(), f" \t{code.lower()}\n")]
    values += [None, "", "unknown", "XX", True, False, 1, 1.2, [], {}, ["DE"], "ｄｅ", "ß", "ﬀ"]
    result = SourceEngine(contract()).read(b"".join(json.dumps({"code": code}).encode() + b"\n" for code in values))
    assert result.deferred == []
    assert result.tables["rows"] == [{"jurisdiction": edgar_jurisdiction(code)} for code in values]


def test_exact_keys_and_explicit_case_do_not_change_default_text():
    spec = contract()
    spec["read"]["tables"]["rows"]["columns"]["key"] = {"text": {"path": "code"}}
    result = SourceEngine(spec).read(b'{"code":" de "}\n')
    assert result.tables["rows"] == [{"jurisdiction": "US-DE", "key": "de"}]


def test_worker_verifies_frozen_reference_and_refuses_a_changed_contract(tmp_path):
    store = Artifacts()
    spec = contract()
    pinned = store.put(tmp_path.as_uri(), spec)
    data = store.put_bytes((tmp_path / "data.jsonl").as_uri(), b'{"code":"de"}\n')
    manifest = store.put(tmp_path.as_uri(), {"version": 1, "contract": pinned, "artifacts": [data]})
    envelope = {"input": manifest, "output": (tmp_path / "reading.json").as_uri(), "checks": ["source.output"]}
    candidate = source_read.execute(envelope, store)
    assert store.json(candidate)["artifacts"][0]["tables"]["rows"] == [{"jurisdiction": "US-DE"}]
    assert source_read.verify({**envelope, "candidate": candidate}, store) == ({"source.output": True}, [])
    changed = copy.deepcopy(spec)
    changed["read"]["references"]["places"]["DE"]["iso"] = "US-NV"
    altered = store.put(tmp_path.as_uri(), changed)
    other_manifest = store.put(tmp_path.as_uri(), {"version": 1, "contract": altered, "artifacts": [data]})
    with pytest.raises(ValueError):
        source_read.verify({**envelope, "input": other_manifest, "candidate": candidate}, store)


def test_missing_key_error_remains_an_artifact_failure():
    spec = contract()
    spec["read"]["tables"]["rows"]["columns"]["jurisdiction"]["lookup"]["on_missing"] = "error"
    with pytest.raises(SourceRejected) as error:
        SourceEngine(spec).read(b'{"code":"unknown"}\n')
    assert error.value.code == "lookup_missing"
