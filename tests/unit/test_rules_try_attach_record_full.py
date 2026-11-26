"""The attach-a-source-record short words become a complete policy."""
import json

import pytest

from edgar_warehouse.rules.bench_families import attach_record_full
from edgar_warehouse.rules.try_page import press

CONTRACT = {
    "normalizer": "normalize_identifier@ticker-v1",
    "consolidates": True,
    "sources": ["example.listings"],
    "claim": {"forward": 1, "reverse": None},
}


def _rule(match="identifier_match@1", allows="identifier_cardinality@1", **changes):
    return {
        "rule_id": "example-listing-ticker", "version": "1", "family": "binding",
        "applies_to_verdict": "security",
        "when": [{"primitive": match, "args": {"namespace": "ticker"}},
                 {"primitive": allows, "args": {"namespace": "ticker"}}],
        **changes,
    }


def _policy(rule, verdict="bind"):
    return {
        "automatic_rules": [{"kind": "security", "family": "binding", "rule_id": "example-listing-ticker",
                             "rule_version": "1", "verdict": verdict}],
        "kinds": {"security": {"rules": [rule], "identifiers": {"ticker": CONTRACT}}},
    }


STORED = _policy(_rule(emits=["bind"], on_no_match="mint", on_several="review"))
SHORT = _policy(
    _rule("same identifier", "how many that identifier allows",
          emits=["attach"], on_no_match="create a master", on_several="send to review"),
    verdict="attach")


def _explain(policy):
    return attach_record_full.explain(json.dumps(policy))


def _record(subject="R1", ticker="EXMPL"):
    return {"subject": subject, "assertion_id": f"A-{subject}", "source_code": "example.listings",
            "kind": "security", "revision": 1, "identifiers": {"ticker": [ticker]}}


def _master(entity_id):
    return {"entity_id": entity_id, "kind": "security", "holds": {"ticker": ["EXMPL"]}}


def _try(document, *masters):
    return press("Try", "attach_record", rule=json.dumps(document), inputs={
        "assertions": json.dumps([_record()]), "identities": json.dumps(list(masters)), "bound": "[]"})


def test_the_shown_policy_is_the_stored_policy_with_a_line_for_each_word_used():
    shown = _explain(SHORT)
    assert shown["document"] == STORED
    assert shown["lines"] == [
        {"word": "attach", "stored": "bind"},
        {"word": "create a master", "stored": "mint"},
        {"word": "send to review", "stored": "review"},
        {"word": "same identifier", "stored": "identifier_match@1"},
        {"word": "how many that identifier allows", "stored": "identifier_cardinality@1"},
    ]


def test_the_one_master_and_two_master_cases_in_these_words_match_the_try():
    document = _explain(SHORT)["document"]
    one = _try(document, _master("M1"))
    two = _try(document, _master("M1"), _master("M2"))
    assert [(item["outcome"], item["stored"]) for item in one["actual"]["outcomes"]] == [("attach", "bind")]
    assert [(item["outcome"], item["stored"]) for item in two["actual"]["outcomes"]] == [
        ("send to review", "review")]
    none = _try(document)
    assert [(item["outcome"], item["stored"]) for item in none["actual"]["outcomes"]] == [
        ("create a master", "mint")]


def test_each_word_is_listed_beside_its_stored_key():
    for pair in ({"word": "same identifier", "stored": "identifier_match@1"},
                 {"word": "how many that identifier allows", "stored": "identifier_cardinality@1"},
                 {"word": "attach", "stored": "bind"},
                 {"word": "create a master", "stored": "mint"},
                 {"word": "send to review", "stored": "review"}):
        assert pair in attach_record_full.words


@pytest.mark.parametrize("policy, typed", [
    (_policy(_rule(emits=["bind"], on_no_match="create a master", on_several="send to review"),
             verdict="attach"), "attach"),
    (_policy(_rule(emits=["attach"], on_no_match="mint", on_several="send to review"), verdict="attach"),
     "create a master"),
    (_policy(_rule("identifier_match@1", "how many that identifier allows", emits=["attach"],
                   on_no_match="create a master"), verdict="attach"), "same identifier"),
    (_policy(_rule("same identifier", "identifier_cardinality@1", emits=["attach"],
                   on_no_match="create a master"), verdict="attach"), "how many that identifier allows"),
    (_policy(_rule("same identifier", "how many that identifier allows", emits=["attach"],
                   on_no_match="create a master"), verdict="bind"), "attach"),
])
def test_a_bare_stored_key_is_refused_naming_the_word_to_type(policy, typed):
    refused = _explain(policy)
    assert list(refused) == ["refused"]
    assert f"Type '{typed}' instead." in refused["refused"]
    assert "Words this file accepts:" in refused["refused"]


def test_a_stored_key_that_names_its_action_is_accepted_as_it_is():
    rule = _rule("same identifier", "how many that identifier allows", emits=["attach"],
                 on_no_match="wait", on_several="review", on_conflict="first")
    shown = _explain(_policy(rule, verdict="attach"))
    assert shown["document"]["kinds"]["security"]["rules"][0]["on_several"] == "review"
    assert shown["document"]["kinds"]["security"]["rules"][0]["on_conflict"] == "first"
    assert shown["document"]["kinds"]["security"]["rules"][0]["on_no_match"] == "wait"


@pytest.mark.parametrize("combining", [
    "merge", "combine the masters", "combine two masters", "merge the masters", "consolidate", "same subject"])
def test_a_word_for_combining_two_existing_masters_is_refused(combining):
    rule = _rule("same identifier", "how many that identifier allows", emits=["attach"],
                 on_no_match="create a master", on_several=combining)
    refused = _explain(_policy(rule, verdict="attach"))
    assert list(refused) == ["refused"]
    assert "rules test" in refused["refused"]
    assert f"'{combining}'" in refused["refused"]


def test_a_combining_word_is_refused_wherever_it_stands():
    for policy in (
        _policy(_rule("same identifier", "how many that identifier allows", emits=["merge"],
                      on_no_match="create a master"), verdict="attach"),
        _policy(_rule("same identifier", "how many that identifier allows", emits=["attach"],
                      on_no_match="create a master", on_conflict="merge"), verdict="attach"),
        _policy(_rule("same identifier", "how many that identifier allows", emits=["attach"],
                      on_no_match="create a master", **{"combine the masters": True}), verdict="attach"),
        _policy(_rule("same identifier", "how many that identifier allows", emits=["attach"],
                      on_no_match="create a master"), verdict="merge"),
    ):
        refused = _explain(policy)
        assert list(refused) == ["refused"] and "rules test" in refused["refused"], policy


@pytest.mark.parametrize("word", [
    "list the values", "one flat list", "first row", "last row", "exactly one row",
    "how many rows", "distinct values", "most frequent", "how many at this path"])
def test_a_word_of_another_family_is_refused_naming_attach_a_source_record(word):
    rule = _rule("same identifier", "how many that identifier allows", emits=["attach"],
                 on_no_match="create a master", on_several=word)
    refused = _explain(_policy(rule, verdict="attach"))
    assert list(refused) == ["refused"]
    assert f"'{word}' is a word of" in refused["refused"]
    assert "not of Attach a source record" in refused["refused"]


def test_a_word_of_another_family_is_refused_as_a_key_too():
    rule = _rule("same identifier", "how many that identifier allows", emits=["attach"],
                 on_no_match="create a master", **{"list the values": "x"})
    refused = _explain(_policy(rule, verdict="attach"))
    assert list(refused) == ["refused"] and "'list the values' is a word of" in refused["refused"]


def test_an_unknown_word_where_an_outcome_goes_is_refused_with_the_accepted_words():
    rule = _rule("same identifier", "how many that identifier allows", emits=["attach"],
                 on_no_match="make something up")
    refused = _explain(_policy(rule, verdict="attach"))
    assert list(refused) == ["refused"]
    assert "'make something up'" in refused["refused"]
    assert "create a master" in refused["refused"]


@pytest.mark.parametrize("rule", ["not json", "[1]", json.dumps({"automatic_rules": []}),
                                  json.dumps({"kinds": {}}),
                                  json.dumps({"automatic_rules": [], "kinds": {"security": {"rules": "x"}}})])
def test_a_bad_short_rule_is_a_refusal(rule):
    refused = attach_record_full.explain(rule)
    assert list(refused) == ["refused"] and refused["refused"]
