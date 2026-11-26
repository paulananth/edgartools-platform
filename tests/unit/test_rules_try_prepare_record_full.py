"""The prepare-the-record short words become a complete contract with a fixed entity type."""
import json
import shutil

from edgar_warehouse.rules.try_page import FAMILY_DIR, families, load_full, press, show_full
from tests.support.reading import reading

READING = reading({"name": "name"})
ROW = '{"id": "R1", "ident": "ID-100", "tax": "TX-7", "name": "Example Works"}'
PUBLICATION = '{"publication_key": "p1", "revision": 1, "artifact_sha256": "%s", "member": "m"}' % ("0" * 64)
STORED = {"schema_version": "1", "adapter": {
    "version": "example-v1", "kind": "company", "record_key": ["id"],
    "identifiers": {"example_id": "ident"}, "reading": READING}}


def _short(**adapter):
    return json.dumps({"schema_version": "1", "adapter": {"version": "example-v1", **adapter, "reading": READING}})


def _tried(rule):
    return press("Try", "prepare_record", rule=rule, inputs={
        "row": ROW, "source": "example.records.v1", "publication": PUBLICATION})


def test_the_fixed_type_case_in_words_matches_the_stored_key_contract():
    shown = show_full("prepare_record", _short(**{
        "entity type": "company", "record key": ["id"], "identifier": {"example_id": "ident"}}))
    assert shown["document"] == STORED
    assert shown["lines"] == [{"word": "entity type", "stored": "kind"},
                              {"word": "record key", "stored": "record_key"},
                              {"word": "identifier", "stored": "identifiers"}]
    tried = _tried(json.dumps(shown["document"]))
    assert tried["actual"]["kind"] == "company"
    assert tried["actual"]["record_key"] == "R1"
    assert tried["actual"]["identifiers"] == {"example_id": "ID-100"}
    assert tried["actual"] == _tried(json.dumps(STORED))["actual"]


def test_lookup_only_is_a_cross_reference_that_does_not_match_by_itself():
    shown = show_full("prepare_record", _short(**{
        "entity type": "company", "record key": ["id"], "identifier": {"example_id": "ident"},
        "lookup only": {"tax_id": "tax"}}))
    assert shown["document"]["adapter"]["cross_references"] == {"tax_id": "tax"}
    assert shown["lines"][-1] == {"word": "lookup only", "stored": "cross_references"}
    tried = _tried(json.dumps(shown["document"]))
    assert tried["actual"]["cross_references"] == {"tax_id": "TX-7"}
    assert tried["actual"]["identifiers"] == {"example_id": "ID-100"}


def test_a_bare_stored_key_is_refused_with_the_word_and_the_accepted_words():
    for bare, typed in [("kind", "entity type"), ("record_key", "record key"),
                        ("identifiers", "identifier"), ("cross_references", "lookup only")]:
        short = json.dumps({"adapter": {bare: {}}})
        refused = show_full("prepare_record", short)
        assert list(refused) == ["refused"]
        assert f"'{bare}' is a stored key. Type '{typed}' instead." in refused["refused"]
        assert "Words this file accepts: entity type, record key, identifier, lookup only." in refused["refused"]


def test_entity_type_rule_is_refused_here():
    for adapter in [{"entity type": "company", "entity type rule": {"kind": "company"}},
                    {"entity type rule": {"kind": "company", "rule_id": "example-rule", "version": "1"}},
                    {"classification": {"kind": "company"}}]:
        refused = show_full("prepare_record", json.dumps({"adapter": adapter}))
        assert list(refused) == ["refused"]
        assert "this contract fixes the entity type" in refused["refused"]
        assert "Prepare a record whose entity type comes from a rule" in refused["refused"]
    top = show_full("prepare_record", json.dumps({"classification": {}, "adapter": {"entity type": "company"}}))
    assert "this contract fixes the entity type" in top["refused"]


def test_a_paste_that_is_not_a_contract_is_refused():
    for short in ["not json", "[1]", json.dumps({"schema_version": "1"}), json.dumps({"adapter": []})]:
        refused = show_full("prepare_record", short)
        assert list(refused) == ["refused"] and refused["refused"], short


def test_the_page_ignores_the_short_words_until_the_run_file_exists(tmp_path):
    shutil.copy(FAMILY_DIR / "prepare_record_full.py", tmp_path)
    assert families(tmp_path) == []
    assert load_full("prepare_record", tmp_path) is None
    shutil.copy(FAMILY_DIR / "prepare_record.py", tmp_path)
    assert families(tmp_path) == ["prepare_record"]
    assert load_full("prepare_record", tmp_path).words[0] == {"word": "entity type", "stored": "kind"}
