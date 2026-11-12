"""Validate and freeze approved Rules exports and source-owned input worklists.

There is intentionally no Rules store here. A submission resolver supplies an
approved export; execution only reads its frozen content-addressed references.
"""
from __future__ import annotations

import re
from string import Formatter
from uuid import UUID


from edgar_warehouse.control_contract import Blocked, canonical, digest, reference


# Checks control runs itself. Every other check a step names is a domain check:
# the step's worker must report it true.
STEP_CHECKS = frozenset({"input.hash", "output.receipt"})
RUN_CHECKS = frozenset({"manifest.hash", "work.accounting", "journal.delivered"})
IDENTIFIER = r"[a-z][a-z0-9_.-]*"


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise Blocked(f"{name} must be an integer in [{low}, {high}]")
    return value


# Version 2 (ticket 14): a step may also say how its units are formed (`units`)
# and what each unit's input names (`input`), which the input-manifest writer
# reads. They are checked here and stripped, so the engine sees version-1 steps.
PLAN_KEYS = frozenset({"units", "input"})
INPUT_KEYS = frozenset({"contract", "keys", "readings", "files", "beside", "context", "lookups", "pieces",
                        "references", "bind", "runfile", "always"})
# A token a step's contract carries, replaced before the contract is frozen: `{fact: <name>}` (text)
# or `{digest: <file>}` (the sha256 of a run file's canonical content).
BIND_TOKEN = r"[A-Za-z0-9_.:-]{1,128}"
# A run's own inputs (ticket 114): facts the operator gives (`--fact name=value`) and files
# from outside the capture (`--file name=path`); a step names them as `{fact: <name>}` in its
# context, `{file: <name>}` for a lookup set or a contract reference.
RUN_KEYS = frozenset({"facts", "files"})
# A run file counts toward a file's processing identity by its content; `projections` names, per file, the
# top-level parts of that content that count (ticket 177, slice 3), so the rest of the file moves nothing.
# `matches` ties a run file to the capture it is run over: its part at a dotted `path` must equal the named
# property of the capture (`receipts_sha256`: the sha256 of its receipts file), so a Name Count built from
# another capture is refused before any unit is written (ticket 177, slice 5d).
# `derived` names, per run file, how the loader builds it when the caller gives none (a set the store decides:
# a scope, the names a reading keeps): a registered `method`, and the `purpose` and `why` that make the rule explain
# itself. A derived file is built on every load, so a daily run and a go-live run get the same answer from the
# store; the operator is asked only when neither the rules nor the store can decide.
RUN_DECLARED = RUN_KEYS | {"projections", "matches", "derived"}
MATCH_PROPERTIES = frozenset({"receipts_sha256"})
PROJECTION_PARTS = 16
NAME = r"[a-z][a-z0-9_]*"
LOOKUP_KEYS = frozenset({"from", "table", "column", "value_column", "max_input_bytes", "max_input_rows"})
# A lookup reads the same file's unit of its prerequisite (`over: file`, the default), or every unit of it in
# one reading (`over: all`, ticket 177 slice 4): one read of a large shared file per bundle, not per group.
LOOKUP_OVER = frozenset({"file", "all"})
# A per-document template names the document's folder, its name before the first dot, and its file name.
TEMPLATE = r"(?:[^{}]|\{(?:dir|base|name)\})*"


SLICE_BYTES = 1024**3


def _units(units) -> None:
    if units == "one":
        return
    if not isinstance(units, dict) or len(units) != 1 or not set(units) <= {"slices", "groups", "each"}:
        raise Blocked(f"A step's units are one, slices of at most N bytes, groups of 1..{COMPOSE_SLOTS} files, "
                      "or each file")
    if "each" in units:
        if units["each"] != "file" and not (isinstance(units["each"], str) and re.fullmatch(NAME, units["each"])):
            raise Blocked("A step's units are each file {each: file}, or (a combine's) each unit of a step {each: <step>}")
        return
    if "slices" in units:
        slices = units["slices"]
        if (not isinstance(slices, dict) or set(slices) != {"bytes"} or type(slices["bytes"]) is not int
                or not 1 <= slices["bytes"] <= SLICE_BYTES):
            raise Blocked(f"A step's slices name their bytes, 1..{SLICE_BYTES}")
    elif type(units["groups"]) is not int or not 1 <= units["groups"] <= COMPOSE_SLOTS:
        raise Blocked(f"A step's groups hold 1..{COMPOSE_SLOTS} files (the composed-slot limit)")


# A context value taken from the document's own receipt (its sha256, as the capture recorded it).
RECEIPT_CONTEXT = {"receipt": "sha256"}


def _segment(value) -> bool:
    """`{segment: <name>}` (optionally `as: text|integer`): the value of the key's `<name>=<value>` folder."""
    return (isinstance(value, dict) and set(value) in ({"segment"}, {"segment", "as"})
            and isinstance(value["segment"], str) and bool(re.fullmatch(NAME, value["segment"]))
            and value.get("as", "text") in ("text", "integer"))


def _named(value, kind: str) -> bool:
    """`{fact: <name>}` or `{file: <name>}`: a run input by name."""
    return isinstance(value, dict) and set(value) == {kind} and isinstance(value[kind], str) and bool(re.fullmatch(NAME, value[kind]))


def run_inputs(selected: dict) -> dict:
    """A target's declared run inputs: `{facts: [names], files: [names], projections: {file: [parts]}}`."""
    declared = selected.get("run", {})
    if (not isinstance(declared, dict) or set(declared) - RUN_DECLARED
            or any(not isinstance(declared.get(k, []), list) or len(set(declared.get(k, []))) != len(declared.get(k, []))
                   or any(not isinstance(n, str) or not re.fullmatch(NAME, n) for n in declared.get(k, []))
                   for k in RUN_KEYS)):
        raise Blocked("A target's run names its facts and files: {facts: [names], files: [names]}")
    found = {k: list(declared.get(k, [])) for k in sorted(RUN_KEYS)}
    projections = declared.get("projections", {})
    if not isinstance(projections, dict) or any(name not in found["files"] for name in projections):
        raise Blocked("A run file's projection names a file the run declares")
    for name, parts in projections.items():
        if (not isinstance(parts, list) or not 1 <= len(parts) <= PROJECTION_PARTS or len(set(parts)) != len(parts)
                or any(not isinstance(part, str) or not part for part in parts)):
            raise Blocked(f"The projection of run file {name} names 1 to {PROJECTION_PARTS} distinct parts of it")
    found["projections"] = {name: list(parts) for name, parts in sorted(projections.items())}
    matches = declared.get("matches", [])
    if (not isinstance(matches, list) or any(
            not isinstance(m, dict) or set(m) != {"file", "path", "to"} or m["file"] not in found["files"]
            or not isinstance(m["path"], str) or not re.fullmatch(r"[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*", m["path"])
            or m["to"] not in MATCH_PROPERTIES for m in matches)):
        raise Blocked("A run file's matches each name a declared file, a dotted path in it and a property of the "
                      f"capture ({sorted(MATCH_PROPERTIES)}): {{file, path, to}}")
    found["matches"] = [dict(m) for m in matches]
    derived = declared.get("derived", {})
    if (not isinstance(derived, dict) or any(
            name not in found["files"] or not isinstance(how, dict) or set(how) != {"method", "purpose", "why"}
            or not isinstance(how["method"], str) or not re.fullmatch(NAME, how["method"])
            or any(not isinstance(how[k], str) or not how[k].strip() for k in ("purpose", "why"))
            for name, how in derived.items())):
        raise Blocked("A derived run file names a declared file and its {method, purpose, why}, each text")
    found["derived"] = {name: dict(how) for name, how in sorted(derived.items())}
    return found



def _key_value(name: str, value) -> bool:
    """A step key is nonempty text; `distinct_on` (mdm.prepare) names 1 to 8 distinct columns."""
    if name == "distinct_on":
        return (isinstance(value, list) and 1 <= len(value) <= 8 and len(set(value)) == len(value)
                and all(isinstance(c, str) and c for c in value))
    return isinstance(value, str) and bool(value)

def _plan(step: dict) -> None:
    _units(step.get("units", "one"))
    shape = step.get("input", {})
    if not isinstance(shape, dict) or set(shape) - INPUT_KEYS:
        raise Blocked("A step's input names its contract, keys, readings, files, beside, context, lookups, "
                      "pieces, references, runfile, always and bind only")
    if "contract" in shape and (not isinstance(shape["contract"], str)
                                or not re.fullmatch(r"(?:[a-z0-9][a-z0-9_.-]*/)?[a-z0-9][a-z0-9_.-]*\.yaml", shape["contract"])):
        raise Blocked("A step's contract is a rules file in the source's folder, or <source>/<file> in another's")
    if "keys" in shape and (not isinstance(shape["keys"], dict)
                            or any(not _key_value(k, v) for k, v in shape["keys"].items())):
        raise Blocked("A step's keys are nonempty text (distinct_on: 1 to 8 distinct column names)")
    readings = shape.get("readings", {})
    if not isinstance(readings, dict) or any(not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in readings):
        raise Blocked("A step's readings are named by identifiers")
    if any(not isinstance(value, dict) or len(value) != 1 or not (
               set(value) <= {"all", "step"} and value.get("all", value.get("step")) in step["requires"]
               or set(value) == {"run"} and _other_run(value["run"])) for value in readings.values()):
        raise Blocked("A step's readings each name one prerequisite step, {all: <step>} or {step: <step>}, "
                      "or another run's step: {run: {source, target, step}}")
    if "files" in shape and (not isinstance(shape["files"], str) or not shape["files"] or ".." in shape["files"]):
        raise Blocked("A step's files are a pattern over the bundle's documents")
    beside = shape.get("beside")
    if beside is not None and (not isinstance(beside, dict) or set(beside) != {"path", "sha256"} or not isinstance(beside["path"], str)
            or not re.fullmatch(TEMPLATE, beside["path"]) or ".." in beside["path"]
            or not isinstance(beside["sha256"], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", beside["sha256"])):
        raise Blocked("A step's beside names a template path and the receipt field holding its sha256")
    context = shape.get("context", {})
    if (not isinstance(context, dict) or any(not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in context)
            or any(isinstance(v, str) and not re.fullmatch(TEMPLATE, v) for v in context.values())
            or any(not isinstance(v, (str, int, bool, type(None))) and not _named(v, "fact") and v != RECEIPT_CONTEXT
                   and not _segment(v) for v in context.values())):
        raise Blocked("A step's context names values: text templates over {dir}, {base} and {name}, "
                      "literals (or null), a run fact {fact: <name>}, a folder segment of the key "
                      "{segment: <name>, as: text|integer}, or the document's receipt hash {receipt: sha256}")
    lookups = shape.get("lookups", {})
    if (not isinstance(lookups, dict) or len(lookups) > COMPOSE_SLOTS - 1
            or any(not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in lookups)
            or any(not _named(v, "file") and (
                       not isinstance(v, dict)
                       or v.get("over", "file") not in LOOKUP_OVER
                       or not (set(v) - {"over"} in (LOOKUP_KEYS, LOOKUP_KEYS - {"value_column"})
                               and v["from"] in step["requires"]
                               or set(v) == LOOKUP_KEYS - {"from"} | {"run"} and _other_run(v["run"]))
                       or any(type(v[k]) is not int or v[k] < 1 for k in ("max_input_bytes", "max_input_rows")))
                   for v in lookups.values())):
        raise Blocked("A step's lookups each read the same file's unit of one prerequisite (from, table, "
                      "column, value_column and their bounds; `over: all` reads every unit of it), another run's "
                      "step instead of `from` ({run: {source, target, step}}), or a run file {file: <name>}")
    if any(_named(v, "file") for v in lookups.values()) and not all(_named(v, "file") for v in lookups.values()):
        raise Blocked("A step's lookups are all run files, or all read from a prerequisite")
    if "runfile" in shape and (not isinstance(shape["runfile"], str) or not re.fullmatch(NAME, shape["runfile"])
                               or {"files", "beside", "pieces"} & set(shape) or step.get("units", "one") != "one"):
        raise Blocked("A step's runfile names a run file, read as the step's one document (one unit, with no "
                      "files, beside or pieces)")
    if "always" in shape and (shape["always"] is not True or "files" not in shape or step.get("units", "one") != "one"):
        raise Blocked("A step's always is true, names its files, and is one unit: documents every bundle reads")
    bind = shape.get("bind", {})
    if (not isinstance(bind, dict) or any(not isinstance(t, str) or not re.fullmatch(BIND_TOKEN, t) for t in bind)
            or any(not (_named(v, "fact") or _named(v, "digest")) for v in bind.values())):
        raise Blocked("A step's bind maps a token to a run fact {fact: <name>} or a run file's digest {digest: <name>}")
    references = shape.get("references", {})
    if (not isinstance(references, dict) or any(not re.fullmatch(NAME, name) for name in references)
            or any(not _named(v, "file") for v in references.values())):
        raise Blocked("A step's references each name a run file: {<reference>: {file: <name>}}")
    if (lookups and not all(_named(v, "file") or v.get("over") == "all" for v in lookups.values())
            and not (isinstance(step.get("units"), dict) and set(step["units"]) <= {"groups", "each"})):
        raise Blocked("A read with lookups is cut into groups or each file (a composed slot per file)")
    pieces = shape.get("pieces")
    if pieces is not None and not (isinstance(pieces, dict) and (
            set(pieces) == {"step"} and pieces["step"] in step["requires"]
            or set(pieces) == {"run"} and _other_run(pieces["run"]))):
        raise Blocked("A step's pieces name one prerequisite step, {step: <step>}, "
                      "or another run's step, {run: {source, target, step}}")
    if pieces is not None and step.get("units", "one") != "one":
        raise Blocked("A read of pieces is one unit")


def validate(document: dict, target: str) -> dict:
    """Strict versioned contract; reject unknown keys rather than guessing."""
    try:
        body = document["bookkeeping"]
        if set(body) != {"version", "targets"} or type(body["version"]) is not int or body["version"] not in (1, 2):
            raise Blocked("Unsupported bookkeeping configuration")
        planned = body["version"] == 2
        selected = body["targets"][target]
        if set(selected) - {"steps", "lease_seconds", "heartbeat_seconds", "retry", "allow_zero_work", "checks",
                            "local", "preparation"} - (
                {"run"} if planned else set()):
            raise Blocked("Unknown target option")
        declared = run_inputs(selected) if planned else {"facts": [], "files": []}
        preparation = selected.get("preparation", [])
        if (not isinstance(preparation, list) or any(
                not isinstance(p, dict) or set(p) != {"method", "options"}
                or not isinstance(p["method"], str) or not re.fullmatch(NAME, p["method"])
                or not isinstance(p["options"], dict) for p in preparation)):
            raise Blocked("Target preparation is a list of {method, options}")
        if type(selected.get("allow_zero_work", False)) is not bool:
            raise Blocked("allow_zero_work must be boolean")
        if type(selected.get("local", False)) is not bool:
            raise Blocked("local must be boolean")
        duration = _integer(selected.get("lease_seconds", 120), 2, 86400, "lease_seconds")
        heartbeat = _integer(selected.get("heartbeat_seconds", 30), 1, duration - 1, "heartbeat_seconds")
        retry = selected.get("retry", {})
        if set(retry) - {"attempts", "base_ms", "cap_ms"}:
            raise Blocked("Unknown retry option")
        attempts = _integer(retry.get("attempts", 5), 1, 100, "retry.attempts")
        base = _integer(retry.get("base_ms", 100), 1, 60000, "retry.base_ms")
        cap = _integer(retry.get("cap_ms", 5000), base, 60000, "retry.cap_ms")
        steps = selected["steps"]
        if not isinstance(steps, list) or not steps:
            raise Blocked("A target requires steps")
        if planned:
            for step in steps:
                _plan(step)
                shape = step.get("input", {})
                named = [*(v for v in shape.get("context", {}).values() if _named(v, "fact"))]
                named += [v for v in shape.get("bind", {}).values() if _named(v, "fact")]
                files_named = [v["file"] for v in [*shape.get("lookups", {}).values(), *shape.get("references", {}).values()]
                               if _named(v, "file")]
                files_named += [v["digest"] for v in shape.get("bind", {}).values() if _named(v, "digest")]
                files_named += [shape["runfile"]] if "runfile" in shape else []
                if any(v["fact"] not in declared["facts"] for v in named) or any(f not in declared["files"] for f in files_named):
                    raise Blocked(f"Step {step['name']}: a fact or file it names is not in the target's run")
            steps = [{k: v for k, v in step.items() if k not in PLAN_KEYS} for step in steps]
        seen = set()
        for step in steps:
            if set(step) != {"name", "operation", "requires", "key", "leases", "checks"}:
                raise Blocked("A step requires name, operation, requires, key, leases and checks")
            name = step["name"]
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]*", name) or name in seen:
                raise Blocked("Step names must be unique identifiers")
            # The operation names the worker profile that pulls this step.
            if not isinstance(step["operation"], str) or not re.fullmatch(IDENTIFIER, step["operation"]):
                raise Blocked("A step's operation names a worker profile")
            if (not isinstance(step["requires"], list) or len(set(step["requires"])) != len(step["requires"])
                    or not set(step["requires"]) <= seen):
                raise Blocked("Prerequisites must name preceding steps")
            for key in ("key",):
                if not isinstance(step[key], str) or not step[key]:
                    raise Blocked("A step requires a work-unit key")
            if not isinstance(step["leases"], list) or not step["leases"]:
                raise Blocked("A step must declare its conflicting resources")
            for pattern in [step["key"], *step["leases"]]:
                if not isinstance(pattern, str) or not pattern:
                    raise Blocked("Lease/key patterns must be nonempty text")
                for _, field, spec, conversion in Formatter().parse(pattern):
                    if field is not None and (not re.fullmatch(r"[a-z][a-z0-9_]*", field) or spec or conversion):
                        raise Blocked("Templates support simple identifier fields only")
            if not isinstance(step["checks"], list) or len(set(step["checks"])) != len(step["checks"]):
                raise Blocked("Step checks must be a list of distinct check names")
            for check in step["checks"]:
                if not isinstance(check, str) or not re.fullmatch(IDENTIFIER, check) or check in RUN_CHECKS:
                    raise Blocked(f"Unsupported check: {check}")
            if not step["checks"]:
                raise Blocked("Every step requires a check")
            seen.add(name)
        if selected.get("local"):
            local = {step["name"] for step in steps if step["operation"] in LOCAL_OPERATIONS}
            if any(not set(step["requires"]) <= local for step in steps if step["name"] in local):
                raise Blocked("A local step requires only local steps")
        checks = selected.get("checks", [])
        if (not isinstance(checks, list) or not checks or len(set(checks)) != len(checks)
                or any(c not in RUN_CHECKS for c in checks)):
            raise Blocked("A target requires supported final checks")
        return {**{k: v for k, v in selected.items() if k != "run"}, "steps": steps, "lease_seconds": duration,
                "heartbeat_seconds": heartbeat,
                "retry": {"attempts": attempts, "base_ms": base, "cap_ms": cap}}
    except Blocked:
        raise
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise Blocked("Malformed bookkeeping configuration") from exc


# The operations a target marked `local: true` runs in the loader's own process: they turn captured files into
# extracts and write files with receipts, so they need no claim or lease (ticket 210).
LOCAL_OPERATIONS = frozenset({"source.read", "source.combine"})


def staged(config: dict) -> dict:
    """The steps of a run in the database: a target marked `local` has its local steps run by the loader, so the
    run starts at the first step after them and no step waits on one of them."""
    if not config.get("local"):
        return config
    local = {step["name"] for step in config["steps"] if step["operation"] in LOCAL_OPERATIONS}
    return {**config, "steps": [{**step, "requires": [name for name in step["requires"] if name not in local]}
                                for step in config["steps"] if step["name"] not in local]}


# A composed input (to-do 20c): a frozen document whose slots each name verified
# prerequisite output, so one unit can read many (Bookkeeping fan-in).
COMPOSE_SLOTS = 16
COMPOSE_LIST = 256  # as many producer readings as a derived lookup set takes
COMPOSE_BYTES = 1024**2
COMPOSE_DEPTH = 2


def _dependency(dependency, step: dict, identities: set):
    if isinstance(dependency, dict) and set(dependency) == {"run", "step", "key"}:
        # Another run's unit (ticket 120): Bookkeeping fills it only from that run's verified output.
        if not all(isinstance(dependency[k], str) and dependency[k] for k in ("step", "key")) or not _run_id(dependency["run"]):
            raise Blocked("Input must name an existing unit in a preceding prerequisite or another run")
        return
    if (not isinstance(dependency, dict) or set(dependency) != {"step", "key"}
            or not isinstance(dependency["step"], str) or not isinstance(dependency["key"], str)
            or dependency["step"] not in step["requires"]
            or (dependency["step"], dependency["key"]) not in identities):
        raise Blocked("Input must name an existing unit in a preceding prerequisite")


def _other_run(value) -> bool:
    """`{source, target, step}`: a step of another source's target, read from its complete runs (ticket 120)."""
    return (isinstance(value, dict) and set(value) == {"source", "target", "step"}
            and all(isinstance(v, str) and re.fullmatch(IDENTIFIER, v) for v in value.values()))


def _run_id(value) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def slot_names(document) -> list[str]:
    """The slots a template uses: every value that is exactly {"slot": <name>}."""
    if isinstance(document, dict):
        if set(document) == {"slot"}:
            return [document["slot"]]
        return [name for value in document.values() for name in slot_names(value)]
    if isinstance(document, list):
        return [name for value in document for name in slot_names(value)]
    return []


def _composed(body, step: dict, identities: set, depth: int = 1):
    """`{"document": <template>, "slots": {name: unit | [units] | {"compose": ...}}}`: every slot used, every
    used slot declared, every unit an existing unit of a declared prerequisite."""
    if (not isinstance(body, dict) or set(body) != {"document", "slots"} or not isinstance(body["document"], dict)
            or not isinstance(body["slots"], dict) or not 1 <= len(body["slots"]) <= COMPOSE_SLOTS):
        raise Blocked(f"A composed input names a document and 1..{COMPOSE_SLOTS} slots")
    if len(canonical(body).encode()) > COMPOSE_BYTES:
        raise Blocked("A composed input exceeds its byte bound")
    used = slot_names(body["document"])
    if (any(not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in used)
            or set(used) != set(body["slots"])):
        raise Blocked("A composed document uses exactly its declared slots")
    for value in body["slots"].values():
        if isinstance(value, list):
            if not 1 <= len(value) <= COMPOSE_LIST:
                raise Blocked(f"A slot lists 1..{COMPOSE_LIST} units")
            for dependency in value:
                _dependency(dependency, step, identities)
        elif isinstance(value, dict) and set(value) == {"compose"}:
            if depth >= COMPOSE_DEPTH:
                raise Blocked("Composed documents nest at most once")
            _composed(value["compose"], step, identities, depth + 1)
        else:
            _dependency(value, step, identities)


def worklist(manifest: dict, config: dict) -> list[dict]:
    """Freeze stage scope; version 1 retains its original worklist digest.

    Version 2 lists units separately for every configured step. An input may
    name a preceding prerequisite's unit, or compose a document from several;
    only verified output can be resolved at execution time. No paths or work are discovered on resume.
    """
    if not isinstance(manifest, dict) or type(manifest.get("version")) is not int:
        raise Blocked("Unsupported input manifest")
    if manifest["version"] == 1 and set(manifest) == {"version", "units"}:
        stages = {step["name"]: manifest["units"] for step in config["steps"]}
    elif manifest["version"] == 2 and set(manifest) - {"capture"} == {"version", "steps"}:
        # A manifest written from a capture names it (ticket 121), so a reading of this run's
        # output can take the newest capture's runs only.
        if "capture" in manifest and (not isinstance(manifest["capture"], str) or not manifest["capture"]):
            raise Blocked("A manifest's capture is the capture's run id, as text")
        stages = manifest["steps"]
        if not isinstance(stages, dict) or set(stages) != {s["name"] for s in config["steps"]}:
            raise Blocked("Manifest must declare exactly the configured steps")
    else:
        raise Blocked("Unsupported input manifest")
    if any(not isinstance(units, list) for units in stages.values()):
        raise Blocked("Each stage worklist must be a list")
    if any(not units for units in stages.values()) and not config.get("allow_zero_work", False):
        raise Blocked("Zero work is not permitted")
    items = []
    identities = set()
    for step in config["steps"]:
        for ordinal, unit in enumerate(stages[step["name"]]):
            if not isinstance(unit, dict) or set(unit) != {"keys", "input", "output", "cursor"}:
                raise Blocked("Units contain keys, input/output references and an opaque cursor only")
            source = unit["input"]
            if manifest["version"] == 2 and isinstance(source, dict) and set(source) == {"from"}:
                _dependency(source["from"], step, identities)
            elif manifest["version"] == 2 and isinstance(source, dict) and set(source) == {"compose"}:
                _composed(source["compose"], step, identities)
            else:
                reference(source)
            # Output URI names intent; verified content hash is supplied by the
            # durable destination receipt, not guessed during submission.
            if not isinstance(unit["output"], str) or not unit["output"]:
                raise Blocked("Output reference missing")
            if not isinstance(unit["keys"], dict) or any(not _key_value(k, v) for k, v in unit["keys"].items()):
                raise Blocked("Unit keys must be nonempty text")
            try:
                key = step["key"].format_map(unit["keys"])
                resources = sorted(set(p.format_map(unit["keys"]) for p in step["leases"]))
            except KeyError as exc:
                raise Blocked(f"Missing configured key: {exc}") from exc
            cursor = unit["cursor"]
            checkpoint = cursor.get("resource_checkpoint") if isinstance(cursor, dict) else None
            if checkpoint is not None:
                if (not isinstance(checkpoint, dict) or set(checkpoint) != {"resource", "revision", "position"}
                        or checkpoint["resource"] not in resources
                        or type(checkpoint["revision"]) is not int or checkpoint["revision"] < 0
                        or type(checkpoint["position"]) is not int or checkpoint["position"] < -1):
                    raise Blocked("Resource checkpoint must pin leased resource, revision and prior position")
            if (step["name"], key) in identities:
                raise Blocked("Duplicate work-unit identity")
            identities.add((step["name"], key))
            items.append({"step": step["name"], "key": key, "ordinal": ordinal,
                          "resources": resources, "unit": unit})
    return items


def generated_worklist(manifest: dict, config: dict, parent: dict) -> list[dict]:
    """Validate one sealed expansion with the same unit/key/lease rules as v2."""
    if (not isinstance(manifest, dict) or set(manifest) != {"version", "parent", "children"}
            or manifest["version"] != 1 or manifest["parent"] != parent
            or not isinstance(manifest["children"], list) or len(manifest["children"]) > 128):
        raise Blocked("Expansion manifest is unsealed or names another parent")
    selected = next((step for step in config["steps"] if step["name"] == parent["generated_step"]), None)
    if (selected is None or parent["step"] not in selected["requires"]
            or type(parent.get("ordinal_base")) is not int or parent["ordinal_base"] < 0):
        raise Blocked("Expansion names no configured child step")
    child_config = {"steps": [{**selected, "requires": []}], "allow_zero_work": True}
    return [{**item, "ordinal": parent["ordinal_base"] + item["ordinal"]}
            for item in worklist({"version": 2, "steps": {selected["name"]: manifest["children"]}}, child_config)]
