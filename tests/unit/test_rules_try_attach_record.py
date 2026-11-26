"""The attach-a-source-record family plans one pasted batch and names each record's outcome."""
import json

import pytest

from edgar_warehouse.rules.try_page import press

RULE = {
    "rule_id": "example-listing-ticker",
    "version": "1",
    "family": "binding",
    "applies_to_verdict": "security",
    "emits": ["bind"],
    "on_no_match": "mint",
    "when": [
        {"primitive": "identifier_match@1", "args": {"namespace": "ticker"}},
        {"primitive": "identifier_cardinality@1", "args": {"namespace": "ticker"}},
    ],
}
CONTRACT = {
    "normalizer": "normalize_identifier@ticker-v1",
    "consolidates": True,
    "sources": ["example.listings"],
    "claim": {"forward": 1, "reverse": None},
}


def _policy(**changes):
    rule = {**RULE, **changes}
    return json.dumps({
        "automatic_rules": [{"kind": "security", "family": "binding", "rule_id": rule["rule_id"],
                             "rule_version": rule["version"], "verdict": "bind"}],
        "kinds": {"security": {"rules": [rule], "identifiers": {"ticker": CONTRACT}}},
    })


def _record(subject="R1", ticker="EXMPL"):
    return {"subject": subject, "assertion_id": f"A-{subject}", "source_code": "example.listings",
            "kind": "security", "revision": 1, "identifiers": {"ticker": [ticker]}}


def _master(entity_id, *tickers):
    return {"entity_id": entity_id, "kind": "security", "holds": {"ticker": list(tickers)}}


def _inputs(records=None, masters=None, bound=None):
    return {"assertions": json.dumps(records if records is not None else [_record()]),
            "identities": json.dumps(masters if masters is not None else []),
            "bound": json.dumps(bound if bound is not None else [])}


def _try(rule=None, expected=None, **inputs):
    return press("Try", "attach_record", rule=rule if rule is not None else _policy(),
                 inputs=_inputs(**inputs), expected=expected)


def test_one_pasted_master_returns_attach():
    tried = _try(masters=[_master("M1", "EXMPL")], expected={
        "looked_up": {"ticker": ["EXMPL"]},
        "outcomes": [{"subject": "R1", "outcome": "attach", "stored": "bind", "master": "M1"}],
        "no_outcome": []})
    assert tried["passed"] is True


def test_two_pasted_masters_return_send_to_review():
    tried = _try(masters=[_master("M1", "EXMPL"), _master("M2", "EXMPL")], expected={
        "looked_up": {"ticker": ["EXMPL"]},
        "outcomes": [{"subject": "R1", "outcome": "send to review", "stored": "review",
                      "reason": "ambiguous_identifier"}],
        "no_outcome": []})
    assert tried["passed"] is True


def test_no_pasted_master_creates_a_master():
    tried = _try(expected={
        "looked_up": {"ticker": ["EXMPL"]},
        "outcomes": [{"subject": "R1", "outcome": "create a master", "stored": "mint", "master": "new-master-1"}],
        "no_outcome": []})
    assert tried["passed"] is True


def test_an_empty_masters_and_bound_paste_means_none():
    inputs = {"assertions": json.dumps([_record()]), "identities": "", "bound": " "}
    tried = press("Try", "attach_record", rule=_policy(), inputs=inputs)
    assert [item["outcome"] for item in tried["actual"]["outcomes"]] == ["create a master"]


def test_the_value_is_matched_as_the_engine_normalizes_it():
    tried = _try(records=[_record(ticker="exmpl")], masters=[_master("M1", "EXMPL")])
    assert tried["actual"]["outcomes"] == [
        {"subject": "R1", "outcome": "attach", "stored": "bind", "master": "M1"}]


def test_a_master_of_another_entity_type_sends_the_record_to_review():
    other = {"entity_id": "M1", "kind": "company", "holds": {"ticker": ["EXMPL"]}}
    tried = _try(masters=[other])
    assert tried["actual"]["outcomes"] == [
        {"subject": "R1", "outcome": "send to review", "stored": "review",
         "reason": "incompatible_identifier_kind"}]


def test_a_record_with_no_outcome_says_why():
    waiting = _try(rule=_policy(on_no_match="wait"), records=[_record("R1"), _record("R2", "OTHER"), _record("R3")],
                   masters=[_master("M1", "OTHER")], bound=["R3"])
    assert waiting["actual"]["outcomes"] == [
        {"subject": "R2", "outcome": "attach", "stored": "bind", "master": "M1"}]
    assert waiting["actual"]["no_outcome"] == [
        {"subject": "R1", "why": "waits for a master"}, {"subject": "R3", "why": "already attached"}]
    other_kind = _record("R4")
    other_kind["kind"] = "company"
    none = _try(records=[other_kind])
    assert none["actual"]["no_outcome"] == [{"subject": "R4", "why": "no rule applies"}]


def test_a_rule_that_merges_two_masters_is_refused():
    masters = [_master("M1", "EXMPL"), _master("M2", "EXMPL")]
    refused = _try(rule=_policy(on_several="merge"), masters=masters)
    assert list(refused) == ["refused"]
    assert "rules test" in refused["refused"]


def test_two_values_reaching_two_masters_go_to_review():
    record = _record()
    record["identifiers"]["ticker"] = ["EXMPL", "OTHER"]
    masters = [_master("M1", "EXMPL"), _master("M2", "OTHER")]
    review = _try(records=[record], masters=masters)
    assert review["actual"]["outcomes"] == [
        {"subject": "R1", "outcome": "send to review", "stored": "review", "reason": "conflicting_identifiers"}]


@pytest.mark.parametrize("rule, inputs", [
    ("not json", _inputs()),
    ("[1]", _inputs()),
    (json.dumps({"kinds": {}}), _inputs()),
    (json.dumps({"automatic_rules": []}), _inputs()),
    (_policy(on_no_match="no such outcome"), _inputs()),
    (_policy(), {**_inputs(), "assertions": "not json"}),
    (_policy(), {**_inputs(), "assertions": '{"subject": "R1"}'}),
    (_policy(), {**_inputs(), "assertions": '[{"kind": "security"}]'}),
    (_policy(), {**_inputs(), "assertions": json.dumps([{**_record(), "revision": "x"}])}),
    (_policy(), {**_inputs(), "identities": "not json"}),
    (_policy(), {**_inputs(), "identities": '[{"entity_id": "M1"}]'}),
    (_policy(), {**_inputs(), "identities": '[{"entity_id": "M1", "kind": "security", "holds": {"ticker": "EXMPL"}}]'}),
    (_policy(), {**_inputs(), "bound": "not json"}),
    (_policy(), {**_inputs(), "bound": '["R1", 2]'}),
])
def test_a_bad_paste_is_a_refusal_not_a_traceback(rule, inputs):
    refused = press("Try", "attach_record", rule=rule, inputs=inputs)
    assert list(refused) == ["refused"] and refused["refused"]


def test_propose_is_not_called_and_no_database_is_opened(monkeypatch):
    def opened(*_args, **_kwargs):
        raise AssertionError("propose or a database was reached")

    monkeypatch.setattr("edgar_warehouse.mdm.binding.propose", opened)
    monkeypatch.setattr("edgar_warehouse.database_connections.connect", opened)
    assert _try(masters=[_master("M1", "EXMPL")])["actual"]["outcomes"][0]["outcome"] == "attach"
