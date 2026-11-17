"""Do the work of a run at grain `run` in this process: every step in order, each unit checked by its worker module.

A source read or combine turns captured files into extracts and writes files with receipts; it needs no claim,
lease or heartbeat, and its content hash is its proof. Inputs resolve from the receipts of earlier units, through
`compose_document`."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

from edgar_warehouse.bookkeeping.clean.compose import compose_document
from edgar_warehouse.bookkeeping.clean.config import (LOCAL_OPERATIONS, STEP_CHECKS, Blocked, reference,
                                                     validate, worklist)


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
    run_local(config["steps"], items, modules, book.artifacts, every=True, extra=claim, workers=workers,
              extracts=Extracts.of_the_stores(book.artifacts, modules))
    return book.finalize(run_id)


class Extracts:
    """The extracts written under one stores' manifest root, each found by what made it: the operation, its worker
    code, and the content of everything it read (the rules it read with, each file, each value it was given). Two
    targets of a source that read the same files the same way then read them once: the second takes the first's
    receipt. Where a file sits is no part of it, so only content decides. An extract whose file is gone or changed
    is made again."""

    def __init__(self, folder: Path, runtimes: dict[str, str], artifacts):
        self.folder, self.runtimes, self.artifacts = folder, runtimes, artifacts

    @classmethod
    def of_the_stores(cls, artifacts, modules: dict) -> "Extracts | None":
        from edgar_warehouse.workers.__main__ import runtime

        root = urlparse(os.environ.get("BOOKKEEPING_MANIFEST_ROOT") or "")
        extracting = {operation: module for operation, module in modules.items() if operation in LOCAL_OPERATIONS}
        if (root.scheme not in ("", "file") or not root.path
                or any(not hasattr(module, "__file__") for module in extracting.values())):
            return None  # no local folder to keep them under, or code with no file to know it by
        return cls(Path(unquote(root.path)) / "extracts",
                   {operation: runtime(module) for operation, module in extracting.items()}, artifacts)

    def _file(self, step: dict, envelope: dict) -> Path:
        from edgar_warehouse.control_contract import digest

        # An input taken whole from an earlier unit is that extract, known by its hash; any other input is the
        # small document that names what the unit reads.
        given = envelope["input"]["sha256"] if envelope["whole"] else _content(self.artifacts.json(envelope["input"]))
        return self.folder / (digest({
            "operation": step["operation"], "runtime": self.runtimes[step["operation"]],
            "input": given, "whole": envelope["whole"], "cursor": envelope["cursor"],
            "keys": {name: value for name, value in envelope["keys"].items() if name != "destination"}}) + ".json")

    def kept(self, step: dict, envelope: dict) -> dict | None:
        """The receipt of this unit's extract when one is written and still reads as it was written."""
        try:
            held = json.loads(self._file(step, envelope).read_text())
        except (OSError, ValueError):
            return None
        found = _written(self.artifacts, held["uri"])
        return found if found == held else None

    def keep(self, step: dict, envelope: dict, receipt: dict) -> None:
        file = self._file(step, envelope)
        file.parent.mkdir(parents=True, exist_ok=True)
        staged = file.with_name(f".{file.name}.{os.getpid()}")
        staged.write_text(json.dumps(receipt, sort_keys=True))
        os.replace(staged, file)


def _whole(item: dict) -> bool:
    source = item["unit"]["input"]
    return isinstance(source, dict) and set(source) == {"from"}


def _content(value):
    """A document with each file it names given by its content alone: `{uri, sha256}` becomes the hash."""
    if isinstance(value, dict):
        if set(value) == {"uri", "sha256"}:
            return value["sha256"]
        return {name: _content(inner) for name, inner in value.items()}
    return [_content(inner) for inner in value] if isinstance(value, list) else value


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
              extra=None, workers: int = 1, extracts: "Extracts | None" = None) -> dict[tuple[str, str], dict]:
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
        if every and not checked:
            # A stopped run worked again: a read or a combine whose output is written is not done again. Its output
            # is written whole or not at all and never replaced, and the same run gives the same unit the same input.
            # Nor is one another target of the stores wrote from the same content with the same rules and code.
            for item, envelope in ready:
                kept = _written(artifacts, envelope["output"])
                if kept is None and extracts is not None:
                    kept = extracts.kept(step, {**envelope, "whole": _whole(item)})
                if kept is not None:
                    done[(step["name"], item["key"])] = kept
            ready = [(item, envelope) for item, envelope in ready if (step["name"], item["key"]) not in done]
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
        if extracts is not None and every and not checked:
            for item, envelope in ready:
                extracts.keep(step, {**envelope, "whole": _whole(item)}, done[(step["name"], item["key"])])
    return done


def _written(artifacts, uri: str) -> dict | None:
    """The receipt of an output already written, or none."""
    import hashlib

    try:
        data = artifacts.read(uri)
    except Blocked:
        return None
    return {"uri": uri, "sha256": hashlib.sha256(data).hexdigest()}


def _input(unit: dict, receipt_of, artifacts) -> dict:
    source = unit["input"]
    if isinstance(source, dict) and set(source) == {"from"}:
        return receipt_of(source["from"])
    if isinstance(source, dict) and set(source) == {"compose"}:
        # Beside the unit's output, named by content: a rerun writes the same object.
        root = unit["output"].rsplit("/", 1)[0] + "/inputs"
        return compose_document(source["compose"], receipt_of, lambda document: artifacts.put(root, document))
    return reference(source)


def _receipt(done: dict, dependency: dict) -> dict:
    found = done.get((dependency["step"], dependency["key"]))
    if found is None:
        raise Blocked("Prerequisite input lacks a finished local unit")
    return found
