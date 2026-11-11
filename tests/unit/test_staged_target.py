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


class Artifacts:
    def __init__(self, manifest):
        self.manifest, self.placed = manifest, []

    def json(self, ref):
        return self.manifest

    def put(self, root, document):
        self.placed.append((root, document))
        return {"uri": f"{root}/staged.json", "sha256": "9" * 64}


class Reader:
    def execute(self, envelope, artifacts):
        return {"uri": envelope["output"], "sha256": "3" * 64}


def test_a_local_target_is_staged_and_the_staged_manifest_is_what_the_run_takes(monkeypatch):
    manifest = {"version": 2, "steps": {"read": [unit("r", REF)], "prepare": [unit("p", {"from": {"step": "read", "key": "r"}})]}}
    config = {"local": True, "steps": STEPS[:1] + STEPS[2:3]}
    config["steps"][1] = {**STEPS[2], "requires": ["read"]}
    items = [{"step": s, "key": u["keys"]["k"], "ordinal": 0, "unit": u} for s, us in manifest["steps"].items() for u in us]
    monkeypatch.setattr(local, "validate", lambda body, target: config)
    monkeypatch.setattr(local, "worklist", lambda m, c: items)
    store = Artifacts(manifest)

    ref = local.staged_inputs(store, {"bookkeeping": {}}, "mastering", {"uri": "file:///m/manifest.json", "sha256": "0" * 64},
                              modules={"source.read": Reader()})

    assert ref == {"uri": "file:///m/staged-000000000000/staged.json", "sha256": "9" * 64}
    root, staged_manifest = store.placed[0]
    assert root == "file:///m/staged-000000000000" and set(staged_manifest["steps"]) == {"prepare"}
    assert staged_manifest["steps"]["prepare"][0]["input"] == {"uri": "file:///out/r", "sha256": "3" * 64}


def test_a_target_not_marked_local_keeps_its_manifest(monkeypatch):
    monkeypatch.setattr(local, "validate", lambda body, target: {"steps": STEPS})
    inputs = {"uri": "file:///m/manifest.json", "sha256": "0" * 64}

    assert local.staged_inputs(Artifacts({}), {"bookkeeping": {}}, "mastering", inputs) is inputs


def test_an_input_that_reads_another_run_is_a_database_input_even_when_a_local_step_has_the_name():
    other = {"from": {"run": "11111111-1111-1111-1111-111111111111", "step": "read", "key": "r"}}
    mixed = {"compose": {"slots": {"a": {"step": "combine", "key": "c"},
                                   "b": {"run": "11111111-1111-1111-1111-111111111111", "step": "read", "key": "r"}},
                         "document": {"a": {"slot": "a"}, "b": {"slot": "b"}}}}
    items = [{"step": "prepare", "key": "p", "ordinal": 0, "unit": unit("p", other)},
             {"step": "merge", "key": "m", "ordinal": 0, "unit": unit("m", mixed)}]
    manifest = {"version": 2, "steps": {}}

    with pytest.raises(Blocked, match="mixes"):
        local.stage_manifest(manifest, STEPS, items, {("read", "r"): REF, ("combine", "c"): REF}, artifacts=None)
    kept = local.stage_manifest(manifest, STEPS, items[:1], {("read", "r"): REF}, artifacts=None)
    assert kept["steps"]["prepare"][0]["input"] == other  # not resolved to this run's own local receipt


def test_a_local_step_that_requires_a_database_step_is_refused_by_the_configuration():
    body = deepcopy(source("openfigi"))
    target = body["bookkeeping"]["targets"]["mastering"]
    target["local"] = True
    gate = {**next(s for s in target["steps"] if s["operation"] == "journal.record"), "name": "gate", "requires": []}
    target["steps"].insert(0, gate)  # a database step before the first read, which then requires it
    next(s for s in target["steps"] if s["name"] == "requests")["requires"] = ["gate"]

    with pytest.raises(Blocked, match="local step requires only local steps"):
        validate(body, "mastering")
