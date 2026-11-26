"""The link-two-masters short words become a complete link rule."""
import json

from edgar_warehouse.rules.try_page import press, show_full

SHORT = {
    "link type": "ISSUED_BY",
    "other master's key": "C1",
    "link starts": "2020-01-01T00:00:00+00:00",
    "link ends": "2022-01-01T00:00:00+00:00",
}
INPUTS = {
    "claims": '{"S1": {"assertion_id": "a1", "source_meta": {}}}',
    "state": '{"bindings": {"S1": "b1", "C1": "b2"}, "canonical": {"b1": "E1", "b2": "E2"}}',
    "entities": ('{"E1": {"kind": "security", "status": "accepted", "profiles": []},'
                 ' "E2": {"kind": "company", "status": "accepted", "profiles": []}}'),
    "as_of": "2026-01-01T00:00:00+00:00",
    "types": '{"ISSUED_BY": {"from": ["security"], "to": ["company"]}}',
}


def _show(**short):
    return show_full("link_masters", json.dumps(short))


def _try(document):
    return press("Try", "link_masters", rule=json.dumps(document), inputs=INPUTS)["actual"]


def test_the_words_show_their_stored_keys_and_the_result_is_the_one_link_of_ticket_25():
    shown = _show(**SHORT)
    assert shown["document"] == {
        "type": "ISSUED_BY", "target_key": "C1",
        "valid_from": "2020-01-01T00:00:00+00:00", "valid_to": "2022-01-01T00:00:00+00:00"}
    assert shown["lines"] == [
        {"word": "link type", "stored": "type"},
        {"word": "other master's key", "stored": "target_key"},
        {"word": "link starts", "stored": "valid_from"},
        {"word": "link ends", "stored": "valid_to"}]
    actual = _try(shown["document"])
    assert actual["reviews"] == []
    assert [(link["source_id"], link["target_id"], link["periods"]) for link in actual["links"]] == [
        ("E1", "E2", [{"valid_from": "2020-01-01T00:00:00+00:00", "valid_to": "2022-01-01T00:00:00+00:00",
                       "valid_from_basis": "stated", "valid_to_basis": "stated"}])]


def test_a_missing_end_is_not_invented_and_a_missing_other_master_stays_a_wait():
    no_end = _show(**{key: value for key, value in SHORT.items() if key != "link ends"})
    assert "valid_to" not in no_end["document"]
    assert _try(no_end["document"])["links"][0]["periods"] == [
        {"valid_from": "2020-01-01T00:00:00+00:00", "valid_from_basis": "stated"}]
    no_master = _show(**{key: value for key, value in SHORT.items() if key != "other master's key"})
    assert "target_key" not in no_master["document"]
    actual = _try(no_master["document"])
    assert actual["links"] == []
    assert [(r["reason"], r["missing"]) for r in actual["reviews"]] == [("unresolved_endpoint", ["target"])]


def test_a_stored_key_and_scope_keep_their_names_in_the_shown_document():
    shown = _show(**{"link type": "ISSUED_BY", "valid_from": "2020-01-01T00:00:00+00:00", "scope": "Example register"})
    assert shown["document"] == {"type": "ISSUED_BY", "valid_from": "2020-01-01T00:00:00+00:00",
                                 "scope": "Example register"}
    assert shown["lines"] == [{"word": "link type", "stored": "type"}]


def test_an_unknown_word_a_word_beside_its_stored_key_and_a_bad_value_are_refused():
    unknown = _show(**{"link type": "ISSUED_BY", "other master": "C1"})
    assert list(unknown) == ["refused"]
    assert "'other master' is not a word" in unknown["refused"]
    assert "Words this file accepts: link type, other master's key, link starts, link ends" in unknown["refused"]
    for word_of_the_other_family in ("attach", "group by"):
        assert list(_show(**{word_of_the_other_family: "x"})) == ["refused"]
    twice = _show(**{"link type": "ISSUED_BY", "type": "ISSUED_BY"})
    assert "names type twice" in twice["refused"]
    assert list(_show(**{"link starts": 2020})) == ["refused"]
    assert show_full("link_masters", "not json") == {"refused": "The short link is not JSON."}
    assert show_full("link_masters", "[]") == {"refused": "The short link is not one JSON object."}

