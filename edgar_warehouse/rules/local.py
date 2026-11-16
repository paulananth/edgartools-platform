"""Run a target's source read and source combine steps in this process (ticket 210).

These steps turn captured files into extracts and write files with receipts. They need no claim, lease,
heartbeat, so they never reach the database: the content hash is their proof. Inputs resolve from
the receipts of earlier local units, through `compose_document`. A run in the database
then opens at the first step that writes the destination, with these receipts as its inputs."""
from __future__ import annotations

from collections import defaultdict

from edgar_warehouse.bookkeeping.clean.compose import compose_document
from edgar_warehouse.bookkeeping.clean.config import (LOCAL_OPERATIONS, STEP_CHECKS, Blocked, reference,
                                                     validate, worklist)


def staged_inputs(artifacts, export_body: dict, target: str, inputs: dict, modules: dict | None = None) -> dict:
    """The manifest reference a run takes. A target not marked `local` keeps the one it was given. A local
    target has its source read and combine steps run here, and the run takes the staged manifest."""
    config = validate(export_body, target)
    if not config.get("local") or config.get("grain") == "run":
        return inputs  # a target at grain `run` has every step run after the run has started (`work_run`)
    from edgar_warehouse.workers import profile

    manifest = artifacts.json(inputs)
    items = worklist(manifest, config)
    modules = modules or {operation: profile(operation) for operation in LOCAL_OPERATIONS}
    done = run_local(config["steps"], items, modules, artifacts)
    # Named by the input manifest's hash, so two bundles beside each other never write one address.
    return artifacts.put(inputs["uri"].rsplit("/", 1)[0] + "/staged-" + inputs["sha256"][:12],
                         stage_manifest(manifest, config["steps"], items, done, artifacts))


def work_run(book, run_id: str, modules: dict | None = None, *, workers: int = 1) -> dict:
    """Do the whole work of a run whose target is at grain `run`, then complete the run. Bookkeeping holds the
    run's start and completion only; every step runs here, in order, each unit checked by its own worker module.
    Safe to repeat on a stopped run: a written file is written again as the same file, and the Change Journal
    skips what it recorded. A step's units run `workers` at once, each in its own process."""
    run = book.status(run_id, limit=1)["run"]
    if run["state"] == "complete":
        return book.status(run_id)
    submission = run["submission"]
    export = book.artifacts.json(submission["rules"])
    config = validate(export["body"], submission["target"])
    if config.get("grain") != "run":
        raise Blocked("Only a target at grain `run` has its work done by the loader")
    from edgar_warehouse.control_contract import digest

    items = worklist(book.artifacts.json(submission["inputs"]), config)
    if modules is None:
        from edgar_warehouse.workers import profile

        modules = {operation: profile(operation) for operation in {step["operation"] for step in config["steps"]}}

    def claim(step: dict, item: dict) -> dict:
        return {"claim": {"run_id": run_id, "step": step["name"], "key": item["key"], "attempt": 1},
                "rules": submission["rules"], "ordinal": item["ordinal"],
                "effect_key": digest({"rules": submission["rules"], "step": step["name"], "key": item["key"],
                                      "unit": item["unit"]})}
    run_local(config["steps"], items, modules, book.artifacts, every=True, extra=claim, workers=workers)
    return book.finalize(run_id)


def _work(module, envelope: dict, artifacts, checked: bool) -> tuple[dict, list[str]]:
    """One unit's work and, for a step that writes a destination, its own check: the receipt and the checks that failed."""
    written = module.execute(envelope, artifacts)
    candidate = {"uri": written["uri"], "sha256": written["sha256"]}
    if not checked:
        return candidate, []
    checks, _ = module.check({**envelope, "candidate": candidate}, artifacts)
    return candidate, sorted(name for name, value in checks.items() if value is not True)


def _work_in_process(operation: str, envelope: dict, checked: bool) -> tuple[dict, list[str]]:
    """`_work` in a worker process of its own, which loads the operation's module and opens its own artifact store."""
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.workers import profile

    return _work(profile(operation), envelope, Artifacts(), checked)


def run_local(steps: list[dict], items: list[dict], modules: dict, artifacts, *, every: bool = False,
              extra=None, workers: int = 1) -> dict[tuple[str, str], dict]:
    """The receipt of every local unit, by (step, key). `steps` are the target's configured steps in order,
    `items` its worklist, `modules` the worker module of each local operation. With `every`, all the steps run
    here (a target at grain `run`): `extra(step, item)` adds what a worker reads of its run to the envelope, and
    a step that writes a destination checks its own result, as a worker does before it reports. A step's units
    depend only on earlier steps, so with `workers` above one they run that many at once, each in its own process
    (the operation's own module, loaded there). A step with fewer units than workers hands each unit its share
    as `processes`: a one-unit merge deals its batches out to them."""
    local = [step for step in steps if every or step["operation"] in LOCAL_OPERATIONS]
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
        ready = []
        for item in sorted(units[step["name"]], key=lambda unit: unit["ordinal"]):
            unit = item["unit"]
            cursor = unit["cursor"]
            if isinstance(cursor, dict) and cursor.get("generated_step") is not None:
                raise Blocked(f"Local step {step['name']} generates work; that is not run locally yet")
            envelope = {"input": _input(unit, receipt_of, artifacts), "output": unit["output"],
                        "checks": [name for name in step["checks"] if name not in STEP_CHECKS],
                        "keys": unit["keys"], "cursor": cursor}
            if extra is not None:
                envelope.update(extra(step, item))
            ready.append((item, envelope))
        for _, envelope in ready:  # the workers a step's units leave over, for a unit that splits its own work
            envelope["processes"] = max(1, workers // len(ready))
        checked = every and step["operation"] not in LOCAL_OPERATIONS
        if workers > 1 and len(ready) > 1:
            from concurrent.futures import ProcessPoolExecutor
            from multiprocessing import get_context

            with ProcessPoolExecutor(min(workers, len(ready)), mp_context=get_context("spawn")) as pool:
                results = list(pool.map(_work_in_process, [step["operation"]] * len(ready),
                                        [envelope for _, envelope in ready], [checked] * len(ready)))
        else:
            results = [_work(modules[step["operation"]], envelope, artifacts, checked) for _, envelope in ready]
        for (item, _), (candidate, failed) in zip(ready, results):
            if failed:
                raise Blocked(f"Step {step['name']} unit {item['key']}: check {', '.join(failed)} failed")
            done[(step["name"], item["key"])] = candidate
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
    if (isinstance(source, dict) and set(source) == {"from"} and "run" not in source["from"]
            and source["from"].get("step") in local):
        return _input(unit, lambda dependency: _receipt(done, dependency), artifacts)
    if isinstance(source, dict) and set(source) == {"compose"}:
        slots = _compose_steps(source["compose"])
        if slots & local and slots - local:
            raise Blocked("A composed input mixes local and database units")
        if slots & local:
            return _input(unit, lambda dependency: _receipt(done, dependency), artifacts)
    return source


OTHER_RUN = "<another run>"  # a unit of another run is never a local unit of this one


def _compose_steps(body: dict) -> set:
    found = set()
    for value in body["slots"].values():
        if isinstance(value, list):
            found |= {OTHER_RUN if "run" in dependency else dependency["step"] for dependency in value}
        elif set(value) == {"compose"}:
            found |= _compose_steps(value["compose"])
        else:
            found.add(OTHER_RUN if "run" in value else value["step"])
    return found


def _receipt(done: dict, dependency: dict) -> dict:
    found = done.get((dependency["step"], dependency["key"]))
    if found is None:
        raise Blocked("Prerequisite input lacks a finished local unit")
    return found
