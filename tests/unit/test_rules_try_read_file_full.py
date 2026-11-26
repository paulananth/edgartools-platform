"""The read-the-file short words become a complete read document."""
import json
import shutil

from edgar_warehouse.rules.try_page import FAMILY_DIR, families, load_full, press, show_full

FILE = '{"records":[{"id":"R1","name":"  Example Works  ","quantity":"12","price":2.50}]}'
LIMITS = {"max_bytes": 4096, "max_records": 10}


def _short(columns, **table):
    return json.dumps({"read": {"format": "json", "limits": LIMITS, "tables": {
        "records": {"each": "records", "columns": columns, **table}}}})


def _full(columns, **table):
    return show_full("read_file", _short(columns, **table))


def test_the_shown_document_reads_the_invented_row():
    short = _short(
        {"id": {"text": {"path": "id"}}, "name": {"text": {"path": "name"}},
         "quantity": {"integer": {"path": "quantity"}}},
        checks=[{"check": "text is there", "column": "id", "on_fail": "skip the row", "reason": "missing_id"}])
    shown = show_full("read_file", short)
    assert shown["document"]["read"]["tables"]["records"]["checks"] == [
        {"check": "required", "column": "id", "on_fail": "defer", "reason": "missing_id"}]
    assert shown["lines"] == [{"word": "text is there", "stored": "required"},
                              {"word": "skip the row", "stored": "defer"}]
    tried = press("Try", "read_file", rule=json.dumps(shown["document"]), inputs={"file": FILE, "lookups": ""},
                  expected={"tables": {"records": [{"id": "R1", "name": "Example Works", "quantity": 12}]},
                            "deferred": []})
    assert tried["passed"] is True


def test_a_word_shows_the_stored_key_and_what_it_adds():
    shown = _full({"price": {"exact decimal": {"path": "price"}},
                   "has_name": {"key exists": {"path": "name"}},
                   "row": {"row number": {}}})
    assert shown["document"]["read"]["tables"]["records"]["columns"] == {
        "price": {"value": {"path": "price", "decimals": "text", "big_numbers": "text"}},
        "has_name": {"test": {"path": "name", "kind": "present"}},
        "row": {"ordinal": {}},
    }
    assert shown["lines"] == [{"word": "exact decimal", "stored": "value"},
                              {"word": "key exists", "stored": "test"},
                              {"word": "row number", "stored": "ordinal"}]
    tried = press("Try", "read_file", rule=json.dumps(shown["document"]), inputs={"file": FILE, "lookups": ""})
    assert tried["actual"]["tables"]["records"] == [{"price": "2.50", "has_name": True, "row": 1}]


def test_a_word_works_inside_a_call_and_an_iteration():
    shown = _full({"label": {"if": {"condition": {"key exists": {"path": "name"}},
                                    "then": {"text": {"path": "name"}},
                                    "else": {"fixed": {"value": "none"}}}}},
                  each={"which list": {"condition": {"shape": {"path": "records", "kind": "array"}},
                                       "then": "records", "else": {"no rows": {}}}})
    table = shown["document"]["read"]["tables"]["records"]
    assert table["columns"]["label"]["choose"]["condition"] == {"test": {"path": "name", "kind": "present"}}
    assert table["columns"]["label"]["choose"]["else"] == {"const": {"value": "none"}}
    assert table["each"] == {"choose": {"condition": {"test": {"path": "records", "kind": "array"}},
                                        "then": "records", "else": {"empty": {}}}}
    tried = press("Try", "read_file", rule=json.dumps(shown["document"]), inputs={"file": FILE, "lookups": ""})
    assert tried["actual"]["tables"]["records"] == [{"label": "Example Works"}]


def test_a_bare_stored_key_is_refused_with_the_words_this_file_accepts():
    for columns, bare, typed in [
        ({"price": {"number": {"path": "price"}}}, "number", "floating-point"),
        ({"names": {"join": {"path": "names", "separator": ","}}}, "join", "join text"),
        ({"price": {"value": {"path": "price"}}}, "value", "exact decimal"),
    ]:
        refused = _full(columns)
        assert list(refused) == ["refused"]
        assert f"'{bare}' is a stored key" in refused["refused"] and typed in refused["refused"]
        assert "Words this file accepts:" in refused["refused"] and "in the caller's list" in refused["refused"]
    bare_check = _full({"id": {"text": {"path": "id"}}},
                       checks=[{"check": "required", "column": "id", "on_fail": "defer", "reason": "x"}])
    assert "'required' is a stored key. Type 'text is there' instead." in bare_check["refused"]
    bare_outcome = _full({"id": {"text": {"path": "id"}}},
                         checks=[{"check": "text is there", "column": "id", "on_fail": "reject", "reason": "x"}])
    assert "'reject' is a stored key. Type 'refuse the file' instead." in bare_outcome["refused"]


def test_a_key_that_is_not_a_call_keeps_its_name():
    short = json.dumps({"read": {"format": "json", "limits": LIMITS, "context": {"run": {"type": "text"}},
                                 "tables": {"records": {"each": "records", "columns": {
                                     "run": {"supplied fact": {"name": "run"}},
                                     "context": {"text": {"path": "id"}}}}}}})
    shown = show_full("read_file", short)
    assert shown["document"]["read"]["context"] == {"run": {"type": "text"}}
    assert shown["document"]["read"]["tables"]["records"]["columns"] == {
        "run": {"context": {"name": "run"}}, "context": {"text": {"path": "id"}}}


def test_the_full_document_is_one_the_engine_loads():
    for short in ["not json", "[1]", json.dumps({"read": {"format": "no such format"}}),
                  _short({"x": {"no such word": {"path": "x"}}})]:
        refused = show_full("read_file", short)
        assert list(refused) == ["refused"] and refused["refused"], short


def test_the_page_ignores_the_short_words_until_the_run_file_exists(tmp_path):
    shutil.copy(FAMILY_DIR / "read_file_full.py", tmp_path)
    assert families(tmp_path) == []
    assert load_full("read_file", tmp_path) is None
    shutil.copy(FAMILY_DIR / "read_file.py", tmp_path)
    assert families(tmp_path) == ["read_file"]
    assert load_full("read_file", tmp_path).words[0] == {"word": "exact decimal", "stored": "value"}
