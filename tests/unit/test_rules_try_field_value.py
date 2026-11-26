"""The field-value family chooses a value per field with a pasted policy."""
import json

from edgar_warehouse.rules.try_page import press

REGISTER = "example.register.v1"
DIRECTORY = "example.directory.v1"
POLICY = json.dumps({"kinds": {"example_company": {
    "defaults": {"sources": [REGISTER, DIRECTORY]},
    "fields": {"address": {"sources": [DIRECTORY, REGISTER]}},
}}})


def _claim(source, record, effective="2026-09-01T00:00:00+00:00", op="value", **fields):
    return {"fields": {name: {"assertion_id": f"{record}-a", "effective_at": effective, "op": op,
                              "record_key": record, "source_code": source, "value": value}
                       for name, value in fields.items()}}


CLAIMS = json.dumps({
    "S1": _claim(REGISTER, "R1", name="Example Works", address="1 Register Way"),
    "S2": _claim(DIRECTORY, "D1", name="EXAMPLE WORKS LTD", address="2 Directory Road"),
})


def _try(rule=POLICY, **changed):
    inputs = {"kind": "example_company", "subjects": '["S1", "S2"]', "claims": CLAIMS, "overrides": "",
              "as_of": "2026-09-22T00:00:00+00:00", "policy_digest": "digest-1"}
    inputs.update(changed)
    return press("Try", "field_value", rule=rule, inputs=inputs)


def test_address_comes_from_the_directory_and_the_other_field_from_the_register():
    fields = _try()["actual"]["fields"]
    assert fields["address"]["value"] == "2 Directory Road"
    assert fields["address"]["winner"]["source_code"] == DIRECTORY
    assert [c["value"] for c in fields["address"]["conflicts"]] == ["1 Register Way"]
    assert fields["name"]["value"] == "Example Works"
    assert fields["name"]["winner"]["source_code"] == REGISTER
    assert [c["value"] for c in fields["name"]["conflicts"]] == ["EXAMPLE WORKS LTD"]


def test_the_pasted_policy_decides_not_a_policy_file(monkeypatch):
    def read(*_args, **_kwargs):
        raise AssertionError("files.policy was called")

    monkeypatch.setattr("edgar_warehouse.rules.files.policy", read)
    register_first = json.dumps({"kinds": {"example_company": {
        "defaults": {"sources": [REGISTER, DIRECTORY]}}}})
    assert _try(register_first)["actual"]["fields"]["address"]["value"] == "1 Register Way"
    assert _try()["actual"]["fields"]["address"]["value"] == "2 Directory Road"


def test_a_claim_older_than_the_limit_leaves_the_next_source_to_answer():
    rule = json.loads(POLICY)
    rule["kinds"]["example_company"]["fields"]["address"]["max_age_days"] = 365
    claims = json.loads(CLAIMS)
    claims["S2"] = _claim(DIRECTORY, "D1", effective="2024-01-01T00:00:00+00:00",
                          name="EXAMPLE WORKS LTD", address="2 Directory Road")
    address = _try(json.dumps(rule), claims=json.dumps(claims))["actual"]["fields"]["address"]
    assert address["value"] == "1 Register Way"
    assert address["conflicts"] == []


def test_only_a_listed_source_may_blank_a_field():
    rule = json.loads(POLICY)
    rule["kinds"]["example_company"]["fields"]["address"]["clear_sources"] = [DIRECTORY]
    claims = json.loads(CLAIMS)
    claims["S2"] = _claim(DIRECTORY, "D1", op="clear", address=None)
    cleared = _try(json.dumps(rule), claims=json.dumps(claims))["actual"]
    assert cleared["fields"]["address"]["cleared"] is True
    assert cleared["reviews"] == []
    claims["S1"] = _claim(REGISTER, "R1", op="clear", address=None)
    del claims["S2"]
    refused_clear = _try(json.dumps(rule), claims=json.dumps(claims))["actual"]
    assert "address" not in refused_clear["fields"]
    assert [item["reason"] for item in refused_clear["reviews"]] == ["unauthorized_clear"]


def test_a_steward_override_wins_and_the_disagreement_is_reviewed():
    override = [{"subject": "S1", "field": "name", "value": "Example Works Ltd",
                 "decision_id": "decision-1", "reason": "checked"}]
    actual = _try(overrides=json.dumps(override))["actual"]
    assert actual["fields"]["name"]["value"] == "Example Works Ltd"
    assert actual["fields"]["name"]["winner"]["source_code"] == "steward"
    assert [item["reason"] for item in actual["reviews"]] == ["override_source_disagreement"]


def test_the_expected_answer_is_compared():
    inputs = {"kind": "example_company", "subjects": '["S1"]', "claims": "{}", "overrides": "",
              "as_of": "2026-09-22T00:00:00+00:00", "policy_digest": "digest-1"}
    nothing = {"fields": {}, "profiles": [], "reviews": []}
    assert press("Try", "field_value", rule=POLICY, inputs=inputs, expected=nothing)["passed"] is True
    other = {"fields": {"name": {}}, "profiles": [], "reviews": []}
    assert press("Try", "field_value", rule=POLICY, inputs=inputs, expected=other)["passed"] is False


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    for rule, changed in [
        ("not json", {}),
        ("[1]", {}),
        (json.dumps({"kinds": {"example_company": {"made_up": 1}}}), {}),
        (json.dumps({"kinds": {"example_company": {"fields": {"address": {}}}}}), {}),
        (json.dumps({"kinds": {"example_company": {}}, "fields": {"example_company": {}}}), {}),
        (POLICY, {"kind": ""}),
        (POLICY, {"subjects": "not json"}),
        (POLICY, {"subjects": '"S1"'}),
        (POLICY, {"subjects": "[1]"}),
        (POLICY, {"subjects": ""}),
        (POLICY, {"claims": "not json"}),
        (POLICY, {"claims": "[]"}),
        (POLICY, {"claims": '{"S1": 5}'}),
        (POLICY, {"overrides": "not json"}),
        (POLICY, {"overrides": '{"subject": "S1"}'}),
        (POLICY, {"as_of": ""}),
        (POLICY, {"as_of": "2026-09-22"}),
        (POLICY, {"as_of": "yesterday"}),
        (POLICY, {"policy_digest": ""}),
    ]:
        refused = _try(rule, **changed)
        assert list(refused) == ["refused"] and refused["refused"], (rule, changed)
