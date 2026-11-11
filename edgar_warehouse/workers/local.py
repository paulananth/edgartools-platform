"""Run a target's source read and source combine steps in this process (ticket 210).

These steps turn captured files into extracts and write files with receipts. They need no claim, lease,
heartbeat or verifier, so they never reach the database: the content hash is their proof. Inputs resolve from
the receipts of earlier local units, through the same `compose_document` the engine uses. A run in the database
then opens at the first step that writes the destination, with these receipts as its inputs."""
from __future__ import annotations

from collections import defaultdict

from edgar_warehouse.bookkeeping.clean.compose import compose_document
from edgar_warehouse.bookkeeping.clean.config import STEP_CHECKS, Blocked, reference

LOCAL_OPERATIONS = frozenset({"source.read", "source.combine"})


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
        found = done.get((dependency["step"], dependency["key"]))
        if found is None:
            raise Blocked("Prerequisite input lacks a finished local unit")
        return found

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
