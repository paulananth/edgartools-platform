"""Every load target has one shape, and it expands to the steps the engine runs."""
import json
from pathlib import Path

import pytest

from edgar_warehouse.rules import files, shape

# The steps of every target, recorded once from the hand-written step lists.
STEPS = json.loads(Path(__file__).with_name("load_target_steps.json").read_text())
SOURCES = sorted(path.parent.name for path in (files.ROOT / "sources").glob("*/source.yaml"))


def targets():
    return {f"{name}/{target}": body for name in SOURCES
            for target, body in (files.source(name).get("bookkeeping", {}).get("targets") or {}).items()}


def test_every_target_is_recorded():
    assert sorted(targets()) == sorted(STEPS)


@pytest.mark.parametrize("name", sorted(STEPS))
def test_a_target_gives_its_recorded_steps(name):
    assert targets()[name] == STEPS[name]


def test_a_target_says_extract_master_and_silver_and_gets_every_step():
    target = shape.expand({
        "extract": [{"name": "read", "read": "fields.yaml", "files": "*.json", "units": {"each": "file"}},
                    {"name": "joined", "combine": "join.yaml", "requires": ["read"], "readings": {"a": {"step": "read"}}}],
        "master": {"keys": {"table": "t", "dataset": "invented.v1"}, "readings": {"joined": {"all": "joined"}}},
        "silver": [{"name": "land_a", "land": {"table": "a", "silver": "a"}, "requires": ["read", "merge"]},
                   {"name": "land_b", "land": {"table": "b", "silver": "b"}, "requires": ["read", "merge"]}]})

    steps = target["steps"]
    assert [(s["name"], s["operation"], s["requires"]) for s in steps] == [
        ("read", "source.read", []), ("joined", "source.combine", ["read"]),
        ("prepare", "mdm.prepare", ["joined"]), ("merge", "mastering.merge", ["prepare"]),
        ("land_a", "silver.land", ["read", "merge"]), ("land_b", "silver.land", ["read", "merge"]),
        ("processed", "journal.record", ["land_a", "land_b"])]  # the record waits for every step nothing waits for
    assert steps[0]["input"] == {"contract": "fields.yaml", "files": "*.json"} and steps[0]["units"] == {"each": "file"}
    assert steps[3] == {"name": "merge", "operation": "mastering.merge", "requires": ["prepare"], "key": "{batch_id}",
                        "leases": ["mdm:consumer:{consumer}"], "checks": ["input.hash", "output.receipt", "mdm.committed"]}
    assert target["checks"] == ["manifest.hash", "work.accounting", "journal.delivered"]


def test_a_silver_only_target_masters_nothing():
    steps = shape.expand({"extract": [{"name": "read", "read": None}],
                          "silver": [{"name": "land", "land": {"table": "t", "silver": "t"}},
                                     {"name": "built", "derive": {"build": "b", "silver": "s", "reads": "t"}}]})["steps"]
    assert [(s["name"], s["requires"]) for s in steps] == [
        ("read", []), ("land", ["read"]), ("built", ["land"]), ("processed", ["built"])]
    assert "input" not in steps[0]


@pytest.mark.parametrize("target", [
    {"extract": [{"name": "read", "read": None}], "steps": []},                 # both ways of writing a target
    {"extract": []},                                                               # nothing extracted
    {"extract": [{"name": "read"}]},                                              # neither read nor combine
    {"extract": [{"name": "read", "read": None, "combine": None}]},              # both
    {"extract": [{"name": "read", "read": None}], "master": {"keys": {}}},       # no readings
    {"extract": [{"name": "read", "read": None}], "silver": [{"name": "x", "land": {}, "extra": 1}]},
])
def test_a_target_outside_the_shape_is_refused(target):
    with pytest.raises(shape.ShapeError):
        shape.expand(target)


def test_a_target_that_lists_its_steps_is_left_as_it_is():
    target = {"steps": [{"name": "capture"}], "checks": ["manifest.hash"]}
    assert shape.expand(target) is target
