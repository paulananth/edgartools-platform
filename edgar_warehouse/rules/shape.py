"""The one shape of a load target: extract, master, silver, record.

A target in `source.yaml` says only what is its own:

    extract:   the passes over the source's files, by name and in order: each names the rules file it reads
               (`read`) or joins (`combine`) with; a rules file alone is read over the pass before it
    master:    the table and Dataset Contract its records are mastered under (none: nothing is mastered)
    silver:    the tables it lands (`land`) or builds from stored rows (`derive`), in order

and `expand` gives the steps the engine runs. A step's key, leases and checks follow from what it does, and
what a pass waits for follows from what it reads, so no target writes them; the record step always comes last
and waits for every step nothing else waits for.
"""
from __future__ import annotations

# What each kind of step is to the engine: its operation, key, leases and checks.
KINDS = {
    "read": ("source.read", "{unit}", ["artifact:{destination}"], "source.output"),
    "combine": ("source.combine", "{unit}", ["artifact:{destination}"], "source.combined"),
    "prepare": ("mdm.prepare", "{unit}", ["artifact:{destination}"], "mdm.prepared"),
    "merge": ("mastering.merge", "{batch_id}", ["mdm:consumer:{consumer}"], "mdm.committed"),
    "land": ("silver.land", "{unit}", ["silver:{silver}"], "silver.landed"),
    "derive": ("silver.derive", "{unit}", ["silver:{silver}", "silver:{reads}"], "silver.derived"),
    "record": ("journal.record", "{unit}", ["artifact:{destination}"], "journal.recorded"),
}
TARGET_CHECKS = ["manifest.hash", "work.accounting", "journal.delivered"]
SHAPE = frozenset({"extract", "master", "silver"})


class ShapeError(ValueError):
    pass


def _step(kind: str, name: str, requires: list, *, units=None, inputs=None) -> dict:
    operation, key, leases, check = KINDS[kind]
    step = {"name": name, "operation": operation, "requires": list(requires), "key": key, "leases": list(leases),
            "checks": ["input.hash", "output.receipt", check]}
    if units is not None:
        step["units"] = units
    if inputs:
        step["input"] = inputs
    return step


def _waits(inputs: dict) -> list:
    """The passes a pass reads from, in the order it names them: it waits for those and nothing else."""
    named = [lookup["from"] for lookup in (inputs.get("lookups") or {}).values() if "from" in lookup]
    named += [reading.get("step") or reading.get("all") for reading in (inputs.get("readings") or {}).values()]
    named += [inputs["pieces"]["step"]] if "step" in (inputs.get("pieces") or {}) else []
    return list(dict.fromkeys(name for name in named if name))


def _extract(name: str, entry, before: str | None) -> dict:
    if isinstance(entry, str) and before:  # the record pass: this rules file over the pass before it
        entry = {"read": entry, "pieces": {"step": before}}
    kinds = [kind for kind in ("read", "combine") if isinstance(entry, dict) and kind in entry]
    if len(kinds) != 1 or "requires" in entry or "name" in entry:
        raise ShapeError("An extract pass has one of `read` or `combine`; what it waits for follows from what it reads")
    (kind,) = kinds
    inputs = {key: value for key, value in entry.items() if key not in (kind, "units")}
    if entry[kind] is not None:  # the rules file it reads with; none is the source's own file
        inputs = {"contract": entry[kind], **inputs}
    return _step(kind, name, _waits(inputs), units=entry.get("units"), inputs=inputs)


def _silver(entry: dict, default: list) -> dict:
    kinds = [kind for kind in ("land", "derive") if kind in entry]
    if not isinstance(entry, dict) or len(kinds) != 1 or not isinstance(entry.get("name"), str) \
            or set(entry) - {"name", "requires", *kinds}:
        raise ShapeError("A silver step has a name and one of `land` or `derive`")
    (kind,) = kinds
    return _step(kind, entry["name"], entry.get("requires", default), inputs={"keys": entry[kind]})


def expand(target: dict) -> dict:
    """The target with its steps written out; one that already lists steps is returned as it is."""
    if not isinstance(target, dict) or not SHAPE & set(target):
        return target
    if "steps" in target:
        raise ShapeError("A target lists steps or is written in the one shape, not both")
    passes = target.get("extract")
    if not isinstance(passes, dict) or not passes:
        raise ShapeError("A target's `extract` names each pass over the source's files, at least one")
    steps = []
    for name, entry in passes.items():
        steps.append(_extract(name, entry, steps[-1]["name"] if steps else None))
    last = [steps[-1]["name"]]
    master = target.get("master")
    if master is not None:
        if not isinstance(master, dict) or "keys" not in master or set(master) - {"keys", "readings", "requires", "names"}:
            raise ShapeError("`master` has keys")
        prepare, merge = (master.get("names") or {}).get("prepare", "prepare"), (master.get("names") or {}).get("merge", "merge")
        steps.append(_step("prepare", prepare, master.get("requires", last),
                           inputs={"keys": master["keys"],  # it reads the last pass whole unless it says otherwise
                                   "readings": master.get("readings", {last[0]: {"all": last[0]}})}))
        steps.append(_step("merge", merge, [prepare]))
        last = [merge]
    base = last  # a landing waits for what it lands from; a derived table for the step before it
    for entry in target.get("silver", []):
        steps.append(_silver(entry, base if "land" in entry else last))
        last = [steps[-1]["name"]]
    waited = {name for step in steps for name in step["requires"]}
    leaves = [step["name"] for step in steps if step["name"] not in waited]
    steps.append(_step("record", (target.get("names") or {}).get("record", "processed"), leaves))
    rest = {key: value for key, value in target.items() if key not in (*SHAPE, "names")}
    return {**rest, "steps": steps, "checks": target.get("checks", list(TARGET_CHECKS))}


def expand_source(body: dict) -> dict:
    """A source document with every target in the one shape written out."""
    targets = ((body.get("bookkeeping") or {}).get("targets")) if isinstance(body, dict) else None
    if isinstance(targets, dict):
        body["bookkeeping"]["targets"] = {name: expand(target) for name, target in targets.items()}
    return body
