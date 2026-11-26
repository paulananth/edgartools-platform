"""The field-value short words become a complete policy."""
import json
import shutil

from edgar_warehouse.rules.try_page import FAMILY_DIR, families, load_full, press, show_full

REGISTER = "example.register.v1"
DIRECTORY = "example.directory.v1"
FULL = {"kinds": {"example_company": {
    "defaults": {"sources": [REGISTER, DIRECTORY]},
    "fields": {"address": {"sources": [DIRECTORY, REGISTER]}},
}}}
SHORT = {"kinds": {"example_company": {
    "source order": [REGISTER, DIRECTORY],
    "fields": {"address": {"this field's order": [DIRECTORY, REGISTER]}},
}}}


def _claim(source, record, **fields):
    return {"fields": {name: {"assertion_id": f"{record}-a", "effective_at": "2026-09-01T00:00:00+00:00",
                              "op": "value", "record_key": record, "source_code": source, "value": value}
                       for name, value in fields.items()}}


INPUTS = {
    "kind": "example_company", "subjects": '["S1", "S2"]', "overrides": "",
    "as_of": "2026-09-22T00:00:00+00:00", "policy_digest": "digest-1",
    "claims": json.dumps({"S1": _claim(REGISTER, "R1", name="Example Works", address="1 Register Way"),
                          "S2": _claim(DIRECTORY, "D1", name="EXAMPLE WORKS LTD", address="2 Directory Road")}),
}


def _full(short):
    return show_full("field_value", json.dumps(short))


def _kind(**block):
    return {"kinds": {"example_company": block}}


def test_the_directory_then_register_case_in_words_matches_the_full_policy():
    shown = _full(SHORT)
    assert shown["document"] == FULL
    assert shown["lines"] == [
        {"word": "source order", "stored": "defaults.sources"},
        {"word": "this field's order", "stored": "fields.address.sources"},
    ]
    in_words = press("Try", "field_value", rule=json.dumps(shown["document"]), inputs=INPUTS)
    stored = press("Try", "field_value", rule=json.dumps(FULL), inputs=INPUTS)
    assert in_words["actual"] == stored["actual"]
    assert in_words["actual"]["fields"]["address"]["value"] == "2 Directory Road"
    assert in_words["actual"]["fields"]["name"]["value"] == "Example Works"


def test_the_words_for_blanking_and_age_work_for_a_field_and_for_the_entity_type():
    shown = _full(_kind(**{
        "source order": [REGISTER, DIRECTORY],
        "may blank the field": [DIRECTORY],
        "fields": {"address": {"this field's order": [DIRECTORY, REGISTER],
                               "may blank the field": [DIRECTORY], "ignore older than": 365}},
    }))
    assert shown["document"] == _kind(
        defaults={"sources": [REGISTER, DIRECTORY], "clear_sources": [DIRECTORY]},
        fields={"address": {"sources": [DIRECTORY, REGISTER], "clear_sources": [DIRECTORY], "max_age_days": 365}})
    assert {"word": "ignore older than", "stored": "fields.address.max_age_days"} in shown["lines"]
    assert {"word": "may blank the field", "stored": "defaults.clear_sources"} in shown["lines"]
    assert {"word": "may blank the field", "stored": "fields.address.clear_sources"} in shown["lines"]


def test_a_key_that_is_not_a_word_keeps_its_name():
    shown = _full(_kind(**{"version": "example-1", "source order": [REGISTER],
                           "defaults": {"allow_unknown_effective": True},
                           "fields": {"address": {"this field's order": [REGISTER],
                                                  "allow_unknown_effective": True}}}))
    assert shown["document"] == _kind(
        version="example-1", defaults={"allow_unknown_effective": True, "sources": [REGISTER]},
        fields={"address": {"sources": [REGISTER], "allow_unknown_effective": True}})


def test_a_bare_stored_key_is_refused_with_the_word_to_type_and_the_words_this_file_accepts():
    for short, bare, typed in [
        (_kind(fields={"address": {"sources": [REGISTER]}}), "sources", "'this field's order'"),
        (_kind(defaults={"sources": [REGISTER]}), "sources", "'source order'"),
        (_kind(sources=[REGISTER]), "sources", "'source order'"),
        (_kind(fields={"address": {"clear_sources": [DIRECTORY], "this field's order": [DIRECTORY]}}),
         "clear_sources", "'may blank the field'"),
        (_kind(fields={"address": {"max_age_days": 30, "this field's order": [DIRECTORY]}}),
         "max_age_days", "'ignore older than'"),
    ]:
        refused = _full(short)
        assert list(refused) == ["refused"], short
        assert f"'{bare}' is a stored key" in refused["refused"] and typed in refused["refused"], short
        assert "Words this file accepts: source order, this field's order, may blank the field, ignore older than." \
            in refused["refused"]


def test_a_word_in_the_wrong_place_is_refused_naming_the_right_one():
    one_field = _full(_kind(**{"this field's order": [REGISTER]}))
    assert "'source order'" in one_field["refused"]
    every_field = _full(_kind(fields={"address": {"source order": [REGISTER]}}))
    assert "'this field's order'" in every_field["refused"]
    set_twice = _full(_kind(**{"may blank the field": [DIRECTORY],
                               "defaults": {"may blank the field": [DIRECTORY]}}))
    assert "'may blank the field' is set twice" in set_twice["refused"]


def test_no_word_decides_that_two_masters_are_one_subject():
    for word in ("attach", "same subject", "merge", "consolidate"):
        refused = _full(_kind(**{"source order": [REGISTER], word: [DIRECTORY]}))
        assert list(refused) == ["refused"] and word in refused["refused"], word


def test_a_short_rule_the_engine_would_refuse_is_refused():
    for short in ["not json", "[1]", "{}", '{"kinds": {}}', '{"kinds": {"example_company": 5}}',
                  _kind(fields={"address": {}}),
                  _kind(**{"source order": REGISTER}),
                  _kind(**{"source order": [1]}),
                  _kind(fields={"address": {"this field's order": [REGISTER], "ignore older than": "30"}}),
                  _kind(fields={"address": {"this field's order": [REGISTER], "ignore older than": True}})]:
        refused = show_full("field_value", short if isinstance(short, str) else json.dumps(short))
        assert list(refused) == ["refused"] and refused["refused"], short


def test_the_page_ignores_the_short_words_until_the_run_file_exists(tmp_path):
    shutil.copy(FAMILY_DIR / "field_value_full.py", tmp_path)
    assert families(tmp_path) == []
    assert load_full("field_value", tmp_path) is None
    shutil.copy(FAMILY_DIR / "field_value.py", tmp_path)
    assert families(tmp_path) == ["field_value"]
    assert load_full("field_value", tmp_path).words[0] == {"word": "source order", "stored": "defaults.sources"}
