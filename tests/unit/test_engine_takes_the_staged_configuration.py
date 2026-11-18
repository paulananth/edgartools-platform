"""A run at grain `run` holds no step in the database (the loader does them all): the engine takes the staged
configuration wherever it reads a target's configuration."""
from edgar_warehouse.bookkeeping.clean import engine as engine_module
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping

STEPS = [
    {"name": "read", "operation": "source.read", "requires": [], "checks": ["x"]},
    {"name": "combine", "operation": "source.combine", "requires": ["read"], "checks": ["x"]},
    {"name": "prepare", "operation": "mdm.prepare", "requires": ["combine"], "checks": ["x"]},
]


def book(monkeypatch, grain):
    reads = []

    class Artifacts:
        def json(self, ref):
            reads.append(ref)
            return {"body": {}, "digest": "d", "kind": "k", "name": "n", "version": "v"} if ref == "rules" else {}

    monkeypatch.setattr(engine_module, "digest", lambda value: "d" if value == {} else "s")
    monkeypatch.setattr(engine_module, "validate", lambda body, target: {**({"grain": grain} if grain else {}), "steps": [dict(s) for s in STEPS]})
    monkeypatch.setattr(engine_module, "worklist", lambda manifest, config: [{"step": "prepare", "key": "1"}])
    result = Bookkeeping.__new__(Bookkeeping)
    result.artifacts, result._frozen_static = Artifacts(), {}
    return result


SUBMISSION = {"rules": "rules", "inputs": "inputs", "kind": "k", "name": "n", "rule_version": "v", "target": "t",
              "profiles": {"read": "source.read", "combine": "source.combine", "prepare": "mdm.prepare"},
              "worklist_hash": "s", "scope": {}}


def test_a_target_at_grain_run_holds_no_step_and_the_loader_has_them_all(monkeypatch):
    # The submission names the profiles of the steps the database holds: none at grain `run`.
    submission = {**SUBMISSION, "profiles": {}}

    _, config, _, _ = book(monkeypatch, "run")._static(submission)

    assert config["steps"] == []
    assert [step["name"] for step in config["loader_steps"]] == ["read", "combine", "prepare"]


def test_a_target_held_by_the_unit_runs_all_its_steps(monkeypatch):
    _, config, _, _ = book(monkeypatch, None)._static(SUBMISSION)

    assert [step["name"] for step in config["steps"]] == ["read", "combine", "prepare"]
