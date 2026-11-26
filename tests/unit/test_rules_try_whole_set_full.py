"""The summarize-every-row short words become a complete reduce plan."""
import json

from edgar_warehouse.rules.bench_families.whole_set_full import explain
from edgar_warehouse.rules.source_engine import ReductionEngine

BOUNDS = {"max_rows": 100, "max_input_bytes": 4096, "max_state_bytes": 4096, "max_keys": 10,
          "max_members": 10, "max_output_rows": 10, "max_output_bytes": 4096}
ROWS = {"source": "main", "table": "rows", "keys": ["key"], "count": "frequency",
        "sample": None, "sample_limit": 0}
DISTINCT = {"source": "main", "table": "rows", "keys": ["key"], "member": "holder",
            "count": "count", "sample": "sample", "sample_limit": 5}
MOST = {"source": "main", "table": "rows", "keys": ["key"], "member": "holder",
        "count": "filed", "sample": "value", "sample_limit": 0}
ACCEPTED = "Words this file accepts: how many rows, distinct values, most frequent."


def _short(**modes):
    groups = {"rows": {**ROWS, "mode": modes.get("rows", "how many rows")},
              "distinct": {**DISTINCT, "mode": modes.get("distinct", "distinct values")},
              "most": {**MOST, "mode": modes.get("most", "most frequent")}}
    return json.dumps({"reduce": {**BOUNDS, "groups": groups}})


def _finish(document, *holders):
    engine = ReductionEngine(document["reduce"])
    rows = [{"key": "K1", "holder": holder} for holder in holders]
    for group in document["reduce"]["groups"]:
        engine.push(group, rows)
    return engine.finish()


def test_the_words_show_the_stored_modes_and_the_three_row_case_matches_ticket_10():
    shown = explain(_short())
    assert [group["mode"] for group in shown["document"]["reduce"]["groups"].values()] == [
        "count", "members", "most"]
    assert shown["lines"] == [{"word": "how many rows", "stored": "count"},
                              {"word": "distinct values", "stored": "members"},
                              {"word": "most frequent", "stored": "most"}]
    assert _finish(shown["document"], "Alpha", "Beta", "Alpha") == {
        "rows": [{"key": "K1", "frequency": 3}],
        "distinct": [{"key": "K1", "count": 2, "sample": [{"holder": "Alpha"}, {"holder": "Beta"}]}],
        "most": [{"key": "K1", "filed": 2, "value": "Alpha"}],
    }


def test_the_two_way_tie_in_those_words_is_blank():
    shown = explain(_short())
    assert _finish(shown["document"], "Alpha", "Beta")["most"] == [{"key": "K1", "filed": 1, "value": None}]


def test_a_word_not_used_is_not_listed_and_the_rest_of_the_paste_is_kept():
    short = json.loads(_short())
    del short["reduce"]["groups"]["distinct"], short["reduce"]["groups"]["most"]
    short["version"] = "draft-1"
    shown = explain(json.dumps(short))
    assert shown["lines"] == [{"word": "how many rows", "stored": "count"}]
    assert shown["document"]["version"] == "draft-1"
    assert shown["document"]["reduce"]["max_keys"] == 10


def test_a_bare_stored_mode_is_refused_with_the_word_to_type_and_the_words_this_file_accepts():
    for group, bare, typed in [("rows", "count", "how many rows"), ("distinct", "members", "distinct values"),
                               ("most", "most", "most frequent")]:
        refused = explain(_short(**{group: bare}))
        assert list(refused) == ["refused"]
        assert f"'{bare}' is a stored key. Type '{typed}' instead." in refused["refused"]
        assert ACCEPTED in refused["refused"]


def test_how_many_at_this_path_is_refused():
    refused = explain(_short(rows="how many at this path"))
    assert list(refused) == ["refused"]
    assert "'how many at this path'" in refused["refused"]
    assert "Type 'how many rows'" in refused["refused"]
    assert ACCEPTED in refused["refused"]


def test_any_other_word_is_refused_with_the_words_this_file_accepts():
    for mode in ["total", "", 3, None]:
        refused = explain(_short(rows=mode))
        assert list(refused) == ["refused"] and ACCEPTED in refused["refused"], mode


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    no_bounds = json.dumps({"reduce": {"groups": {"rows": {**ROWS, "mode": "how many rows"}}}})
    for short in ["not json", "[1]", "{}", json.dumps({"reduce": [1]}),
                  json.dumps({"reduce": {**BOUNDS, "groups": [1]}}),
                  json.dumps({"reduce": {**BOUNDS, "groups": {"rows": "how many rows"}}}),
                  json.dumps({"reduce": {**BOUNDS, "groups": {"rows": {**ROWS}}}}),
                  no_bounds]:
        refused = explain(short)
        assert list(refused) == ["refused"] and refused["refused"], short
    assert list(explain(None)) == ["refused"]
