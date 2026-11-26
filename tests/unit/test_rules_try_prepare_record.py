"""The prepare-the-record family prepares one invented row with a pasted contract that fixes the entity type."""
import json

from edgar_warehouse.rules.try_page import press
from tests.support.reading import reading

CONTRACT = {
    "schema_version": "1",
    "adapter": {
        "version": "example-v1",
        "kind": "company",
        "record_key": ["id"],
        "identifiers": {"example_id": "ident"},
        "reading": reading({"name": "name"}),
    },
}
ROW = '{"id": "R1", "ident": "ID-100", "name": "Example Works"}'
PUBLICATION = '{"publication_key": "p1", "revision": 1, "artifact_sha256": "%s", "member": "m"}' % ("0" * 64)


def _try(contract=CONTRACT, row=ROW, source="example.records.v1", publication=PUBLICATION, expected=None):
    rule = contract if isinstance(contract, str) else json.dumps(contract)
    return press("Try", "prepare_record", rule=rule,
                 inputs={"row": row, "source": source, "publication": publication}, expected=expected)


def test_the_fixed_type_row_comes_back_with_that_type_key_and_identifier():
    tried = _try()
    assert tried["actual"]["kind"] == "company"
    assert tried["actual"]["record_key"] == "R1"
    assert tried["actual"]["identifiers"] == {"example_id": "ID-100"}
    assert tried["actual"]["fields"] == {"name": {"op": "value", "value": "Example Works"}}
    assert tried["actual"]["source_code"] == "example.records.v1"
    assert _try(expected=tried["actual"])["passed"] is True
    assert _try(expected={"kind": "person"})["passed"] is False


def test_a_row_missing_the_key_is_refused_with_the_engines_reason():
    refused = _try(row='{"ident": "ID-100", "name": "Example Works"}')
    assert refused == {"refused": "The record is set aside: missing_record_identity"}


def test_a_contract_that_contains_classification_is_refused_before_normalize(monkeypatch):
    from edgar_warehouse.rules.bench_families import prepare_record

    def called(*_args, **_kwargs):
        raise AssertionError("normalize ran")

    monkeypatch.setattr(prepare_record, "normalize", called)
    named = {"kind": "company", "rule_id": "example-rule", "version": "1"}
    for contract in [
        {**CONTRACT, "adapter": {**CONTRACT["adapter"], "classification": named}},
        {**CONTRACT, "classification": named},
        {**CONTRACT, "adapter": {**CONTRACT["adapter"], "classification": None}},
    ]:
        refused = _try(contract=contract)
        assert list(refused) == ["refused"]
        assert "contains classification" in refused["refused"]
        assert "Prepare a record whose entity type comes from a rule" in refused["refused"]


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    no_key = {**CONTRACT, "adapter": {k: v for k, v in CONTRACT["adapter"].items() if k != "record_key"}}
    no_reading = {**CONTRACT, "adapter": {k: v for k, v in CONTRACT["adapter"].items() if k != "reading"}}
    no_version = {k: v for k, v in CONTRACT.items() if k != "schema_version"}
    unknown_format = {**CONTRACT, "adapter": {**CONTRACT["adapter"], "record_key_format": "invented"}}
    no_kind = {**CONTRACT, "adapter": {k: v for k, v in CONTRACT["adapter"].items() if k != "kind"}}
    for kwargs in [
        {"contract": "not json"},
        {"contract": "[1]"},
        {"contract": {"schema_version": "1"}},
        {"contract": no_key},
        {"contract": no_reading},
        {"contract": no_version},
        {"contract": unknown_format},
        {"contract": no_kind},
        {"row": "not json"},
        {"row": "[1]"},
        {"row": ""},
        {"source": ""},
        {"publication": "not json"},
        {"publication": "[1]"},
        {"publication": '{"publication_key": "p1"}'},
    ]:
        refused = _try(**kwargs)
        assert list(refused) == ["refused"] and refused["refused"], kwargs
    assert "reading" in _try(contract=no_reading)["refused"]
    assert "record_key" in _try(contract=no_key)["refused"]
    assert "schema_version" in _try(contract=no_version)["refused"]
    assert "invented" in _try(contract=unknown_format)["refused"]
    assert "revision" in _try(publication='{"publication_key": "p1"}')["refused"]
