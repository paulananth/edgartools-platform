"""`rules pending` says what a version changes, value by value, naming rules."""
from edgar_warehouse.rules.db import changes


def test_changes_name_values_and_rules():
    assert changes(None, {"a": 1}) == ["new: nothing of this name is active yet"]
    assert changes({"a": 1, "b": 2}, {"a": 1, "c": 3}) == ["removed b", "added c"]
    assert changes({"a": {"b": 1}}, {"a": {"b": 2}}) == ["changed a.b: 1 -> 2"]
    assert changes({"r": [{"rule_id": "x", "v": 1}]}, {"r": [{"rule_id": "x", "v": 2}, {"rule_id": "y"}]}) == [
        "added r: y", "changed r[x].v: 1 -> 2"]
    long = changes({"l": ["a" * 200]}, {"l": ["b" * 200]})[0]
    assert long.endswith("...") and len(long) < 260
