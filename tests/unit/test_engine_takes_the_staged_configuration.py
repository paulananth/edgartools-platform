"""A run of a target marked `local` holds only the steps after the local ones: the engine takes the staged
configuration wherever it reads a target's configuration (ticket 210)."""
from edgar_warehouse.bookkeeping.clean import engine as engine_module
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping

STEPS = [
    {"name": "read", "operation": "source.read", "requires": [], "checks": ["x"]},
    {"name": "combine", "operation": "source.combine", "requires": ["read"], "checks": ["x"]},
    {"name": "prepare", "operation": "mdm.prepare", "requires": ["combine"], "checks": ["x"]},
]


def book(monkeypatch, local):
    reads = []

    class Artifacts:
        def json(self, ref):
            reads.append(ref)
            return {"body": {}, "digest": "d", "kind": "k", "name": "n", "version": "v"} if ref == "rules" else {}

    monkeypatch.setattr(engine_module, "digest", lambda value: "d" if value == {} else "s")
    monkeypatch.setattr(engine_module, "validate", lambda body, target: {"local": local, "steps": [dict(s) for s in STEPS]})
    monkeypatch.setattr(engine_module, "worklist", lambda manifest, config: [{"step": "prepare", "key": "1"}])
    result = Bookkeeping.__new__(Bookkeeping)
    result.artifacts, result._frozen_static = Artifacts(), {}
    return result


SUBMISSION = {"rules": "rules", "inputs": "inputs", "kind": "k", "name": "n", "rule_version": "v", "target": "t",
              "profiles": {"read": "source.read", "combine": "source.combine", "prepare": "mdm.prepare"},
              "worklist_hash": "s", "scope": {}}


def test_a_local_target_runs_only_its_database_steps(monkeypatch):
    # The submission names the profiles of the steps it runs; a staged run names only the database step.
    submission = {**SUBMISSION, "profiles": {"prepare": "mdm.prepare"}}

    _, config, _, _ = book(monkeypatch, True)._static(submission)

    assert [step["name"] for step in config["steps"]] == ["prepare"]
    assert config["steps"][0]["requires"] == []


def test_a_target_not_marked_local_runs_all_its_steps(monkeypatch):
    _, config, _, _ = book(monkeypatch, False)._static(SUBMISSION)

    assert [step["name"] for step in config["steps"]] == ["read", "combine", "prepare"]
