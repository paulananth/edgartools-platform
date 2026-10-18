"""A declared target's input manifest, from the target itself (ticket 14, slice 2).

A source's Bookkeeping section version 2 says, per step, how its units are
formed (`units`) and what each unit's input names (`input`); this one writer
turns that into the version-2 input manifest Bookkeeping runs, so a source
needs no writer of its own. It checks a bundle of captured documents against
the capture's receipts, names only those the Change Journal does not record
as processed under this source's rules (ticket 22; `force` names every one),
and freezes every unit's input. Each step by its operation:

- `source.read`: the bundle's documents, cut by `units` (`slices` of at most N
  bytes, each at most the reading's `max_artifacts` documents), read with
  the step's `contract` (default `source.yaml`);
- `mdm.prepare`: the readings its `input.readings` names, as one publication,
  with its `input.keys` (`table`, `record_column`, `dataset`);
- `mdm.merge`: the preparation's manifest through the Merge Stage;
- `journal.record`: each document the run processed, once its merge is verified.

Nothing here names a source or a kind.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import validate
from edgar_warehouse.rules import files as rules_files
from . import changed_files, raw_capture
from .evidence import instant
from .raw_capture import read_bounded
from .store import digest

DOCUMENTS_BYTES = 1024**2
# One preparation reads the whole bundle, inside mdm.prepare's 32 MiB of
# readings; a reading kept whole is about its documents' size.
BUNDLE_BYTES = 24 * 1024**2
OPERATIONS = ("source.read", "mdm.prepare", "mdm.merge", "journal.record")


def _unit(output: str, keys: dict, source: dict) -> dict:
    return {"keys": {**keys, "destination": output}, "input": source, "output": output, "cursor": {}}


def _plan(reading: dict, target: str) -> list[dict]:
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


def _prepared_shape(source: str, by_name: dict, prepare: dict, keys_of: dict) -> None:
    """The table and record column the preparation reads are ones the reading it
    reads declares: one column holding the record."""
    readings = prepare.get("input", {}).get("readings", {})
    producer = by_name.get(next(iter(readings.values()), {}).get("all", ""), {})
    contract = rules_files.load(rules_files.ROOT / "sources" / source
                                / producer.get("input", {}).get("contract", "source.yaml"))
    columns = (((contract.get("read") or {}).get("tables") or {}).get(keys_of["table"]) or {}).get("columns") or {}
    if keys_of["record_column"] not in columns:
        raise ValueError(f"The preparation's table {keys_of['table']!r} and column {keys_of['record_column']!r} "
                         "are not declared by the reading it reads")


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
) -> dict:
    """The input manifest of `target` for one bundle of captured documents.

    `documents` lists the bundle's documents by receipt key (at most the
    source's `execution.max_artifacts`, and at most 24 MiB). `capture_run` is
    the caller's approved run ID of the capture. Returns the report: the
    manifest's reference (none when every document was processed already) and
    the publication."""
    if type(revision) is not int or revision < 0:
        raise ValueError("Require a nonnegative explicit publication revision")
    instant(as_of)
    if source not in {p.name for p in (rules_files.ROOT / "sources").iterdir() if p.is_dir()}:
        raise ValueError(f"No source named {source!r} under rules/sources")
    reading = rules_files.source(source)
    if target not in ((reading.get("bookkeeping") or {}).get("targets") or {}):
        raise ValueError(f"The source declares no `{target}` target")
    steps = _plan(reading, target)
    prepare = [step for step in steps if step["operation"] == "mdm.prepare"]
    if len(prepare) != 1:
        raise ValueError("A target prepares one publication: exactly one mdm.prepare step")
    keys_of = prepare[0].get("input", {}).get("keys", {})
    if set(keys_of) != {"table", "record_column", "dataset"} or keys_of["dataset"] not in (reading.get("mdm") or {}):
        raise ValueError("The mdm.prepare step's keys name its table, record column and one of the source's datasets")
    dataset = keys_of["dataset"]
    _prepared_shape(source, by_name_of(steps), prepare[0], keys_of)
    limit = reading["execution"]["max_artifacts"]
    folder = Path(capture).resolve()
    receipts_raw, receipts = raw_capture.receipts(folder)
    keys = json.loads(read_bounded(Path(documents).resolve(), DOCUMENTS_BYTES))
    if (not isinstance(keys, list) or not 1 <= len(keys) <= limit
            or len(set(keys)) != len(keys) or any(not isinstance(key, str) for key in keys)):
        raise ValueError(f"A bundle names 1..{limit} distinct documents")
    keys = sorted(keys)  # a bundle is its documents, in key order, however they are listed
    files = [(key, raw_capture.document(folder, receipts, key)["sha256"]) for key in keys]
    policy = digest(rules_files.policy())
    processing = changed_files.identity(changed_files.source_rules(source), policy)
    listed, keys = len(keys), changed_files.select(source, processing, files, force=force, ledger=journal)
    scope = {"documents": len(keys), "listed": listed, "receipts_sha256": hashlib.sha256(receipts_raw).hexdigest(),
             "capture_run_id": capture_run, "processing_identity": processing, "forced": force}
    if not keys:  # every document is processed already: no run
        return {"source": source, "source_code": dataset, "target": target, "manifest": None,
                "publication": None, "policy_digest": policy, "scope": scope}
    # Each document equal to its receipt before it is frozen; its size cuts the read units.
    sized = [(key, len(raw_capture.document_bytes(folder, receipts, key))) for key in keys]
    if sum(size for _, size in sized) > BUNDLE_BYTES:
        raise ValueError(f"A bundle's documents exceed {BUNDLE_BYTES} bytes; name fewer")
    # The publication is the documents themselves (key and receipt), not the
    # list file's bytes: the same documents are one publication.
    documents_hash = digest([[key, receipts[key]] for key in keys])
    publication_key = f"{capture_run}:{source}:{documents_hash}"
    # The consumer and batch ids name what shapes the records (the reading, the
    # contract with its quality rule, the policy): a rerun under other rules or
    # another time is a new consumer, not a reused batch key. The steps do not.
    bundle = digest([publication_key, revision, as_of, reading["read"], reading["mdm"], policy])
    publication = {"publication_key": publication_key, "revision": revision, "as_of": as_of,
                   "consumer": f"{dataset}/{bundle}", "batch_id": f"{source}:{bundle}"}
    store = Artifacts()
    root = Path(output).resolve().as_uri()
    inputs = root + "/inputs"
    units: dict[str, list[dict]] = {}
    by_name = by_name_of(steps)
    for step in steps:
        name, shape = step["name"], step.get("input", {})
        if step["operation"] != "source.read" and "units" in step:
            raise ValueError(f"Step {name}: only a read of captured documents forms units today")
        if step["operation"] == "source.read":
            plan = step.get("units", "one")
            if not isinstance(plan, dict) or "slices" not in plan:
                raise ValueError(f"Step {name}: a read of captured documents is cut into slices of bytes")
            contract = store.put(inputs, rules_files.load(
                rules_files.ROOT / "sources" / source / shape.get("contract", "source.yaml")))
            units[name], start = [], 0
            for unit in raw_capture.slices(sized, plan["slices"]["bytes"], limit):
                artifacts = [raw_capture.document(folder, receipts, key) for key in unit]
                units[name].append(_unit(f"{root}/{name}/{start}.reading.json", {"unit": f"{name}-{start}"},
                                         store.put(inputs, {"version": 1, "contract": contract,
                                                            "artifacts": artifacts})))
                start += len(unit)
        elif step["operation"] == "mdm.prepare":
            readings = shape.get("readings", {})
            if len(readings) != 1 or set(next(iter(readings.values()))) != {"all"}:
                raise ValueError(f"Step {name}: preparation reads every unit of one step: readings {{<name>: {{all: <step>}}}}")
            ((slot, named),) = readings.items()
            units[name] = [_unit(f"{root}/{name}/manifest.json", {
                "unit": name, **keys_of, "policy": policy, "consumer": publication["consumer"],
                "batch_id": publication["batch_id"], "as_of": as_of, "publication_key": publication_key,
                "revision": str(revision)}, {"compose": {
                    "document": {"version": 1, "readings": {"slot": slot}},
                    "slots": {slot: [{"step": named["all"], "key": unit["keys"]["unit"]}
                                     for unit in units[named["all"]]]}}})]
        elif step["operation"] == "mdm.merge":
            if len(step["requires"]) != 1 or by_name[step["requires"][0]]["operation"] != "mdm.prepare":
                raise ValueError(f"Step {name}: a merge follows the one preparation step")
            (before,) = step["requires"]
            units[name] = [{"keys": {"batch_id": publication["batch_id"], "consumer": publication["consumer"]},
                            "input": {"from": {"step": before, "key": units[before][0]["keys"]["unit"]}},
                            "output": f"{root}/{name}.json", "cursor": {}}]
        elif step["operation"] == "journal.record":
            units[name] = [_unit(f"{root}/{name}.json", {"unit": name}, store.put(inputs, changed_files.record_input(
                source=source, feed=reading["bronze"]["family"], processing=processing, forced=force, as_of=as_of,
                files=[{"key": key, **raw_capture.document(folder, receipts, key)} for key in keys])))]
        else:
            raise ValueError(f"Step {name}: the writer does not form units for {step['operation']}")
    manifest = store.put(root, {"version": 2, "steps": units})
    return {"source": source, "source_code": dataset, "target": target, "manifest": manifest,
            "publication": publication, "policy_digest": policy, "scope": scope}
