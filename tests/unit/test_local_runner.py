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

    def read(self, uri):
        raise Blocked(f"Artifact missing or unreadable: {uri}")  # nothing was written before


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


def test_a_steps_units_run_several_at_once_each_in_its_own_process_and_give_the_same_receipts(tmp_path):
    """With workers above one, the units of a step run in worker processes that load the operation's own module:
    every unit is done, checked, and its receipt is the one a single worker gives."""
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.workers import copy

    artifacts = Artifacts()
    steps = [{"name": "copy", "operation": "artifact.copy", "requires": [], "checks": ["output.matches"]},
             {"name": "again", "operation": "artifact.copy", "requires": ["copy"], "checks": ["output.matches"]}]
    items = []
    for n in range(4):
        source = artifacts.put(tmp_path.as_uri() + "/in", {"n": n})
        items.append({"step": "copy", "key": str(n), "ordinal": n, "unit": {
            "keys": {"id": str(n)}, "input": source, "output": (tmp_path / f"copy-{n}").as_uri(), "cursor": {}}})
        items.append({"step": "again", "key": str(n), "ordinal": n, "unit": {
            "keys": {"id": str(n)}, "input": {"from": {"step": "copy", "key": str(n)}},
            "output": (tmp_path / f"again-{n}").as_uri(), "cursor": {}}})
    modules = {"artifact.copy": copy}

    several = local.run_local(steps, items, modules, artifacts, every=True, workers=3)
    one = local.run_local(steps, items, modules, artifacts, every=True)

    assert several == one and len(several) == 8
    assert all((tmp_path / f"again-{n}").exists() for n in range(4))


def test_a_step_of_one_unit_hands_the_unit_every_worker():
    """A step with fewer units than workers gives each unit the workers left over, so a one-unit merge
    (a whole GLEIF publication) splits its own batches across them."""
    module = Module("merge")
    steps = [{"name": "merge", "operation": "source.read", "requires": [], "checks": []}]
    items = [{"step": "merge", "key": "only", "ordinal": 0, "unit": {
        "keys": {"id": "only"}, "input": REF, "output": "file:///out/only", "cursor": {}}}]

    local.run_local(steps, items, {"source.read": module}, Store(), every=True, workers=8)
    local.run_local(steps, items, {"source.read": module}, Store(), every=True)

    assert [call["processes"] for call in module.calls] == [8, 1]


def test_a_stopped_run_worked_again_does_not_read_again_what_it_wrote(tmp_path):
    """The reads of a stopped run are kept: a restart does the steps after them only, with the same receipts."""
    import hashlib

    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts

    artifacts = Artifacts()

    class Writing:
        def __init__(self):
            self.calls = []

        def execute(self, envelope, store):
            self.calls.append(envelope["output"])
            return store.put_bytes(envelope["output"], repr(sorted(envelope["input"].items())).encode())

        def check(self, envelope, store):
            return {name: True for name in envelope["checks"]}, []

    read, merge = Writing(), Writing()
    steps = [{"name": "read", "operation": "source.read", "requires": [], "checks": []},
             {"name": "merge", "operation": "mastering.merge", "requires": ["read"], "checks": ["mdm.committed"]}]
    items = [{"step": "read", "key": str(n), "ordinal": n, "unit": {
                  "keys": {"id": str(n)}, "input": REF, "output": (tmp_path / f"read-{n}").as_uri(), "cursor": {}}}
             for n in range(3)]
    items.append({"step": "merge", "key": "all", "ordinal": 0, "unit": {
        "keys": {"id": "all"}, "input": {"from": {"step": "read", "key": "0"}},
        "output": (tmp_path / "merge").as_uri(), "cursor": {}}})
    modules = {"source.read": read, "mastering.merge": merge}

    first = local.run_local(steps, items, modules, artifacts, every=True)
    (tmp_path / "read-2").unlink()  # the run stopped before its last read was written
    second = local.run_local(steps, items, modules, artifacts, every=True)

    assert len(read.calls) == 4 and read.calls[3] == (tmp_path / "read-2").as_uri()  # only the missing read again
    assert len(merge.calls) == 2  # a step that writes a destination is always done again; the destination skips
    assert second == first
    assert first[("read", "0")]["sha256"] == hashlib.sha256((tmp_path / "read-0").read_bytes()).hexdigest()


def test_a_run_held_by_the_unit_stages_every_local_read_as_before():
    read = Module("read")
    steps = [step("read", "source.read")]
    local.run_local(steps, [item("read", "one", REF)], {"source.read": read}, Store())
    local.run_local(steps, [item("read", "one", REF)], {"source.read": read}, Store())
    assert len(read.calls) == 2



class Extracting:
    """A read or combine that writes its unit's extract, and counts its calls."""

    def __init__(self):
        self.calls = []

    def execute(self, envelope, store):
        self.calls.append(envelope["output"])
        return store.put_bytes(envelope["output"], ("extract of " + envelope["keys"]["unit"]).encode())


def target_of(tmp_path, name, artifacts, *, context="first"):
    """One target's read and combine over the same captured file, its inputs and outputs in its own folder."""
    captured = artifacts.put_bytes((tmp_path / "captured.json").as_uri(), b"{}")
    contract = artifacts.put((tmp_path / name / "inputs").as_uri(), {"read": "the same rules"})
    request = artifacts.put((tmp_path / name / "inputs").as_uri(), {
        "contract": contract, "artifacts": [{"input": captured}], "context": context})
    steps = [{"name": "read", "operation": "source.read", "requires": [], "checks": []},
             {"name": "combine", "operation": "source.combine", "requires": ["read"], "checks": []}]
    items = [{"step": "read", "key": "one", "ordinal": 0, "unit": {
                  "keys": {"unit": "one", "destination": (tmp_path / name / "read").as_uri()}, "input": request,
                  "output": (tmp_path / name / "read").as_uri(), "cursor": {}}},
             {"step": "combine", "key": "all", "ordinal": 0, "unit": {
                  "keys": {"unit": "all", "destination": (tmp_path / name / "combine").as_uri()},
                  "input": {"from": {"step": "read", "key": "one"}},
                  "output": (tmp_path / name / "combine").as_uri(), "cursor": {}}}]
    return steps, items


def worked(tmp_path, name, module, runtime="code-1", **options):
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts

    artifacts = Artifacts()
    steps, items = target_of(tmp_path, name, artifacts, **options)
    extracts = local.Extracts(tmp_path / "extracts", {"source.read": runtime, "source.combine": runtime}, artifacts)
    return local.run_local(steps, items, {"source.read": module, "source.combine": module}, artifacts, every=True,
                           extracts=extracts)


def test_a_second_target_takes_the_extracts_another_target_wrote_from_the_same_content(tmp_path):
    """Two targets of a source that read the same files with the same rules read them once: the second target's
    run does no read and no combine, and its later steps get the first target's receipts."""
    module = Extracting()

    first = worked(tmp_path, "mastering", module)
    second = worked(tmp_path, "silver", module)

    assert module.calls == [(tmp_path / "mastering" / "read").as_uri(), (tmp_path / "mastering" / "combine").as_uri()]
    assert second == first and not (tmp_path / "silver" / "read").exists()


@pytest.mark.parametrize("change", ["context", "code", "file gone", "file changed"])
def test_an_extract_is_made_again_when_what_made_it_differs_or_its_file_is_not_as_written(tmp_path, change):
    module = Extracting()
    worked(tmp_path, "mastering", module)
    if change == "file gone":
        (tmp_path / "mastering" / "read").unlink()
    if change == "file changed":
        (tmp_path / "mastering" / "read").write_bytes(b"other")

    worked(tmp_path, "silver", module, runtime="code-2" if change == "code" else "code-1",
           context="other" if change == "context" else "first")

    assert (tmp_path / "silver" / "read").as_uri() in module.calls  # read again, into its own folder
