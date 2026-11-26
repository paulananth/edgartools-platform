"""The check-one-record family runs a pasted quality block on one pasted record."""
import json

from edgar_warehouse.rules.try_page import press

BLOCK = {
    "version": "example-quality-v1",
    "checks": [{"id": "name_required", "test": "present@1", "value": "fields.name",
                "on_fail": "exception", "args": {}}],
}


def _try(rule=None, fields='{"name": "Example Works"}', matching="", expected=None):
    rule = json.dumps(BLOCK) if rule is None else rule
    return press("Try", "check_record", rule=rule, inputs={"fields": fields, "matching": matching},
                 expected=expected)


def _block(**changes):
    return json.dumps({**BLOCK, **changes})


def test_a_present_name_passes_and_the_check_is_counted():
    passed = {"version": "example-quality-v1", "checks": {"name_required": {
        "kind": "present@1", "failure_action": "exception", "rows_checked": 1, "rows_failed": 0}}}
    tried = _try(expected=passed)
    assert tried["actual"] == passed
    assert tried["passed"] is True


def test_a_missing_name_is_held_out_with_exception_beside_it():
    held = {"held out": "quality_name_required", "on_fail": "exception"}
    for fields in ('{}', '{"name": ""}', '{"name": null}'):
        tried = _try(fields=fields, expected=held)
        assert tried["actual"] == held, fields
        assert tried["passed"] is True


def test_withhold_keeps_the_value_off_matching_and_flag_only_counts():
    checks = [{"id": "name_required", "test": "present@1", "value": "fields.name",
               "on_fail": "withhold", "args": {}},
              {"id": "name_listed", "test": "in_set@1", "value": "fields.name",
               "on_fail": "flag", "args": {"values": ["Sample Goods"]}}]
    actual = _try(rule=_block(checks=checks), fields='{"name": ""}')["actual"]
    assert actual["withheld"] == ["fields.name"]
    assert actual["flags"] == ["name_listed"]
    only_flag = _try(rule=_block(checks=checks[1:]), fields='{"name": "Example Works"}')["actual"]
    assert only_flag["flags"] == ["name_listed"]
    assert only_flag["checks"]["name_listed"]["rows_failed"] == 1


def test_a_fix_runs_before_the_check_so_a_cleared_stand_in_is_held_out():
    block = _block(fixes=[{"id": "clear_unknown", "fix": "blank_values@1",
                           "args": {"field": "fields.name", "values": ["UNKNOWN"]}}])
    held = _try(rule=block, fields='{"name": "UNKNOWN"}')["actual"]
    assert held == {"held out": "quality_name_required", "on_fail": "exception"}
    kept = _try(rule=block, fields='{"name": "Example Works"}')["actual"]
    assert "held out" not in kept


def test_the_matching_input_is_read_by_a_check():
    block = _block(checks=[{"id": "match_name", "test": "present@1", "value": "matching.name",
                            "on_fail": "exception", "args": {}}])
    assert "held out" not in _try(rule=block, fields="{}", matching='{"name": "EXAMPLE WORKS"}')["actual"]
    assert _try(rule=block, fields="{}", matching="")["actual"]["held out"] == "quality_match_name"


def test_a_bad_paste_is_a_refusal_not_a_traceback():
    for rule, fields, matching in [
        ("not json", '{"name": "Example Works"}', ""),
        ("[1]", '{"name": "Example Works"}', ""),
        (json.dumps({"checks": BLOCK["checks"]}), '{"name": "Example Works"}', ""),
        (_block(checks=[{**BLOCK["checks"][0], "test": "no_such_test@1"}]), '{"name": "x"}', ""),
        (_block(checks=[{**BLOCK["checks"][0], "on_fail": "stop"}]), '{"name": "x"}', ""),
        (_block(checks=[{**BLOCK["checks"][0], "value": "name"}]), '{"name": "x"}', ""),
        (json.dumps(BLOCK), "not json", ""),
        (json.dumps(BLOCK), "[1]", ""),
        (json.dumps(BLOCK), '{"name": "x"}', "not json"),
        (json.dumps(BLOCK), '{"name": "x"}', "[1]"),
        (json.dumps(BLOCK), "", ""),
    ]:
        refused = _try(rule=rule, fields=fields, matching=matching)
        assert list(refused) == ["refused"] and refused["refused"], (rule, fields, matching)
