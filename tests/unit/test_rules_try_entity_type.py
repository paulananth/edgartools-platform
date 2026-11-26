"""The entity-type family decides one invented record with a pasted classification rule."""
import json

from edgar_warehouse.rules.try_page import press

RULE = {
    "rule_id": "example-entity-type",
    "version": "example-entity-type-v1",
    "family": "classification",
    "emits": ["company", "entity_undetermined", "deferred"],
    "steps": [
        {"step": "1", "verdict": "deferred",
         "when": [{"primitive": "fields_all_empty@1", "args": {"fields": ["ticker"]}}]},
        {"step": "2", "verdict": "company",
         "when": [{"primitive": "field_in_set@1", "args": {"field": "category", "values": ["OPERATING"]}}]},
        {"step": "3", "verdict": "entity_undetermined",
         "when": [{"primitive": "field_in_set@1", "args": {"field": "category", "values": ["OTHER"]}}]},
        {"step": "4", "verdict": "deferred", "otherwise": True},
    ],
}


def _try(rule=RULE, record=None, doc="", expected=None):
    text = rule if isinstance(rule, str) else json.dumps(rule)
    pasted = record if isinstance(record, str) else json.dumps(record if record is not None else {})
    return press("Try", "entity_type", rule=text, inputs={"record": pasted, "doc": doc}, expected=expected)


def test_an_empty_ticker_is_held_back_and_shows_the_stored_verdict():
    tried = _try(record={"ticker": "", "category": "OPERATING"}, expected={"held back": "deferred"})
    assert tried["passed"] is True
    assert tried["actual"] == {"held back": "deferred"}


def test_a_record_with_a_ticker_gets_the_entity_type_the_step_decides():
    tried = _try(record={"ticker": "EXMP", "category": "OPERATING"}, expected={"entity type": "company"})
    assert tried["passed"] is True


def test_a_record_no_step_matches_falls_to_otherwise():
    assert _try(record={"ticker": "EXMP", "category": "NEITHER"})["actual"] == {"held back": "deferred"}


def test_a_step_that_decides_no_entity_type_shows_its_own_stored_verdict():
    assert _try(record={"ticker": "EXMP", "category": "OTHER"})["actual"] == {"held back": "entity_undetermined"}


def test_a_list_the_rule_names_comes_from_the_doc():
    rule = json.loads(json.dumps(RULE))
    rule["steps"][0]["when"][0]["args"]["fields"] = "ticker_fields"
    record = {"ticker": ""}
    refused = _try(rule=rule, record=record)
    held = _try(rule=rule, record=record, doc=json.dumps({"lists": {"ticker_fields": ["ticker"]}}))
    assert list(refused) == ["refused"] and "ticker_fields" in refused["refused"]
    assert held["actual"] == {"held back": "deferred"}


def test_a_rule_with_no_otherwise_returns_the_engines_refusal():
    rule = {**RULE, "steps": RULE["steps"][:3]}
    refused = _try(rule=rule, record={"ticker": "EXMP", "category": "NEITHER"})
    assert list(refused) == ["refused"]
    assert "otherwise" in refused["refused"]


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    steps = RULE["steps"]
    for rule, record, doc in [
        ("not json", {}, ""),
        ("[1]", {}, ""),
        ({**RULE, "steps": "none"}, {}, ""),
        ({**RULE, "steps": [1]}, {}, ""),
        ({**RULE, "steps": [{**steps[0], "when": [5]}, steps[3]]}, {}, ""),
        ({**RULE, "steps": [{**steps[0], "when": [{"primitive": "no_such_test@1"}]}, steps[3]]}, {}, ""),
        ({**RULE, "family": "binding"}, {}, ""),
        ({**RULE, "emits": ["company"]}, {}, ""),
        (RULE, "not json", ""),
        (RULE, "[1]", ""),
        (RULE, "", ""),
        (RULE, {}, "not json"),
        (RULE, {}, "[1]"),
    ]:
        refused = _try(rule=rule, record=record, doc=doc)
        assert list(refused) == ["refused"] and refused["refused"], (rule, record, doc)


def test_no_kind_workbook_is_opened(monkeypatch):
    _try(record={"ticker": ""})

    def opened(*_args, **_kwargs):
        raise AssertionError("a file or folder was opened")

    monkeypatch.setattr("pathlib.Path.open", opened)
    monkeypatch.setattr("pathlib.Path.iterdir", opened)
    monkeypatch.setattr("pathlib.Path.read_bytes", opened)
    monkeypatch.setattr("pathlib.Path.read_text", opened)
    assert _try(record={"ticker": ""})["actual"] == {"held back": "deferred"}
