"""The group-and-attach-rows family combines pasted tables with a pasted plan."""
import copy
import json

from edgar_warehouse.rules.try_page import press

GROUP = {"source": "extra", "table": "names", "key": "id", "value": "alias", "mode": "collect",
         "order_by": ["alias"], "distinct": True, "skip_null_values": True, "checks": {}, "where": {}}
PLAN = {"execution": {"profile": "source.combine"}, "combine": {
    "max_rows": 1000,
    "groups": {"aliases": GROUP},
    "tables": {"records": {"source": "primary", "table": "records", "checks": {}, "where": {},
                           "joins": {"aliases": {"group": "aliases", "key": "id",
                                                 "on_missing": "empty", "replace": False}}}},
}}
TABLES = {"primary": {"records": [{"id": "R1"}]},
          "extra": {"names": [{"id": "R1", "alias": "B"}, {"id": "R1", "alias": "A"}]}}


def _plan(**group):
    plan = copy.deepcopy(PLAN)
    plan["combine"]["groups"]["aliases"].update(group)
    return json.dumps(plan)


def _try(rule=None, tables=None, expected=None):
    return press("Try", "group_rows", rule=json.dumps(PLAN) if rule is None else rule,
                 inputs={"tables": json.dumps(TABLES) if tables is None else tables}, expected=expected)


def test_the_invented_row_carries_its_two_aliases_in_order():
    tried = _try(expected={"tables": {"records": [{"id": "R1", "aliases": ["A", "B"]}]}})
    assert tried["passed"] is True
    assert tried["actual"]["tables"]["records"] == [{"id": "R1", "aliases": ["A", "B"]}]


def test_a_flat_collection_joins_one_level_of_values_sorted():
    rule = _plan(mode="collect_flat", value="parts", order_by=[], sort_values=True)
    tables = {"primary": {"records": [{"id": "R1"}]},
              "extra": {"names": [{"id": "R1", "parts": ["B", "A"]}, {"id": "R1", "parts": ["A"]}]}}
    tried = _try(rule=rule, tables=json.dumps(tables))
    assert tried["actual"]["tables"]["records"] == [{"id": "R1", "aliases": ["A", "B"]}]


def test_a_row_with_no_names_gets_an_empty_list_or_is_refused_as_the_plan_says():
    tables = json.dumps({"primary": {"records": [{"id": "R1"}]}, "extra": {"names": []}})
    assert _try(tables=tables)["actual"]["tables"]["records"] == [{"id": "R1", "aliases": []}]
    plan = copy.deepcopy(PLAN)
    plan["combine"]["tables"]["records"]["joins"]["aliases"]["on_missing"] = "error"
    refused = _try(rule=json.dumps(plan), tables=tables)
    assert list(refused) == ["refused"] and "aliases" in refused["refused"]


def test_exactly_one_refuses_two_matching_rows_even_when_equal():
    tables = json.dumps({"primary": {"records": [{"id": "R1"}]},
                         "extra": {"names": [{"id": "R1", "alias": "A"}, {"id": "R1", "alias": "A"}]}})
    refused = _try(rule=_plan(mode="one", distinct=False), tables=tables)
    assert list(refused) == ["refused"] and refused["refused"]
    single = json.dumps({"primary": {"records": [{"id": "R1"}]},
                         "extra": {"names": [{"id": "R1", "alias": "A"}]}})
    assert _try(rule=_plan(mode="one", distinct=False), tables=single)["actual"]["tables"]["records"] == [
        {"id": "R1", "aliases": "A"}]


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    unknown_mode = _plan(mode="no such mode", distinct=False)
    missing_reading = json.dumps({"primary": TABLES["primary"]})
    cases = [
        ("not json", None),
        ("[1]", None),
        (json.dumps({"combine": PLAN["combine"]}), None),
        (unknown_mode, None),
        (None, "not json"),
        (None, "[1]"),
        (None, missing_reading),
        (None, json.dumps({"primary": {"records": ["R1"]}, "extra": TABLES["extra"]})),
        (None, json.dumps({"primary": {"records": [{"id": "R1"}]}, "extra": {"other": []}})),
        (None, json.dumps({"primary": {"records": [{"id": 1.5}]}, "extra": TABLES["extra"]})),
        (None, '{"primary": {"records": [{"id": NaN}]}, "extra": {"names": []}}'),
    ]
    for rule, tables in cases:
        refused = _try(rule=rule, tables=tables)
        assert list(refused) == ["refused"] and refused["refused"], (rule, tables)


def test_more_rows_than_the_plan_allows_are_refused():
    plan = copy.deepcopy(PLAN)
    plan["combine"]["max_rows"] = 2
    refused = _try(rule=json.dumps(plan))
    assert list(refused) == ["refused"] and "2" in refused["refused"]
