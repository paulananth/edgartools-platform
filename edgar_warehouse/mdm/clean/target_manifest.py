"""A declared target's input manifest, from the target itself (ticket 14, slice 2).

A source's Bookkeeping section version 2 says, per step, how its units are
formed (`units`) and what each unit's input names (`input`); this one writer
turns that into the version-2 input manifest Bookkeeping runs, so a source
needs no writer of its own. It checks a bundle of captured documents against
the capture's receipts, names only those the Change Journal does not record
as processed under this source's rules (ticket 22; `force` names every one),
and freezes every unit's input. Each step by its operation:

- `source.read`: the bundle's documents, cut by `units` and read with the
  step's `contract` (default `source.yaml`), or a combine's pieces
  (`read_units`);
- `source.combine`: one unit, the step's contract over the readings it names;
- `mdm.prepare`: the readings its `input.readings` names, as one publication,
  with its `input.keys` (`table`, `record_column`, `dataset`);
- `mdm.merge`: the preparation's manifest through the Merge Stage;
- `journal.record`: each document the run processed, once its merge is verified.

Nothing here names a source or a kind.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import run_inputs, validate
from edgar_warehouse.rules import files as rules_files
from . import changed_files, raw_capture, read_units
from .evidence import instant
from .raw_capture import read_bounded
from .store import digest

DOCUMENTS_BYTES = 1024**2
RUN_FILE_BYTES = 256 * 1024**2  # a run file is JSON: a scope, a lookup set


@dataclass(frozen=True)
class _Run:
    """What every step's units are formed from: the checked bundle and the publication."""

    source: str
    reading: dict
    folder: Path
    receipts: dict
    rows: dict
    companions: dict
    keys: list
    sized: list
    limit: int
    keys_of: dict
    policy: str
    processing: str
    force: bool
    publication: dict
    contracts: dict
    by_name: dict
    store: Artifacts
    root: str
    inputs: str
    facts: dict
    run_files: dict




def plan(reading: dict, target: str) -> list[dict]:
    """The target's steps as written, each checked by Bookkeeping's own rules."""
    body = reading.get("bookkeeping") or {}
    if body.get("version") != 2:
        raise ValueError("The source's Bookkeeping section must be version 2: each step's units and input")
    validate(reading, target)
    steps = body["targets"][target]["steps"]
    unknown = sorted({step["operation"] for step in steps} - set(OPERATIONS))
    if unknown:
        raise ValueError(f"The writer does not yet form units for {', '.join(unknown)}")
    return steps


def by_name_of(steps: list[dict]) -> dict:
    return {step["name"]: step for step in steps}


_contract = read_units.contract_of


def _prepared_shape(by_name: dict, prepare: dict, keys_of: dict, contracts: dict) -> None:
    """The table and record column the preparation reads are ones the reading it
    reads declares: one column holding the record."""
    readings = prepare.get("input", {}).get("readings", {})
    producer = by_name.get(next(iter(readings.values()), {}).get("all", ""), {})
    if producer.get("operation") != "source.read":
        raise ValueError("The preparation reads the units of one source.read step")
    contract = contracts[_contract(producer)]
    columns = (((contract.get("read") or {}).get("tables") or {}).get(keys_of["table"]) or {}).get("columns") or {}
    if keys_of["record_column"] not in columns:
        raise ValueError(f"The preparation's table {keys_of['table']!r} and column {keys_of['record_column']!r} "
                         "are not declared by the reading it reads")


def _read(step: dict, run: _Run, units: dict) -> list[dict]:
    """The step's documents cut into units, each read with the step's contract (`read_units`)."""
    return read_units.form(step, run, units)


def _combine(step: dict, run: _Run, units: dict) -> list[dict]:
    """One unit: the step's contract over the readings it names, each a list of units or one unit."""
    name, shape = step["name"], step.get("input", {})
    readings, slots = shape.get("readings", {}), {}
    if not readings:
        raise ValueError(f"Step {name}: a combine names its readings")
    for slot, named in readings.items():
        if "all" in named:
            slots[slot] = [{"step": named["all"], "key": u["keys"]["unit"]} for u in units[named["all"]]]
        elif len(units[named["step"]]) != 1:
            raise ValueError(f"Step {name}: {{step: {named['step']}}} names a step of one unit; use {{all: ...}}")
        else:
            slots[slot] = {"step": named["step"], "key": units[named["step"]][0]["keys"]["unit"]}
    contract = run.store.put(run.inputs, run.contracts[_contract(step)])
    return [read_units.unit(f"{run.root}/{name}/combined.json", {"unit": name}, {"compose": {
        "document": {"version": 1, "contract": contract, "readings": {slot: {"slot": slot} for slot in slots}},
        "slots": slots}})]


def _prepare(step: dict, run: _Run, units: dict) -> list[dict]:
    """One unit: every reading of the step it names, as one publication."""
    name, readings = step["name"], step.get("input", {}).get("readings", {})
    if len(readings) != 1 or set(next(iter(readings.values()))) != {"all"}:
        raise ValueError(f"Step {name}: preparation reads every unit of one step: readings {{<name>: {{all: <step>}}}}")
    ((slot, named),) = readings.items()
    publication = run.publication
    return [read_units.unit(f"{run.root}/{name}/manifest.json", {
        "unit": name, **run.keys_of, "policy": run.policy, "consumer": publication["consumer"],
        "batch_id": publication["batch_id"], "as_of": publication["as_of"],
        "publication_key": publication["publication_key"], "revision": str(publication["revision"])}, {"compose": {
            "document": {"version": 1, "readings": {"slot": slot}},
            "slots": {slot: [{"step": named["all"], "key": unit["keys"]["unit"]} for unit in units[named["all"]]]}}})]


def _merge(step: dict, run: _Run, units: dict) -> list[dict]:
    """One unit: the preparation's manifest through the Merge Stage."""
    if len(step["requires"]) != 1 or run.by_name[step["requires"][0]]["operation"] != "mdm.prepare":
        raise ValueError(f"Step {step['name']}: a merge follows the one preparation step")
    (before,) = step["requires"]
    return [{"keys": {"batch_id": run.publication["batch_id"], "consumer": run.publication["consumer"]},
             "input": {"from": {"step": before, "key": units[before][0]["keys"]["unit"]}},
             "output": f"{run.root}/{step['name']}.json", "cursor": {}}]


def _record(step: dict, run: _Run, units: dict) -> list[dict]:
    """One unit: each document the run processed, for the Change Journal."""
    return [read_units.unit(f"{run.root}/{step['name']}.json", {"unit": step["name"]}, run.store.put(
        run.inputs, changed_files.record_input(
            source=run.source, feed=run.reading["bronze"]["family"], processing=run.processing, forced=run.force,
            as_of=run.publication["as_of"], files=[
                *({"key": key, **raw_capture.document(run.folder, run.receipts, key)} for key in run.keys),
                *({"key": other, **raw_capture.verified(run.folder, other, sha256)[0]}
                  for key in run.keys for other, sha256 in run.companions[key])])))]


# Each operation's units, from the step, the run and the units of the steps before it.
FORMS = {"source.read": _read, "source.combine": _combine, "mdm.prepare": _prepare, "mdm.merge": _merge, "journal.record": _record}
OPERATIONS = tuple(FORMS)


def run_arguments(facts: list[str] | None, run_files: list[str] | None) -> tuple[dict, dict]:
    """`--fact name=value` (a JSON value, else text) and `--file name=path`, as two maps."""
    def pairs(items):
        found = {}
        for item in items or []:
            name, sep, value = item.partition("=")
            if not sep or not name or name in found:
                raise ValueError(f"A run input is name=value, each name once: {item!r}")
            found[name] = value
        return found
    parsed = {}
    for name, value in pairs(facts).items():
        try:
            parsed[name] = json.loads(value)
        except json.JSONDecodeError:
            parsed[name] = value
    return parsed, pairs(run_files)


def write_manifest(
    *,
    source: str,
    target: str,
    capture: str,
    documents: str,
    capture_run: str,
    output: str,
    as_of: str,
    revision: int,
    force: bool = False,
    journal=None,
    facts: dict | None = None,
    run_files: dict | None = None,
) -> dict:
    """The input manifest of `target` for one bundle of captured documents.

    `documents` lists the bundle's documents by receipt key (at most the
    source's `execution.max_artifacts`; each step's worker bounds what it
    reads). `capture_run` is the caller's approved run ID of the capture.
    Returns the report: the manifest's reference (none when every document was
    processed already) and the publication."""
    if type(revision) is not int or revision < 0:
        raise ValueError("Require a nonnegative explicit publication revision")
    instant(as_of)
    if source not in {p.name for p in (rules_files.ROOT / "sources").iterdir() if p.is_dir()}:
        raise ValueError(f"No source named {source!r} under rules/sources")
    reading = rules_files.source(source)
    if target not in ((reading.get("bookkeeping") or {}).get("targets") or {}):
        raise ValueError(f"The source declares no `{target}` target")
    steps = plan(reading, target)
    # The run's own inputs, exactly as the target declares them (`run`): facts and files.
    declared = run_inputs(reading["bookkeeping"]["targets"][target])
    facts, run_files = dict(facts or {}), dict(run_files or {})
    if set(facts) != set(declared["facts"]) or set(run_files) != set(declared["files"]):
        raise ValueError(f"The target's run takes facts {declared['facts']} and files {declared['files']}")
    loaded = {}
    for name, path in run_files.items():
        try:
            loaded[name] = json.loads(read_bounded(Path(path).resolve(), RUN_FILE_BYTES))
        except (OSError, ValueError) as error:  # missing, a folder, too large, or not JSON
            raise ValueError(f"Run file {name} ({path}) is not a readable JSON file: {error}") from None
    shared = [*({"name": f"file:{name}", "sha256": digest(value)} for name, value in sorted(loaded.items())),
              *({"name": f"fact:{name}", "sha256": digest(value)} for name, value in sorted(facts.items()))]
    prepare = [step for step in steps if step["operation"] == "mdm.prepare"]
    if len(prepare) != 1:
        raise ValueError("A target prepares one publication: exactly one mdm.prepare step")
    keys_of = prepare[0].get("input", {}).get("keys", {})
    if set(keys_of) != {"table", "record_column", "dataset"} or keys_of["dataset"] not in (reading.get("mdm") or {}):
        raise ValueError("The mdm.prepare step's keys name its table, record column and one of the source's datasets")
    for step in steps:
        if step["operation"] != "source.read" and "units" in step:
            raise ValueError(f"Step {step['name']}: only a read declares its units")
    dataset = keys_of["dataset"]
    # Each contract the steps read with, loaded once: what is frozen is what the ids digest.
    contracts = {name: rules_files.load(rules_files.ROOT / "sources" / source / name)
                 for name in sorted({_contract(step) for step in steps
                                     if step["operation"] == "source.read" or "contract" in step.get("input", {})})}
    by_name = by_name_of(steps)
    _prepared_shape(by_name, prepare[0], keys_of, contracts)
    limit = reading["execution"]["max_artifacts"]
    folder = Path(capture).resolve()
    receipts_raw, receipts = raw_capture.receipts(folder)
    rows = raw_capture.rows(receipts_raw)
    keys = json.loads(read_bounded(Path(documents).resolve(), DOCUMENTS_BYTES))
    if (not isinstance(keys, list) or not 1 <= len(keys) <= limit
            or len(set(keys)) != len(keys) or any(not isinstance(key, str) for key in keys)):
        raise ValueError(f"A bundle names 1..{limit} distinct documents")
    keys = sorted(keys)  # a bundle is its documents, in key order, however they are listed
    # A document and the companions read beside it are selected as one: kept when any of them is not processed.
    paired = {key: read_units.companions(steps, rows, key) for key in keys}
    files = [(key, raw_capture.document(folder, receipts, key)["sha256"]) for key in keys]
    files += [pair for key in keys for pair in paired[key]]
    policy = digest(rules_files.policy())
    processing = changed_files.identity(changed_files.source_rules(source), policy, shared)
    fresh = set(changed_files.select(source, processing, files, force=force, ledger=journal))
    listed, keys = len(keys), [key for key in keys if key in fresh or any(o in fresh for o, _ in paired[key])]
    scope = {"documents": len(keys), "listed": listed, "receipts_sha256": hashlib.sha256(receipts_raw).hexdigest(),
             "capture_run_id": capture_run, "processing_identity": processing, "forced": force}
    if not keys:  # every document is processed already: no run
        return {"source": source, "source_code": dataset, "target": target, "manifest": None,
                "publication": None, "policy_digest": policy, "scope": scope}
    # Each document equal to its receipt before it is frozen; its size cuts the read units.
    sized = [(key, len(raw_capture.document_bytes(folder, receipts, key))) for key in keys]
    # The publication is the documents themselves (key and receipt), not the
    # list file's bytes: the same documents are one publication.
    documents_hash = digest([[key, receipts[key], *paired[key]] for key in keys])
    publication_key = f"{capture_run}:{source}:{documents_hash}"
    # The consumer and batch ids name what shapes the records (every contract
    # the steps read with, the Dataset Contracts, the policy): a rerun under
    # other rules or another time is a new consumer, not a reused batch key.
    # A contract is digested whole, so an edit to its steps' units is one too.
    bundle = digest([publication_key, revision, as_of, contracts, reading["mdm"], policy,
                     *([shared] if shared else [])])
    publication = {"publication_key": publication_key, "revision": revision, "as_of": as_of,
                   "consumer": f"{dataset}/{bundle}", "batch_id": f"{source}:{bundle}"}
    root = Path(output).resolve().as_uri()
    run = _Run(source=source, reading=reading, folder=folder, receipts=receipts, rows=rows, companions=paired, keys=keys, sized=sized, limit=limit,
               keys_of=keys_of, policy=policy, processing=processing, force=force, publication=publication, contracts=contracts, by_name=by_name, store=Artifacts(), root=root,
               inputs=root + "/inputs", facts=facts, run_files=loaded)
    units: dict[str, list[dict]] = {}
    for step in steps:
        units[step["name"]] = FORMS[step["operation"]](step, run, units)
    manifest = run.store.put(root, {"version": 2, "steps": units})
    return {"source": source, "source_code": dataset, "target": target, "manifest": manifest,
            "publication": publication, "policy_digest": policy, "scope": scope}
