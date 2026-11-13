"""The one shape of a load target: extract, master, silver, record.

A target in `source.yaml` says only what is its own:

    extract:   the source's reads and joins, in order (each names its `read` or `combine` rules file)
    master:    the table and Dataset Contract its records are mastered under (none: nothing is mastered)
    silver:    the tables it lands (`land`) or builds from stored rows (`derive`), in order

and `expand` gives the steps the engine runs. A step's key, leases and checks follow from what it does, so
no target writes them; the record step always comes last and waits for every step nothing else waits for.
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
STEP_PARTS = ("requires", "units")  # what a step may say beside its name, its kind and its input


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


def _extract(entry: dict) -> dict:
    kinds = [kind for kind in ("read", "combine") if kind in entry]
    if not isinstance(entry, dict) or len(kinds) != 1 or not isinstance(entry.get("name"), str):
        raise ShapeError("An extract step has a name and one of `read` or `combine`")
    (kind,) = kinds
    inputs = {key: value for key, value in entry.items() if key not in ("name", kind, *STEP_PARTS)}
    if entry[kind] is not None:  # the rules file it reads with; none is the source's own file
        inputs = {"contract": entry[kind], **inputs}
    return _step(kind, entry["name"], entry.get("requires", []), units=entry.get("units"), inputs=inputs)


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
    steps = [_extract(entry) for entry in target.get("extract", [])]
    if not steps:
        raise ShapeError("A target extracts at least one file")
    last = [steps[-1]["name"]]
    master = target.get("master")
    if master is not None:
        if not isinstance(master, dict) or not {"keys", "readings"} <= set(master) \
                or set(master) - {"keys", "readings", "requires", "names"}:
            raise ShapeError("`master` has keys and readings")
        prepare, merge = (master.get("names") or {}).get("prepare", "prepare"), (master.get("names") or {}).get("merge", "merge")
        steps.append(_step("prepare", prepare, master.get("requires", last),
                           inputs={"keys": master["keys"], "readings": master["readings"]}))
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
