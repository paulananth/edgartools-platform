"""A target marked `local: true` runs its source read and combine steps in the loader (ticket 210). The run
in the database holds only the steps after them: `staged` drops the local steps from the configuration, and
`stage_manifest` writes the run's manifest with each later step's input resolved to the local receipts."""
from copy import deepcopy

import pytest

from edgar_warehouse.bookkeeping.clean.config import Blocked, staged, validate
from edgar_warehouse.rules.files import source
from edgar_warehouse.rules import local

REF = {"uri": "file:///captured/a.json", "sha256": "a" * 64}
STEPS = [
    {"name": "read", "operation": "source.read", "requires": [], "checks": ["x"]},
    {"name": "combine", "operation": "source.combine", "requires": ["read"], "checks": ["x"]},
    {"name": "prepare", "operation": "mdm.prepare", "requires": ["combine"], "checks": ["x"]},
    {"name": "merge", "operation": "mastering.merge", "requires": ["prepare"], "checks": ["x"]},
]


def by_the_unit(name: str) -> dict:
    """A source's rules with its targets held by the unit, as a `local` target's steps are then staged."""
    body = deepcopy(source(name))
    for target in body["bookkeeping"]["targets"].values():
        target.pop("grain", None)
    return body


def test_a_target_may_declare_itself_local_and_nothing_else_changes():
    body = by_the_unit("sec.nport.registrant")
    body["bookkeeping"]["targets"]["mastering"]["local"] = True

    assert validate(body, "mastering")["local"] is True
    assert "local" not in validate(by_the_unit("sec.nport.registrant"), "mastering")


def test_openfigi_mastering_held_by_the_unit_is_local_and_its_run_starts_at_prepare():
    config = validate(by_the_unit("openfigi"), "mastering")

    assert config["local"] is True
    assert [step["name"] for step in staged(config)["steps"]] == ["prepare", "merge", "processed"]


def test_a_local_target_at_grain_run_holds_no_step_at_all():
    config = validate(source("openfigi"), "mastering")

    assert (config["grain"], config["local"]) == ("run", True)
    assert staged(config)["steps"] == []


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


def test_the_driver_waits_only_for_the_steps_the_database_run_holds():
    from edgar_warehouse.rules.driving import run_steps

    assert [step["name"] for step in run_steps(by_the_unit("openfigi"), "mastering")] == ["prepare", "merge", "processed"]
    unmarked = by_the_unit("sec.nport.registrant")
    assert [s["name"] for s in run_steps(unmarked, "mastering")] == [
        s["name"] for s in validate(unmarked, "mastering")["steps"]]


def test_company_mastering_held_by_the_unit_is_local_and_its_run_starts_at_records():
    config = validate(by_the_unit("sec.company"), "mastering")

    assert config["local"] is True
    assert [step["name"] for step in staged(config)["steps"]] == ["records", "merge", "processed"]


def test_a_target_at_grain_run_keeps_no_step_in_the_database_and_its_manifest_is_still_checked():
    """Bookkeeping holds the run's start and completion only: the run has no step and no unit, and the manifest
    is checked against the steps the loader will run."""
    from edgar_warehouse.bookkeeping.clean.config import worklist

    body = deepcopy(source("sec.nport.registrant"))
    config = staged(validate(body, "mastering"))

    assert config["steps"] == [] and config["loader_steps"]
    whole = {"version": 2, "steps": {step["name"]: [] for step in config["loader_steps"]}}
    with pytest.raises(Blocked, match="Zero work"):
        worklist(whole, config)  # checked as the loader will run it
    assert worklist(whole, {**config, "allow_zero_work": True}) == []
    with pytest.raises(Blocked, match="exactly the configured steps"):
        worklist({"version": 2, "steps": {}}, {**config, "allow_zero_work": True})


@pytest.mark.parametrize("change, message", [({"grain": "off"}, "grain is one of"), ({"grain": False}, "grain is one of"),
                                             ({"grain": "bundle"}, "grain is one of")])
def test_a_grain_is_unit_or_run(change, message):
    body = by_the_unit("sec.nport.registrant")
    body["bookkeeping"]["targets"]["mastering"].update(change)

    with pytest.raises(Blocked, match=message):
        validate(body, "mastering")


def test_a_target_that_names_no_grain_is_held_by_the_unit():
    config = validate(source("sec.nport.security"), "mastering")
    assert "grain" not in config
    assert staged(config)["steps"] == config["steps"]


def test_a_local_target_at_grain_run_keeps_the_manifest_it_was_given():
    """Its local steps are not run before the run starts: the run takes the whole manifest, and the loader runs
    every step after the run has started."""
    class Untouched:
        def json(self, ref):
            raise AssertionError("the manifest is not read before the run starts")

    assert local.staged_inputs(Untouched(), source("openfigi"), "mastering", REF) == REF
