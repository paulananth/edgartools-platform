"""The one shape of a load target: extract, master, silver, record.

A target in `source.yaml` says only what is its own:

    extract:   the source's last rules file (or files). Each rules file says what it reads in its own `pass`
               block, so the passes follow from the files; a target may instead name each pass itself
    capture:   `copy` or `provider`, for a target that only brings files in
    master:    the table and Dataset Contract its records are mastered under (none: nothing is mastered)
    silver:    the tables it lands (`land`) or builds from stored rows (`derive`), in order

and `expand` gives the steps the engine runs. A step's key, leases and checks follow from what it does, and
what a pass waits for follows from what it reads, so no target writes them; the record step always comes last
and waits for every step nothing else waits for.
"""
from __future__ import annotations

from pathlib import Path

# What each kind of step is to the engine: its operation, key, leases and checks.
KINDS = {
    "read": ("source.read", "{unit}", ["artifact:{destination}"], "source.output"),
    "combine": ("source.combine", "{unit}", ["artifact:{destination}"], "source.combined"),
    "prepare": ("mdm.prepare", "{unit}", ["artifact:{destination}"], "mdm.prepared"),
    "merge": ("mastering.merge", "{batch_id}", ["mdm:consumer:{consumer}"], "mdm.committed"),
    # A landing unit leases its own part of the table, so a step's units land side by side; the writer's table
    # lock, held for the merge of its staged rows only, keeps two deliveries apart.
    "land": ("silver.land", "{unit}", ["silver:{silver}:{unit}"], "silver.landed"),
    "derive": ("silver.derive", "{unit}", ["silver:{silver}", "silver:{reads}"], "silver.derived"),
    "record": ("journal.record", "{unit}", ["artifact:{destination}"], "journal.recorded"),
}
# A capture brings files in before any extract: a copy of files already held, or a fetch from the provider.
CAPTURES = {
    "copy": ("artifact.copy", "{artifact_id}", ["artifact:{destination}"], []),
    "provider": ("provider.capture", "{accession_number}", ["provider:sec", "output:{destination}"], ["capture.verified"]),
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


def _reads(block: dict):
    """Every place a pass names another pass: (holder, key)."""
    for lookup in (block.get("lookups") or {}).values():
        if "from" in lookup:
            yield lookup, "from"
    for reading in (block.get("readings") or {}).values():
        for key in ("step", "all"):
            if key in reading:
                yield reading, key
    if "step" in (block.get("pieces") or {}):
        yield block["pieces"], "step"


def follow(leaves: list, folder) -> dict:
    """The passes behind a target's rules files, each after the passes it reads.

    A rules file says what it reads in its own `pass` block: its files, units and context, and the other rules
    files it looks up, joins or reads over. The target names only the last file (or files); a pass is named
    after its file unless the block names it.
    """
    from . import files

    passes, names = {}, {}

    def visit(ref: str, base) -> str:
        path = (base / ref) if "/" not in ref else base.parent / ref
        if path in names:
            return names[path]
        block = files.load(path).get("pass")
        if not isinstance(block, dict):
            raise ShapeError(f"{path.parent.name}/{path.name} has no `pass` block saying what it reads")
        block = {key: ({name: dict(item) for name, item in value.items()} if key in ("lookups", "readings")
                       else dict(value) if key == "pieces" else value) for key, value in block.items()}
        for holder, key in _reads(block):
            if not str(holder[key]).endswith(".yaml"):
                raise ShapeError(f"{path.name}: a pass names the rules file it reads, not {holder[key]!r}")
            holder[key] = visit(holder[key], path.parent)
        name = block.pop("name", path.stem.replace("-", "_"))
        if name in passes:
            raise ShapeError(f"Two passes of one target are named {name}")
        contract = None if path == folder / "source.yaml" else path.name if path.parent == folder \
            else f"{path.parent.name}/{path.name}"
        passes[name] = {"combine" if "readings" in block else "read": contract, **block}
        names[path] = name
        return name

    for leaf in leaves:
        visit(leaf, folder)
    return passes


def _snapshots(folder) -> set:
    """The tables of the source's silver specs (`silver-*.yaml`) that are snapshots."""
    from .files import load

    found = (load(path) for path in sorted(Path(folder).glob("silver-*.yaml"))) if folder is not None else ()
    return {spec["table"] for spec in found if isinstance(spec, dict) and spec.get("load_mode") == "snapshot"}


def _silver(entry: dict, default: list, folder=None) -> dict:
    kinds = [kind for kind in ("land", "derive") if kind in entry]
    if not isinstance(entry, dict) or len(kinds) != 1 or not isinstance(entry.get("name"), str) \
            or set(entry) - {"name", "requires", *kinds}:
        raise ShapeError("A silver step has a name and one of `land` or `derive`")
    (kind,) = kinds
    step = _step(kind, entry["name"], entry.get("requires", default), inputs={"keys": entry[kind]})
    if kind == "land" and entry["land"].get("silver") in _snapshots(folder):
        # A snapshot delivery deletes every row it lacks, so units each holding their own keys would erase each other.
        raise ShapeError(f"{entry['name']}: silver.{entry['land']['silver']} is a snapshot table; derive it whole, "
                         "do not land it")
    return step


def _capture(target: dict) -> dict:
    kind = target["capture"]
    if kind not in CAPTURES or set(target) & (SHAPE | {"steps"}):
        raise ShapeError(f"`capture` is one of {sorted(CAPTURES)} and the target's only step")
    operation, key, leases, checks = CAPTURES[kind]
    rest = {name: value for name, value in target.items() if name != "capture"}
    return {**rest, "steps": [{"name": "capture", "operation": operation, "requires": [], "key": key,
                              "leases": list(leases), "checks": ["input.hash", "output.receipt", *checks]}],
            "checks": target.get("checks", list(TARGET_CHECKS))}


def expand(target: dict, folder=None) -> dict:
    """The target with its steps written out; one that already lists steps is returned as it is."""
    if isinstance(target, dict) and "capture" in target:
        return _capture(target)
    if not isinstance(target, dict) or not SHAPE & set(target):
        return target
    if "steps" in target:
        raise ShapeError("A target lists steps or is written in the one shape, not both")
    passes = target.get("extract")
    if isinstance(passes, (str, list)) and passes and folder is not None:
        passes = follow([passes] if isinstance(passes, str) else passes, folder)
    if not isinstance(passes, dict) or not passes:
        raise ShapeError("A target's `extract` names its last rules file, or each pass by name")
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
        steps.append(_silver(entry, base if "land" in entry else last, folder))
        last = [steps[-1]["name"]]
    checks = list(TARGET_CHECKS)
    if target.get("record", True):
        waited = {name for step in steps for name in step["requires"]}
        leaves = [step["name"] for step in steps if step["name"] not in waited]
        steps.append(_step("record", (target.get("names") or {}).get("record", "processed"), leaves))
    else:  # a second pass over files another target records
        checks.remove("journal.delivered")
    rest = {key: value for key, value in target.items() if key not in (*SHAPE, "names", "record")}
    return {**rest, "steps": steps, "checks": target.get("checks", checks)}


def expand_source(body: dict, folder=None) -> dict:
    """A source document with every target in the one shape written out. `folder` is the source's rules
    folder: a target that names its last rules file is followed from there."""
    targets = ((body.get("bookkeeping") or {}).get("targets")) if isinstance(body, dict) else None
    if isinstance(targets, dict):
        body["bookkeeping"]["targets"] = {name: expand(target, folder) for name, target in targets.items()}
    return body
