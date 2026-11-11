"""A target marked `local: true` runs its source read and combine steps in the loader (ticket 210). The run
in the database holds only the steps after them: `staged` drops the local steps from the configuration, and
`stage_manifest` writes the run's manifest with each later step's input resolved to the local receipts."""
from copy import deepcopy

import pytest

from edgar_warehouse.bookkeeping.clean.config import Blocked, staged, validate
from edgar_warehouse.rules.files import source
from edgar_warehouse.workers import local

REF = {"uri": "file:///captured/a.json", "sha256": "a" * 64}
STEPS = [
    {"name": "read", "operation": "source.read", "requires": [], "checks": ["x"]},
    {"name": "combine", "operation": "source.combine", "requires": ["read"], "checks": ["x"]},
    {"name": "prepare", "operation": "mdm.prepare", "requires": ["combine"], "checks": ["x"]},
    {"name": "merge", "operation": "mastering.merge", "requires": ["prepare"], "checks": ["x"]},
]


def test_a_target_may_declare_itself_local_and_nothing_else_changes():
    body = deepcopy(source("openfigi"))
    body["bookkeeping"]["targets"]["mastering"]["local"] = True

    assert validate(body, "mastering")["local"] is True
    assert "local" not in validate(source("openfigi"), "mastering")


def test_local_must_be_a_boolean():
    body = deepcopy(source("openfigi"))
    body["bookkeeping"]["targets"]["mastering"]["local"] = "yes"

    with pytest.raises(Blocked, match="local"):
        validate(body, "mastering")


def test_staged_drops_the_local_steps_and_the_requirements_on_them():
    config = {"local": True, "steps": deepcopy(STEPS), "retry": {}}

    result = staged(config)

    assert [s["name"] for s in result["steps"]] == ["prepare", "merge"]
    assert result["steps"][0]["requires"] == []  # prepare no longer waits on a step that is not in the run
    assert result["steps"][1]["requires"] == ["prepare"]


def test_a_target_not_marked_local_is_left_whole():
    config = {"steps": deepcopy(STEPS)}

    assert staged(config) is config


def unit(key, input):
    return {"keys": {"k": key}, "input": input, "output": f"file:///out/{key}", "cursor": {}}


def test_the_manifest_of_the_run_resolves_later_inputs_to_the_local_receipts():
    manifest = {"version": 2, "capture": "run-1", "steps": {
        "read": [unit("r", REF)],
        "combine": [unit("c", {"from": {"step": "read", "key": "r"}})],
        "prepare": [unit("p", {"from": {"step": "combine", "key": "c"}})],
        "merge": [unit("m", {"from": {"step": "prepare", "key": "p"}})]}}
    items = [{"step": s, "key": u["keys"]["k"], "ordinal": 0, "unit": u}
             for s, us in manifest["steps"].items() for u in us]
    done = {("read", "r"): {"uri": "file:///out/r", "sha256": "1" * 64},
            ("combine", "c"): {"uri": "file:///out/c", "sha256": "2" * 64}}

    result = local.stage_manifest(manifest, STEPS, items, done, artifacts=None)

    assert result["capture"] == "run-1" and result["version"] == 2
    assert set(result["steps"]) == {"prepare", "merge"}
    assert result["steps"]["prepare"][0]["input"] == {"uri": "file:///out/c", "sha256": "2" * 64}
    assert result["steps"]["merge"][0]["input"] == {"from": {"step": "prepare", "key": "p"}}  # a database step stays


def test_a_composed_input_that_mixes_local_and_database_units_is_refused():
    mixed = {"compose": {"slots": {"a": {"step": "combine", "key": "c"}, "b": {"step": "merge", "key": "m"}},
                         "document": {"a": {"slot": "a"}, "b": {"slot": "b"}}}}
    manifest = {"version": 2, "steps": {"prepare": [unit("p", mixed)]}}
    items = [{"step": "prepare", "key": "p", "ordinal": 0, "unit": unit("p", mixed)}]

    with pytest.raises(Blocked, match="mixes"):
        local.stage_manifest(manifest, STEPS, items, {("combine", "c"): REF}, artifacts=None)
