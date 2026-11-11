"""Source read and source combine run in the loader's own process (ticket 210): no claim, lease, heartbeat,
verifier or database. The runner resolves each unit's input from the receipts of earlier units, calls the
worker module's `execute` with the three fields it reads, and returns every unit's receipt."""
import pytest

from edgar_warehouse.control_contract import Blocked
from edgar_warehouse.rules import local

REF = {"uri": "file:///captured/a.json", "sha256": "a" * 64}


class Store:
    """Artifacts double: names each document by its position, so the test sees what was placed."""

    def __init__(self):
        self.placed = []

    def put(self, root, document):
        self.placed.append((root, document))
        return {"uri": f"{root}/{len(self.placed)}", "sha256": f"{len(self.placed):064d}"}


class Module:
    def __init__(self, name):
        self.name, self.calls = name, []

    def execute(self, envelope, artifacts):
        self.calls.append(envelope)
        return {"uri": envelope["output"], "sha256": ("%s" % len(self.calls)).rjust(64, "0")}


def step(name, operation, requires=(), checks=("input.hash", "output.receipt", "source.output")):
    return {"name": name, "operation": operation, "requires": list(requires), "checks": list(checks)}


def item(step_name, key, input, ordinal=0):
    return {"step": step_name, "key": key, "ordinal": ordinal,
            "unit": {"keys": [key], "input": input, "output": f"file:///out/{step_name}/{key}.json", "cursor": {}}}


def test_each_local_step_runs_in_order_with_its_input_resolved_from_earlier_receipts():
    read, combine = Module("read"), Module("combine")
    steps = [step("read", "source.read"), step("combine", "source.combine", ["read"]),
             step("prepare", "mdm.prepare", ["combine"])]
    items = [item("read", "one", REF), item("combine", "all", {"compose": {
                 "slots": {"reads": [{"step": "read", "key": "one"}]},
                 "document": {"reads": {"slot": "reads"}}}}),
             item("prepare", "p", {"from": {"step": "combine", "key": "all"}})]

    store = Store()
    done = local.run_local(steps, items, {"source.read": read, "source.combine": combine}, store)

    assert set(done) == {("read", "one"), ("combine", "all")}  # the database steps are not run here
    assert read.calls[0]["input"] == REF
    assert read.calls[0]["output"] == "file:///out/read/one.json"
    assert read.calls[0]["checks"] == ["source.output"]  # the engine's own checks are not the worker's
    root, document = store.placed[0]
    assert root == "file:///out/combine/inputs"
    assert document == {"reads": [done[("read", "one")]]}  # the combine reads the read's receipt
    assert combine.calls[0]["input"]["uri"].startswith("file:///out/combine/inputs/")
    assert done[("read", "one")] == {"uri": "file:///out/read/one.json", "sha256": "1".rjust(64, "0")}


def test_a_local_step_that_requires_a_database_step_is_refused():
    steps = [step("prepare", "mdm.prepare"), step("read", "source.read", ["prepare"])]

    with pytest.raises(Blocked, match="requires"):
        local.run_local(steps, [item("read", "one", REF)], {"source.read": Module("read")}, Store())


def test_a_local_step_that_generates_more_work_is_refused_until_a_source_needs_it():
    steps = [step("read", "source.read")]
    generating = item("read", "one", REF)
    generating["unit"]["cursor"] = {"generated_step": "answers"}

    with pytest.raises(Blocked, match="generates work"):
        local.run_local(steps, [generating], {"source.read": Module("read")}, Store())
