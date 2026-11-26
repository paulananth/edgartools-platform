"""The summarize-every-row family finishes a pasted reduce plan over pasted rows."""
import json
import sys

from edgar_warehouse.rules.try_page import press

BOUNDS = {"max_rows": 100, "max_input_bytes": 4096, "max_state_bytes": 4096, "max_keys": 10,
          "max_members": 10, "max_output_rows": 10, "max_output_bytes": 4096}
GROUPS = {
    "rows": {"source": "main", "table": "rows", "keys": ["key"], "mode": "count",
             "count": "frequency", "sample": None, "sample_limit": 0},
    "distinct": {"source": "main", "table": "rows", "keys": ["key"], "mode": "members",
                 "member": "holder", "count": "count", "sample": "sample", "sample_limit": 5},
    "most": {"source": "main", "table": "rows", "keys": ["key"], "mode": "most",
             "member": "holder", "count": "filed", "sample": "value", "sample_limit": 0},
}
PLAN = json.dumps({"reduce": {**BOUNDS, "groups": GROUPS}})


def _rows(*holders):
    return [{"key": "K1", "holder": holder} for holder in holders]


def _pasted(*holders):
    rows = _rows(*holders)
    return json.dumps({"rows": rows, "distinct": rows, "most": rows})


def _try(rule=PLAN, rows=None, expected=None):
    return press("Try", "whole_set", rule=rule, inputs={"rows": _pasted("Alpha", "Beta", "Alpha")
                                                          if rows is None else rows},
                 expected=expected)


def test_three_rows_two_of_them_the_same_member_give_the_count_the_distinct_values_and_the_most_frequent():
    tried = _try(expected={"groups": {
        "rows": [{"key": "K1", "frequency": 3}],
        "distinct": [{"key": "K1", "count": 2, "sample": [{"holder": "Alpha"}, {"holder": "Beta"}]}],
        "most": [{"key": "K1", "filed": 2, "value": "Alpha"}],
    }})
    assert tried["passed"] is True


def test_a_two_way_tie_leaves_the_most_frequent_blank():
    tried = _try(rows=_pasted("Alpha", "Beta"))
    assert tried["actual"]["groups"]["most"] == [{"key": "K1", "filed": 1, "value": None}]
    assert tried["actual"]["groups"]["rows"] == [{"key": "K1", "frequency": 2}]


def test_a_row_that_files_no_value_votes_for_none_and_a_group_with_no_rows_is_empty():
    rows = json.dumps({"most": [{"key": "K1", "holder": None}, {"key": "K1", "holder": "Alpha"}]})
    tried = _try(rows=rows)
    assert tried["actual"]["groups"] == {"rows": [], "distinct": [],
                                         "most": [{"key": "K1", "filed": 1, "value": "Alpha"}]}


def test_the_rows_of_two_keys_come_out_in_key_order_each_summarized_alone():
    rows = [{"key": "K2", "holder": "Beta"}, {"key": "K1", "holder": "Alpha"}, {"key": "K2", "holder": "Beta"}]
    tried = _try(rows=json.dumps({"rows": rows}))
    assert tried["actual"]["groups"]["rows"] == [{"key": "K1", "frequency": 1}, {"key": "K2", "frequency": 2}]


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    tight = json.dumps({"reduce": {**BOUNDS, "max_keys": 1, "groups": GROUPS}})
    two_keys = json.dumps({"rows": [{"key": "K1"}, {"key": "K2"}]})
    for rule, rows in [
        ("not json", _pasted("Alpha")),
        ("[1]", _pasted("Alpha")),
        (json.dumps({"version": "draft-1"}), _pasted("Alpha")),
        (json.dumps({"reduce": [1]}), _pasted("Alpha")),
        (json.dumps({"reduce": {**BOUNDS, "groups": {}}}), _pasted("Alpha")),
        (json.dumps({"reduce": {**BOUNDS, "groups": {"rows": {**GROUPS["rows"], "mode": "total"}}}}),
         _pasted("Alpha")),
        (PLAN, "not json"),
        (PLAN, "[1]"),
        (PLAN, json.dumps({"rows": {"key": "K1"}})),
        (PLAN, json.dumps({"no_such_group": _rows("Alpha")})),
        (PLAN, json.dumps({"rows": ["K1"]})),
        (PLAN, json.dumps({"rows": [{"key": 1}]})),
        (PLAN, json.dumps({"distinct": [{"key": "K1"}]})),
        (tight, two_keys),
    ]:
        refused = _try(rule=rule, rows=rows)
        assert list(refused) == ["refused"] and refused["refused"], (rule, rows)
    absent = press("Try", "whole_set", rule=PLAN, inputs={})
    assert list(absent) == ["refused"] and absent["refused"]


def test_a_blank_rows_box_summarizes_nothing():
    assert _try(rows="  ")["actual"]["groups"] == {"rows": [], "distinct": [], "most": []}


def test_the_family_does_not_use_the_grouping_family():
    _try()
    assert "edgar_warehouse.rules.bench_families.group_rows" not in sys.modules
