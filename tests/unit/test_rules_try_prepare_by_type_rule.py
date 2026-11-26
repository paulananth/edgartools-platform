"""The rule-decided family prepares one invented row; the pasted entity type rule decides its entity type."""
import copy
import json

from edgar_warehouse.rules.try_page import press
from tests.support.reading import reading

NAMED = {"kind": "company", "rule_id": "example-rule", "version": "1"}
CONTRACT = {
    "schema_version": "1",
    "adapter": {
        "version": "example-v1",
        "classification": NAMED,
        "record_key": ["id"],
        "identifiers": {"example_id": "ident"},
        "reading": reading({"name": "name"}),
    },
}
RULE = {
    "rule_id": "example-rule",
    "version": "1",
    "family": "classification",
    "emits": ["company", "person", "deferred"],
    "steps": [
        {"step": "1", "verdict": "company",
         "when": [{"primitive": "field_in_set@1", "args": {"field": "category", "values": ["operating"]}}]},
        {"step": "2", "verdict": "person",
         "when": [{"primitive": "field_in_set@1", "args": {"field": "category", "values": ["individual"]}}]},
        {"step": "3", "verdict": "deferred", "otherwise": True},
    ],
}
SWITCHED_ON = [{"kind": "company", "family": "classification", "rule_id": "example-rule",
                "rule_version": "1", "verdict": verdict} for verdict in ("company", "person")]
POLICY = {"automatic_rules": SWITCHED_ON, "kinds": {"company": {"rules": [RULE]}}}
ROW = '{"id": "R1", "ident": "ID-100", "name": "Example Works", "category": "operating"}'
PUBLICATION = '{"publication_key": "p1", "revision": 1, "artifact_sha256": "%s", "member": "m"}' % ("0" * 64)


def _text(value):
    return value if isinstance(value, str) else json.dumps(value)


def _try(contract=CONTRACT, row=ROW, source="example.records.v1", publication=PUBLICATION, policy=POLICY,
         expected=None):
    return press("Try", "prepare_by_type_rule", rule=_text(contract), expected=expected,
                 inputs={"row": row, "source": source, "publication": publication, "policy": _text(policy)})


def _changed(base, **changes):
    changed = copy.deepcopy(base)
    changed.update(changes)
    return changed


def test_the_row_receives_the_entity_type_the_rule_decides():
    tried = _try()
    assert tried["actual"]["kind"] == "company"
    assert tried["actual"]["record_key"] == "R1"
    assert tried["actual"]["identifiers"] == {"example_id": "ID-100"}
    assert tried["actual"]["provenance"]["classification"] == {
        "rule_id": "example-rule", "version": "1", "step": "1"}
    assert _try(expected=tried["actual"])["passed"] is True
    other = _try(row='{"id": "R2", "ident": "ID-200", "name": "Example Person", "category": "individual"}')
    assert other["actual"]["kind"] == "person"
    assert other["actual"]["provenance"]["classification"]["step"] == "2"


def test_the_entity_type_is_the_rule_and_not_the_contract():
    swapped = _changed(RULE, steps=[
        {"step": "1", "verdict": "person",
         "when": [{"primitive": "field_in_set@1", "args": {"field": "category", "values": ["operating"]}}]},
        {"step": "2", "verdict": "deferred", "otherwise": True}])
    tried = _try(policy={**POLICY, "kinds": {"company": {"rules": [swapped]}}})
    assert tried["actual"]["kind"] == "person"


def test_a_verdict_the_policy_has_not_switched_on_is_set_aside_with_its_rule():
    refused = _try(policy={**POLICY, "automatic_rules": []})
    assert refused == {"refused": "The record is set aside: classification_not_activated "
                                  "(rule example-rule, version 1, step 1, verdict company)"}


def test_a_verdict_that_decides_no_entity_type_is_set_aside_with_its_step():
    refused = _try(row='{"id": "R3", "ident": "ID-300", "name": "Example", "category": "other"}')
    assert refused == {"refused": "The record is set aside: classification_deferred "
                                  "(rule example-rule, version 1, step 3, verdict deferred)"}


def test_a_row_missing_the_key_is_refused_with_the_engines_reason():
    refused = _try(row='{"ident": "ID-100", "name": "Example Works", "category": "operating"}')
    assert refused == {"refused": "The record is set aside: missing_record_identity"}


def test_a_rule_the_policy_does_not_hold_or_holds_for_another_source_is_refused():
    absent = _try(policy={**POLICY, "kinds": {"company": {"rules": []}}})
    assert "absent classification rule: example-rule" in absent["refused"]
    other_version = _try(contract=_changed(CONTRACT, adapter={**CONTRACT["adapter"],
                                                              "classification": {**NAMED, "version": "2"}}))
    assert "version 2" in other_version["refused"]
    written_for = _changed(RULE, source="example.other.v1")
    elsewhere = _try(policy={**POLICY, "kinds": {"company": {"rules": [written_for]}}})
    assert "written for example.other.v1, not example.records.v1" in elsewhere["refused"]


def test_a_contract_with_no_classification_is_refused_and_names_the_fixed_type_page():
    fixed = {**CONTRACT, "adapter": {k: v for k, v in CONTRACT["adapter"].items() if k != "classification"}}
    fixed["adapter"]["kind"] = "company"
    refused = _try(contract=fixed)
    assert list(refused) == ["refused"]
    assert "no classification" in refused["refused"] and "Prepare the MDM record" in refused["refused"]
    assert "no classification" in _try(contract=_changed(CONTRACT, classification=NAMED,
                                                         adapter={k: v for k, v in CONTRACT["adapter"].items()
                                                                  if k != "classification"}))["refused"]


def test_a_contract_stating_a_kind_and_a_classification_is_refused():
    for extra in ({"kind": "person"}, {"kind_field": "category"}):
        both = {**CONTRACT, "adapter": {**CONTRACT["adapter"], **extra}}
        assert "not both" in _try(contract=both)["refused"]


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    no_key = {**CONTRACT, "adapter": {k: v for k, v in CONTRACT["adapter"].items() if k != "record_key"}}
    no_reading = {**CONTRACT, "adapter": {k: v for k, v in CONTRACT["adapter"].items() if k != "reading"}}
    no_version = {k: v for k, v in CONTRACT.items() if k != "schema_version"}
    no_rule_id = {**CONTRACT, "adapter": {**CONTRACT["adapter"], "classification": {"kind": "company"}}}
    shapeless = {**CONTRACT, "adapter": {**CONTRACT["adapter"], "classification": "example-rule"}}
    for kwargs in [
        {"contract": "not json"},
        {"contract": "[1]"},
        {"contract": {"schema_version": "1"}},
        {"contract": no_key},
        {"contract": no_reading},
        {"contract": no_version},
        {"contract": no_rule_id},
        {"contract": shapeless},
        {"row": "not json"},
        {"row": ""},
        {"source": ""},
        {"publication": "not json"},
        {"publication": '{"publication_key": "p1"}'},
        {"policy": ""},
        {"policy": "not json"},
        {"policy": "[1]"},
        {"policy": "{}"},
    ]:
        refused = _try(**kwargs)
        assert list(refused) == ["refused"] and refused["refused"], kwargs
    assert "rule_id" in _try(contract=no_rule_id)["refused"]
    assert "reading" in _try(contract=no_reading)["refused"]
    assert "kinds block" in _try(policy="{}")["refused"]


def test_no_rules_file_is_opened_to_prepare_the_row(monkeypatch):
    def opened(*_args, **_kwargs):
        raise AssertionError("a file was opened")

    for name in ("open", "read_bytes", "read_text", "iterdir"):
        monkeypatch.setattr(f"pathlib.Path.{name}", opened)
    assert _try()["actual"]["kind"] == "company"
