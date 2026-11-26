"""The rule-decided short words become a complete contract whose entity type comes from a rule."""
import json
import shutil

from edgar_warehouse.rules.try_page import FAMILY_DIR, families, load_full, press, show_full
from tests.support.reading import reading

READING = reading({"name": "name"})
ROW = '{"id": "R1", "ident": "ID-100", "tax": "TX-7", "name": "Example Works", "category": "operating"}'
PUBLICATION = '{"publication_key": "p1", "revision": 1, "artifact_sha256": "%s", "member": "m"}' % ("0" * 64)
NAMED = {"kind": "company", "rule_id": "example-rule", "version": "1"}
SAID = {"entity type": "company", "rule_id": "example-rule", "version": "1"}
STORED = {"schema_version": "1", "adapter": {
    "version": "example-v1", "classification": NAMED, "record_key": ["id"],
    "identifiers": {"example_id": "ident"}, "reading": READING}}
POLICY = json.dumps({
    "automatic_rules": [{"kind": "company", "family": "classification", "rule_id": "example-rule",
                         "rule_version": "1", "verdict": "company"}],
    "kinds": {"company": {"rules": [{
        "rule_id": "example-rule", "version": "1", "family": "classification",
        "emits": ["company", "deferred"],
        "steps": [{"step": "1", "verdict": "company",
                   "when": [{"primitive": "field_in_set@1",
                             "args": {"field": "category", "values": ["operating"]}}]},
                  {"step": "2", "verdict": "deferred", "otherwise": True}]}]}}})


def _short(**adapter):
    return json.dumps({"schema_version": "1", "adapter": {"version": "example-v1", **adapter, "reading": READING}})


def _tried(rule):
    return press("Try", "prepare_by_type_rule", rule=rule, inputs={
        "row": ROW, "source": "example.records.v1", "publication": PUBLICATION, "policy": POLICY})


def test_the_rule_decided_case_in_words_matches_the_stored_key_contract():
    shown = show_full("prepare_by_type_rule", _short(**{
        "entity type rule": {"entity type": "company", "rule_id": "example-rule", "version": "1"},
        "record key": ["id"], "identifier": {"example_id": "ident"}}))
    assert shown["document"] == STORED
    assert shown["lines"] == [{"word": "entity type rule", "stored": "classification"},
                              {"word": "entity type", "stored": "kind"},
                              {"word": "record key", "stored": "record_key"},
                              {"word": "identifier", "stored": "identifiers"}]
    tried = _tried(json.dumps(shown["document"]))
    assert tried["actual"]["kind"] == "company"
    assert tried["actual"]["record_key"] == "R1"
    assert tried["actual"]["provenance"]["classification"] == {"rule_id": "example-rule", "version": "1", "step": "1"}
    assert tried["actual"] == _tried(json.dumps(STORED))["actual"]


def test_the_words_of_the_fixed_type_page_are_accepted_here_too():
    shown = show_full("prepare_by_type_rule", _short(**{
        "entity type rule": SAID, "record key": ["id"], "identifier": {"example_id": "ident"},
        "lookup only": {"tax_id": "tax"}}))
    assert shown["document"]["adapter"]["cross_references"] == {"tax_id": "tax"}
    assert shown["lines"][-1] == {"word": "lookup only", "stored": "cross_references"}
    assert _tried(json.dumps(shown["document"]))["actual"]["cross_references"] == {"tax_id": "TX-7"}


def test_a_bare_stored_key_is_refused_with_the_word_and_the_accepted_words():
    for adapter, bare, typed in [({"classification": NAMED}, "classification", "entity type rule"),
                                 ({"kind": "company"}, "kind", "entity type"),
                                 ({"record_key": ["id"]}, "record_key", "record key"),
                                 ({"identifiers": {}}, "identifiers", "identifier"),
                                 ({"cross_references": {}}, "cross_references", "lookup only"),
                                 ({"entity type rule": {"kind": "company"}}, "kind", "entity type")]:
        refused = show_full("prepare_by_type_rule", json.dumps({"adapter": adapter}))
        assert list(refused) == ["refused"]
        assert f"'{bare}' is a stored key. Type '{typed}' instead." in refused["refused"]
        assert ("Words this file accepts: entity type, record key, identifier, lookup only, entity type rule."
                in refused["refused"])


def test_an_entity_type_and_an_entity_type_rule_together_are_refused():
    refused = show_full("prepare_by_type_rule", _short(**{"entity type": "company", "entity type rule": SAID}))
    assert "not both" in refused["refused"]


def test_a_paste_that_is_not_a_contract_is_refused():
    for short in ["not json", "[1]", json.dumps({"schema_version": "1"}), json.dumps({"adapter": []})]:
        refused = show_full("prepare_by_type_rule", short)
        assert list(refused) == ["refused"] and refused["refused"], short


def test_only_this_file_accepts_entity_type_rule():
    accepted = []
    for name in families():
        full = load_full(name)
        if any(item["word"] == "entity type rule" for item in getattr(full, "words", [])):
            accepted.append(name)
    assert accepted == ["prepare_by_type_rule"]


def test_the_page_ignores_the_short_words_until_the_run_file_exists(tmp_path):
    shutil.copy(FAMILY_DIR / "prepare_by_type_rule_full.py", tmp_path)
    assert families(tmp_path) == []
    assert load_full("prepare_by_type_rule", tmp_path) is None
    shutil.copy(FAMILY_DIR / "prepare_by_type_rule.py", tmp_path)
    assert families(tmp_path) == ["prepare_by_type_rule"]
    assert load_full("prepare_by_type_rule", tmp_path).words[-1] == {"word": "entity type rule", "stored": "classification"}
