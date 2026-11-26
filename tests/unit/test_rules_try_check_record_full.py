"""The check-one-record short words become a complete quality block."""
import json
import shutil

from edgar_warehouse.rules.try_page import FAMILY_DIR, families, load_full, press, show_full

VERSION = "example-quality-v1"
HELD = {"held out": "quality_name_required"}


def _short(test="is present", on_fail="hold the record out", **check):
    return json.dumps({"version": VERSION, "checks": [
        {"id": "name_required", "test": test, "value": "fields.name", "on_fail": on_fail, "args": {}, **check}]})


def _try(document, fields):
    return press("Try", "check_record", rule=json.dumps(document),
                 inputs={"fields": fields, "matching": ""}, expected=HELD)


def test_the_missing_name_in_short_words_matches_the_run_file():
    shown = show_full("check_record", _short())
    assert shown["lines"] == [{"word": "is present", "stored": "present@1"},
                              {"word": "hold the record out", "stored": "exception"}]
    assert shown["document"] == {"version": VERSION, "checks": [
        {"id": "name_required", "test": "present@1", "value": "fields.name", "on_fail": "exception", "args": {}}]}
    held = _try(shown["document"], "{}")
    assert held["actual"] == HELD and held["passed"] is True
    assert "held out" not in _try(shown["document"], '{"name": "Example Works"}')["actual"]


def test_the_shown_block_keeps_the_version_the_person_types():
    shown = show_full("check_record", json.dumps({"version": "example-quality-v7", "checks": []}))
    assert shown["document"]["version"] == "example-quality-v7"
    assert shown["lines"] == []


def test_each_word_shows_its_stored_key():
    for word, stored, field in [("keep off matching", "withhold", "on_fail"),
                                ("count the failure", "flag", "on_fail")]:
        shown = show_full("check_record", _short(on_fail=word))
        assert shown["document"]["checks"][0]["on_fail"] == stored
        assert {"word": word, "stored": stored} in shown["lines"]
    pinned = show_full("check_record", _short(
        test="in the pinned code set", args={"table": "approved_codes", "sha256": "0" * 64}))
    assert pinned["document"]["checks"][0]["test"] == "in_reference@1"
    assert pinned["lines"][0] == {"word": "in the pinned code set", "stored": "in_reference@1"}


def test_a_stored_key_that_is_not_a_word_keeps_its_name():
    shown = show_full("check_record", _short(
        test="in_set@1", id="name_listed", on_fail="count the failure", args={"values": ["Sample Goods"]}))
    assert shown["document"]["checks"][0]["test"] == "in_set@1"
    assert shown["lines"] == [{"word": "count the failure", "stored": "flag"}]


def test_a_bare_stored_key_is_refused_with_the_words_this_file_accepts():
    for short, bare, typed in [
        (_short(test="present@1"), "present@1", "is present"),
        (_short(on_fail="exception"), "exception", "hold the record out"),
        (_short(on_fail="withhold"), "withhold", "keep off matching"),
        (_short(on_fail="flag"), "flag", "count the failure"),
        (_short(test="in_reference@1"), "in_reference@1", "in the pinned code set"),
    ]:
        refused = show_full("check_record", short)
        assert list(refused) == ["refused"], bare
        assert f"'{bare}' is a stored key. Type '{typed}' instead." in refused["refused"]
        assert "Words this file accepts:" in refused["refused"] and "count the failure" in refused["refused"]


def test_a_paste_the_quality_engine_refuses_is_a_refusal():
    for short in ["not json", "[1]", json.dumps({"checks": []}), json.dumps({"version": VERSION, "checks": "x"}),
                  _short(test="no such word"), _short(on_fail="stop the run"),
                  _short(value="name")]:
        refused = show_full("check_record", short)
        assert list(refused) == ["refused"] and refused["refused"], short


def test_the_page_ignores_the_short_words_until_the_run_file_exists(tmp_path):
    shutil.copy(FAMILY_DIR / "check_record_full.py", tmp_path)
    assert families(tmp_path) == []
    assert load_full("check_record", tmp_path) is None
    shutil.copy(FAMILY_DIR / "check_record.py", tmp_path)
    assert families(tmp_path) == ["check_record"]
    assert load_full("check_record", tmp_path).words[0] == {"word": "is present", "stored": "present@1"}
