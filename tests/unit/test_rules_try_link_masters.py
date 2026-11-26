"""The link-two-masters family projects one pasted link with `mdm.relationships.project`."""
import json
from unittest import mock

from edgar_warehouse.mdm import relationships
from edgar_warehouse.rules.try_page import press

RULE = json.dumps({
    "type": "ISSUED_BY",
    "target_key": "C1",
    "valid_from": "2020-01-01T00:00:00+00:00",
    "valid_to": "2022-01-01T00:00:00+00:00",
})
CLAIMS = '{"S1": {"assertion_id": "a1", "source_meta": {}}}'
STATE = '{"bindings": {"S1": "b1", "C1": "b2"}, "canonical": {"b1": "E1", "b2": "E2"}}'
ENTITIES = ('{"E1": {"kind": "security", "status": "accepted", "profiles": []},'
            ' "E2": {"kind": "company", "status": "accepted", "profiles": []}}')
TYPES = '{"ISSUED_BY": {"from": ["security"], "to": ["company"]}}'
AS_OF = "2026-01-01T00:00:00+00:00"


def _try(rule=RULE, **changes):
    inputs = {"claims": CLAIMS, "state": STATE, "entities": ENTITIES, "as_of": AS_OF, "types": TYPES, **changes}
    return press("Try", "link_masters", rule=rule, inputs=inputs)


def _rule(**changes):
    rule = json.loads(RULE)
    rule.update(changes)
    return json.dumps({key: value for key, value in rule.items() if value is not None})


def test_resolved_ends_emit_one_link_with_its_stated_period():
    link = {
        "type": "ISSUED_BY", "source_id": "E1", "target_id": "E2", "scope": "", "derived": False,
        "relationship_id": mock.ANY, "last_seen": None,
        "periods": [{"valid_from": "2020-01-01T00:00:00+00:00", "valid_to": "2022-01-01T00:00:00+00:00",
                     "valid_from_basis": "stated", "valid_to_basis": "stated"}],
        "evidence": [{"assertion_id": "a1", "source_subject": "S1", "target_subject": "C1"}],
    }
    actual = _try()["actual"]
    assert actual["reviews"] == []
    assert actual["links"] == [link]


def test_types_of_is_not_called():
    with mock.patch.object(relationships, "types_of", side_effect=AssertionError("types_of called")):
        assert "links" in _try()["actual"]


def test_a_claim_with_no_start_time_waits_and_emits_no_link():
    actual = _try(rule=_rule(valid_from=None, valid_to=None))["actual"]
    assert actual["links"] == []
    assert actual["reviews"] == [{
        "reason": "unknown_relationship_start", "assertion_id": "a1", "subject": "S1",
        "relationship": {"type": "ISSUED_BY", "target_subject": "C1"},
    }]


def test_the_stating_record_effective_time_is_the_observed_start():
    claims = '{"S1": {"assertion_id": "a1", "source_meta": {"effective_at": "2024-01-01T00:00:00+00:00"}}}'
    actual = _try(rule=_rule(valid_from=None, valid_to=None), claims=claims)["actual"]
    assert actual["links"][0]["periods"] == [
        {"valid_from": "2024-01-01T00:00:00+00:00", "valid_from_basis": "observed"}]


def test_a_missing_end_master_waits_and_is_not_invented():
    unnamed = _try(rule=_rule(target_key=None))["actual"]
    unbound = _try(rule=_rule(target_key="C9"))["actual"]
    for actual in (unnamed, unbound):
        assert actual["links"] == []
        assert [(r["reason"], r["missing"]) for r in actual["reviews"]] == [("unresolved_endpoint", ["target"])]


def test_a_link_with_no_end_time_stays_open():
    actual = _try(rule=_rule(valid_to=None))["actual"]
    assert actual["links"][0]["periods"] == [
        {"valid_from": "2020-01-01T00:00:00+00:00", "valid_from_basis": "stated"}]


def test_a_link_does_not_create_a_master():
    entities = ('{"E1": {"kind": "security", "status": "accepted", "profiles": []},'
                ' "E2": {"kind": "company", "status": "candidate", "profiles": []}}')
    actual = _try(entities=entities)["actual"]
    assert actual["links"] == []
    assert [r["reason"] for r in actual["reviews"]] == ["unresolved_endpoint_identity"]
    assert set(actual) == {"links", "reviews"}


def test_an_unlisted_type_is_set_aside_for_review():
    actual = _try(types="{}")["actual"]
    assert actual["links"] == []
    assert [r["reason"] for r in actual["reviews"]] == ["unsupported_relationship"]


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    bad_rule_text = _try(rule="not json")
    assert bad_rule_text == {"refused": "The link is not JSON."}
    cases = [
        _try(rule="[]"),
        _try(rule=_rule(color="red")),
        _try(rule=_rule(target_key=5)),
        _try(claims="not json"),
        _try(claims='{"S1": {"relationships": []}}'),
        _try(claims="[]"),
        _try(state="not json"),
        _try(state='{"bindings": {"S1": "b1"}}'),
        _try(state='{"bindings": {"S1": 1}, "canonical": {}}'),
        _try(entities="not json"),
        _try(entities='{"E1": 1}'),
        _try(types="not json"),
        _try(types="[]"),
        _try(as_of=""),
        _try(as_of="2026-01-01T00:00:00"),
        _try(types='{"ISSUED_BY": 5}'),
        _try(state='{"bindings": {"S1": "b1", "C1": "b2"}, "canonical": {"b1": "E1"}}'),
        _try(rule=_rule(valid_from="soon")),
    ]
    for refused in cases:
        assert list(refused) == ["refused"] and refused["refused"]
    assert "color" in cases[1]["refused"]
