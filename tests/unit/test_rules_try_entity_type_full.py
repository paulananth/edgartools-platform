"""The entity-type short words become a complete classification rule."""
import json

from edgar_warehouse.rules.try_page import families, load_full, press, show_full

STORED = {
    "rule_id": "example-entity-type",
    "version": "example-entity-type-v1",
    "family": "classification",
    "emits": ["company", "deferred"],
    "steps": [
        {"step": "1", "verdict": "deferred",
         "when": [{"primitive": "fields_all_empty@1", "args": {"fields": ["ticker"]}}]},
        {"step": "2", "verdict": "company",
         "when": [{"primitive": "field_in_set@1", "args": {"field": "category", "values": ["OPERATING"]}}]},
        {"step": "3", "verdict": "deferred", "otherwise": True},
    ],
}


def _short(**changes):
    short = json.loads(json.dumps(STORED))
    short["emits"] = ["company", "held back"]
    short["steps"][0]["verdict"] = "held back"
    short["steps"][0]["when"][0]["primitive"] = "these fields are empty"
    short["steps"][1]["when"][0]["primitive"] = "field is one of"
    short["steps"][2]["verdict"] = "held back"
    short.update(changes)
    return short


def _show(short):
    return show_full("entity_type", json.dumps(short))


def _try(document, record):
    return press("Try", "entity_type", rule=json.dumps(document),
                 inputs={"record": json.dumps(record), "doc": ""})


def test_the_empty_ticker_written_in_words_is_held_back_like_the_stored_rule():
    shown = _show(_short())
    assert shown["document"] == STORED
    assert shown["lines"] == [{"word": "held back", "stored": "deferred"},
                              {"word": "these fields are empty", "stored": "fields_all_empty@1"},
                              {"word": "field is one of", "stored": "field_in_set@1"},
                              {"word": "otherwise", "stored": "otherwise"}]
    assert _try(shown["document"], {"ticker": "", "category": "OPERATING"})["actual"] == {"held back": "deferred"}
    assert _try(shown["document"], {"ticker": "EXMP", "category": "OPERATING"})["actual"] == {
        "entity type": "company"}


def test_a_rule_with_no_otherwise_step_is_refused_by_the_engine():
    short = _short()
    del short["steps"][2]["otherwise"]
    refused = _show(short)
    assert list(refused) == ["refused"] and "otherwise" in refused["refused"]


def test_name_tokens_match_is_the_current_version_and_the_older_one_has_its_own_word():
    tokens = {"field": "name", "normalizer": "conformed", "token_list": ["FUND"], "min_count": 1}
    doc = {"normalizers": {"conformed": "normalize_text@edgar-conformed-v1"}}

    def decide(word):
        short = {"rule_id": "example", "version": "example-v1", "family": "classification",
                 "emits": ["fund_structure", "held back"],
                 "steps": [{"step": "1", "verdict": "fund_structure",
                            "when": [{"primitive": word, "args": tokens}]},
                           {"step": "2", "verdict": "held back", "otherwise": True}]}
        shown = _show(short)
        tried = press("Try", "entity_type", rule=json.dumps(shown["document"]),
                      inputs={"record": json.dumps({"name": "McZeph & Co"}), "doc": json.dumps(doc)})
        return shown, tried

    current, current_tried = decide("name tokens match")
    older, older_tried = decide("name tokens match with any ampersand")
    assert current["document"]["steps"][0]["when"][0]["primitive"] == "token_match@2"
    assert older["document"]["steps"][0]["when"][0]["primitive"] == "token_match@1"
    assert current_tried["actual"] == {"held back": "deferred"}
    assert older_tried["actual"] == {"entity type": "fund_structure"}


def test_a_probable_entity_type_is_a_label_on_a_held_back_step():
    short = _short()
    short["steps"][2]["probable entity type"] = "fund_structure"
    shown = _show(short)
    assert shown["document"]["steps"][2]["probable_kind"] == "fund_structure"
    assert {"word": "probable entity type", "stored": "probable_kind"} in shown["lines"]
    decided = _short()
    decided["steps"][1]["probable entity type"] = "fund_structure"
    refused = _show(decided)
    assert list(refused) == ["refused"] and "Probable Kind" in refused["refused"]


def test_a_bare_stored_key_is_refused_naming_the_word_to_type():
    for stored, word in [("deferred", "held back"), ("fields_all_empty@1", "these fields are empty"),
                         ("field_in_set@1", "field is one of"), ("token_match@2", "name tokens match"),
                         ("token_match@1", "name tokens match with any ampersand")]:
        short = _short()
        if stored == "deferred":
            short["steps"][0]["verdict"] = stored
        else:
            short["steps"][1]["when"][0]["primitive"] = stored
        refused = _show(short)
        assert list(refused) == ["refused"]
        assert f"'{stored}' is a stored key. Type '{word}' instead." in refused["refused"]
        assert "Words this file accepts" in refused["refused"]
    short = _short()
    short["steps"][2]["probable_kind"] = "fund_structure"
    assert "Type 'probable entity type' instead." in _show(short)["refused"]
    short = _short(emits=["company", "deferred"])
    assert "Type 'held back' instead." in _show(short)["refused"]


def test_a_bad_short_rule_is_a_refusal_not_a_traceback():
    steps = _short()["steps"]
    for rule in ["not json", "[1]", json.dumps({"rule_id": "x"}), json.dumps(_short(steps=[1])),
                 json.dumps(_short(steps=[{**steps[0], "when": [5]}, steps[2]])),
                 json.dumps(_short(emits="company")),
                 json.dumps(_short(family="binding")),
                 json.dumps(_short(steps=[{**steps[0], "when": [{"primitive": "no such test"}]}, steps[2]]))]:
        refused = show_full("entity_type", rule)
        assert list(refused) == ["refused"] and refused["refused"], rule


def test_the_page_lists_every_word_beside_its_stored_key():
    assert "entity_type" in families()
    full = load_full("entity_type")
    pairs = {(item["word"], item["stored"]) for item in full.words}
    assert pairs == {("field is one of", "field_in_set@1"),
                     ("these fields are empty", "fields_all_empty@1"),
                     ("name tokens match", "token_match@2"),
                     ("name tokens match with any ampersand", "token_match@1"),
                     ("held back", "deferred"),
                     ("probable entity type", "probable_kind"),
                     ("otherwise", "otherwise")}
