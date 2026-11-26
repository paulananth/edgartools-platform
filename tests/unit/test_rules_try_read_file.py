"""The read-the-file family reads pasted bytes with a pasted read document."""
import json

from edgar_warehouse.rules.try_page import press

READ_DOCUMENT = json.dumps({"read": {
    "format": "json",
    "limits": {"max_bytes": 4096, "max_records": 10},
    "tables": {"records": {"each": "records", "columns": {
        "id": {"text": {"path": "id"}},
        "name": {"text": {"path": "name"}},
        "quantity": {"integer": {"path": "quantity"}},
    }}},
}})
FILE = '{"records":[{"id":"R1","name":"  Example Works  ","quantity":"12"}]}'


def _try(rule=READ_DOCUMENT, file=FILE, lookups="", expected=None):
    return press("Try", "read_file", rule=rule, inputs={"file": file, "lookups": lookups},
                 expected=expected)


def test_the_invented_row_is_read_trimmed_with_a_whole_quantity():
    tried = _try(expected={"tables": {"records": [{"id": "R1", "name": "Example Works", "quantity": 12}]},
                           "deferred": []})
    assert tried["passed"] is True
    assert tried["actual"]["tables"]["records"] == [{"id": "R1", "name": "Example Works", "quantity": 12}]


def test_a_lookup_list_decides_which_row_is_set_aside():
    rule = json.loads(READ_DOCUMENT)
    rule["read"]["lookup_sets"] = {"scope": {"max_values": 10, "max_bytes": 100, "max_value_bytes": 10}}
    rule["read"]["tables"]["records"]["checks"] = [
        {"check": "in_lookup", "column": "id", "lookup": "scope", "on_fail": "defer", "reason": "outside_scope"}]
    inside = _try(rule=json.dumps(rule), lookups='{"scope": ["R1"]}')
    outside = _try(rule=json.dumps(rule), lookups='{"scope": ["R2"]}')
    assert len(inside["actual"]["tables"]["records"]) == 1
    assert inside["actual"]["deferred"] == []
    assert outside["actual"]["tables"]["records"] == []
    assert [item["reason"] for item in outside["actual"]["deferred"]] == ["outside_scope"]


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    for rule, file, lookups in [
        ("not json", FILE, ""),
        ("[1]", FILE, ""),
        (json.dumps({"read": {"format": "no such format"}}), FILE, ""),
        (READ_DOCUMENT, "not a json file", ""),
        (READ_DOCUMENT, FILE, "not json"),
        (READ_DOCUMENT, FILE, '{"scope": "R1"}'),
    ]:
        refused = _try(rule=rule, file=file, lookups=lookups)
        assert list(refused) == ["refused"] and refused["refused"], (rule, file, lookups)


def test_no_capture_folder_is_opened(monkeypatch):
    def opened(*_args, **_kwargs):
        raise AssertionError("a folder was opened")

    monkeypatch.setattr("pathlib.Path.open", opened)
    monkeypatch.setattr("pathlib.Path.iterdir", opened)
    monkeypatch.setattr("pathlib.Path.read_bytes", opened)
    assert _try()["actual"]["tables"]["records"]
