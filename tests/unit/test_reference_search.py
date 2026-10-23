"""Search computation without a storage server; invented words only."""
import json

import edgar_control
import pytest


@pytest.mark.parametrize("words,label,expected", [
    ("AI", "chair", False), ("AI", "AI reference", True),
    ("the", "The reference", True), ("-second", "First reference", True),
    ("-second", "Second reference", False), ("-absent OR first", "Second", True),
    ("first -second", "first second", False), ('"first second"', "first ignored second", False),
    ('"first second"', "First second", True), ("well-known", "well known", False),
    ("well-known", "well-known", True), ('"well known"', "well-known", True),
    ("alpha", "alpha.beta", False), ("alpha", "alpha-beta@example.test", False), ("alpha.beta", "alpha.beta", True),
    ("alpha,beta", "alpha beta", True), ("%", "anything", False),
    ("OR", "or", True), ("first OR", "first or", True),
    ("OR first", "or first", True), ("first & second", "first ignored second", True),
    ("first:second", "first ignored second", True), ("- second", "first", True),
])
def test_query_membership(words, label, expected):
    assert edgar_control.reference_query_matches(words, label) is expected


def test_word_index_tokens_keep_short_stop_and_long_words():
    tokens = edgar_control.encode_reference_search("a the " + "z" * 200).split()
    assert len(tokens) == 3 and all(len(token) == 64 for token in tokens)
    assert edgar_control.compile_reference_query("a the").count("+") == 2
    assert edgar_control.compile_reference_query("-second") == ""
    assert edgar_control.compile_reference_query("first OR -second") == ""


def test_negative_only_hits_have_zero_density_and_stable_code_order():
    rows = [{"code": code, "label": "First", "label_path": "First", "search_text": "First",
             "rank": 0, "matched_by": "label"} for code in ("b", "a")]
    found = json.loads(edgar_control.prepare_reference_search(json.dumps({
        "rows": rows, "words": "-second", "position_weight": .1, "synonym_weight": .9, "limit": 5})))
    assert [(row["code"], row["rank"]) for row in found] == [("a", 0), ("b", 0)]
