"""Run a target's source read and source combine steps in this process (ticket 210).

These steps turn captured files into extracts and write files with receipts. They need no claim, lease,
heartbeat or verifier, so they never reach the database: the content hash is their proof. Inputs resolve from
the receipts of earlier local units, through the same `compose_document` the engine uses. A run in the database
then opens at the first step that writes the destination, with these receipts as its inputs."""
from __future__ import annotations

from collections import defaultdict

from edgar_warehouse.bookkeeping.clean.compose import compose_document
from edgar_warehouse.bookkeeping.clean.config import LOCAL_OPERATIONS, STEP_CHECKS, Blocked, reference


def run_local(steps: list[dict], items: list[dict], modules: dict, artifacts) -> dict[tuple[str, str], dict]:
    """The receipt of every local unit, by (step, key). `steps` are the target's configured steps in order,
    `items` its worklist, `modules` the worker module of each local operation."""
    local = [step for step in steps if step["operation"] in LOCAL_OPERATIONS]
    names = {step["name"] for step in local}
    for step in local:
        if not set(step["requires"]) <= names:
            raise Blocked(f"Local step {step['name']} requires a step that runs in the database")
    units = defaultdict(list)
    for item in items:
        units[item["step"]].append(item)
    done: dict[tuple[str, str], dict] = {}

    def receipt_of(dependency: dict) -> dict:
        if "run" in dependency:
            raise Blocked("A local step reads only this run's local steps")
        return _receipt(done, dependency)

    for step in local:
        for item in sorted(units[step["name"]], key=lambda unit: unit["ordinal"]):
            unit = item["unit"]
            cursor = unit["cursor"]
            if isinstance(cursor, dict) and cursor.get("generated_step") is not None:
                raise Blocked(f"Local step {step['name']} generates work; that is not run locally yet")
            envelope = {"input": _input(unit, receipt_of, artifacts), "output": unit["output"],
                        "checks": [name for name in step["checks"] if name not in STEP_CHECKS],
                        "keys": unit["keys"], "cursor": cursor}
            written = modules[step["operation"]].execute(envelope, artifacts)
            done[(step["name"], item["key"])] = {"uri": written["uri"], "sha256": written["sha256"]}
    return done


def _input(unit: dict, receipt_of, artifacts) -> dict:
    source = unit["input"]
    if isinstance(source, dict) and set(source) == {"from"}:
        return receipt_of(source["from"])
    if isinstance(source, dict) and set(source) == {"compose"}:
        # Beside the unit's output, named by content: a rerun writes the same object.
        root = unit["output"].rsplit("/", 1)[0] + "/inputs"
        return compose_document(source["compose"], receipt_of, lambda document: artifacts.put(root, document))
    return reference(source)


def stage_manifest(manifest: dict, steps: list[dict], items: list[dict], done: dict, artifacts) -> dict:
    """The manifest of the run in the database: the steps after the local ones, each input that read a local
    unit now the receipt of that unit. An input on a database step stays as it is, and one composed from both
    kinds is refused. `artifacts` is only needed to place a composed document, which is all local."""
    local = {step["name"] for step in steps if step["operation"] in LOCAL_OPERATIONS}
    units = defaultdict(list)
    for item in items:
        units[item["step"]].append(item)
    result = {key: value for key, value in manifest.items() if key != "steps"}
    result["steps"] = {}
    for step in steps:
        if step["name"] in local:
            continue
        result["steps"][step["name"]] = [
            {**item["unit"], "input": _staged_input(item["unit"], local, done, artifacts)}
            for item in sorted(units[step["name"]], key=lambda unit: unit["ordinal"])]
    return result


def _staged_input(unit: dict, local: set, done: dict, artifacts):
    source = unit["input"]
    if isinstance(source, dict) and set(source) == {"from"} and source["from"].get("step") in local:
        return _input(unit, lambda dependency: _receipt(done, dependency), artifacts)
    if isinstance(source, dict) and set(source) == {"compose"}:
        slots = _compose_steps(source["compose"])
        if slots & local and slots - local:
            raise Blocked("A composed input mixes local and database units")
        if slots & local:
            return _input(unit, lambda dependency: _receipt(done, dependency), artifacts)
    return source


def _compose_steps(body: dict) -> set:
    found = set()
    for value in body["slots"].values():
        if isinstance(value, list):
            found |= {dependency["step"] for dependency in value}
        elif set(value) == {"compose"}:
            found |= _compose_steps(value["compose"])
        else:
            found.add(value["step"])
    return found


def _receipt(done: dict, dependency: dict) -> dict:
    found = done.get((dependency["step"], dependency["key"]))
    if found is None:
        raise Blocked("Prerequisite input lacks a finished local unit")
    return found
