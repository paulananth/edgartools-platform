"""A declared `source.read` step's units, from a bundle of captured documents (ticket 14, slice 2c).

The step's `units` cut the documents its `files` pattern selects: `slices` of
at most N bytes, `groups` of at most N documents, `each` file alone, or `one`.
Its `input` says what each document is read as:

- `beside`: the document's companion instead (`{path, sha256}`: a request
  file beside its answer, its sha256 in the answer's receipt), so the pair
  is selected, and processed, as one;
- `context`: values per document, each text a template over `{dir}` (the
  key's folder), `{base}` (its name before the first dot) and `{name}`;
- `lookups`: pair sets read from the same file's unit of an earlier `each`
  step (one composed slot per document, so a group holds at most 16);
- `pieces`: one unit reading a combine's verified output piece by piece.

A document's pair key is `{dir}/{base}`: an answer and its request share it,
and it is the key of an `each` unit. Nothing here names a source or a kind.
"""

from __future__ import annotations

import fnmatch
import posixpath

from edgar_warehouse.bookkeeping.clean.config import COMPOSE_LIST, RECEIPT_CONTEXT
from edgar_warehouse.workers.source_readings import RECEIPT_BYTES

from . import raw_capture
from .store import canonical, digest

CONTRACT_BYTES = 1024**2  # the worker reads a contract within 1 MiB
CONTEXT_TYPES = {"integer": int, "text": str, "boolean": bool}


def unit(output: str, keys: dict, source: dict) -> dict:
    """A manifest unit: its keys (with its output as `destination`), its input and its output."""
    return {"keys": {**keys, "destination": output}, "input": source, "output": output, "cursor": {}}


def context_value(template, key: str, run):
    """A context value for one document: a run fact, the document's receipt hash, or a filled template."""
    if template == RECEIPT_CONTEXT:
        return run.receipts[key]
    return fill(template, key, run.facts)


def fill(template, key: str, facts: dict | None = None):
    """A template filled for one document; a run fact (`{fact: <name>}`) its value; a key folder's `<name>=<value>` segment (`{segment: <name>}`); a literal as it is."""
    if isinstance(template, dict) and "segment" in template:
        found = [part[len(template["segment"]) + 1:] for part in key.split("/")[:-1]
                 if part.startswith(template["segment"] + "=")]
        if len(found) != 1:
            raise ValueError(f"Document {key} has no segment {template['segment']}= (or more than one)")
        return int(found[0]) if template.get("as") == "integer" else found[0]
    if isinstance(template, dict):
        return (facts or {})[template["fact"]]
    if not isinstance(template, str):
        return template
    folder, name = posixpath.split(key)
    return template.replace("{dir}", folder).replace("{base}", name.split(".", 1)[0]).replace("{name}", name)


def contract_of(step: dict) -> str:
    """The rules file a step reads with: its `input.contract`, default `source.yaml`."""
    return step.get("input", {}).get("contract", "source.yaml")


def run_label(selector: dict) -> str:
    """Another run's step a reading or a lookup names (ticket 120): `<source>/<target>/<step>`."""
    return f"{selector['source']}/{selector['target']}/{selector['step']}"


def run_units(run, selector: dict) -> list[dict]:
    """That step's verified units, as the slot's list of `{run, step, key}`."""
    return [{k: u[k] for k in ("run", "step", "key")} for u in run.others[run_label(selector)]]


def pair(key: str) -> str:
    """A document's pair key, `{dir}/{base}`: an answer and its request share it."""
    return fill("{dir}/{base}", key)


def _cut(step: dict, run, keys: list[str]) -> list[tuple[str, str, list[str]]]:
    """The step's units as (unit key, output name, documents)."""
    name, plan = step["name"], step.get("units", "one")
    if plan == "one":
        return [(name, "reading", keys)]
    if "each" in plan:
        return [(pair(key), pair(key), [key]) for key in keys]
    if "groups" in plan:
        size = plan["groups"]
        return [(f"{name}-{start}", str(start), keys[start:start + size]) for start in range(0, len(keys), size)]
    selected = set(keys)
    found, start = [], 0
    for cut in raw_capture.slices([(k, size) for k, size in run.sized if k in selected], plan["slices"]["bytes"],
                                  run.limit):
        found.append((f"{name}-{start}", str(start), cut))
        start += len(cut)
    return found


def companions(steps: list[dict], rows: dict, key: str) -> list[tuple[str, str]]:
    """The companion files a document's steps read beside it, each with the sha256 its receipt holds."""
    found = {}
    for step in steps:
        beside = step.get("input", {}).get("beside")
        if beside is not None:
            sha256 = rows[key].get(beside["sha256"])
            if not isinstance(sha256, str):
                raise raw_capture.Conflict(f"Step {step['name']}: the receipt of {key} holds no {beside['sha256']}")
            found[fill(beside["path"], key)] = sha256
    return sorted(found.items())


def _document(step: dict, run, key: str) -> dict:
    """What one document is read as: itself, or its companion."""
    beside = step.get("input", {}).get("beside")
    if "runfile" in step.get("input", {}):  # a run file's canonical bytes, stored once (ticket 177, slice 5)
        return run.store.put_bytes(f"{run.inputs}/{key}.json", canonical(run.run_files[key]).encode())
    if beside is None:
        return raw_capture.document(run.folder, run.receipts, key)
    companion = fill(beside["path"], key)
    return raw_capture.verified(run.folder, companion, dict(run.companions[key])[companion])[0]


def _check_run_inputs(name: str, shape: dict, body: dict, run) -> None:
    """A run's facts and files fit the contract they fill, checked before any unit is written."""
    read = body.get("read") or {}
    for ref in shape.get("references", {}):
        if read.get("references", {}).get(ref) != {}:
            raise ValueError(f"Step {name}: reference {ref} is not one the contract declares empty")
    for value_name, template in shape.get("context", {}).items():
        if template == RECEIPT_CONTEXT:
            if (read.get("context") or {}).get(value_name, {}).get("type") != "text":
                raise ValueError(f"Step {name}: the receipt hash is text, but the contract's {value_name} is not")
        elif isinstance(template, dict) and "segment" in template:
            declared = (read.get("context") or {}).get(value_name, {}).get("type")
            if declared != template.get("as", "text"):
                raise ValueError(f"Step {name}: segment {template['segment']} is {template.get('as', 'text')}, "
                                 f"but the contract's {value_name} is {declared}")
        elif template is None:
            if not (read.get("context") or {}).get(value_name, {}).get("nullable"):
                raise ValueError(f"Step {name}: the contract's {value_name} does not take null")
        elif isinstance(template, dict):
            kind = CONTEXT_TYPES.get((read.get("context") or {}).get(value_name, {}).get("type"))
            fact = run.facts[template["fact"]]
            if kind is None or not isinstance(fact, kind) or kind is int and isinstance(fact, bool):
                raise ValueError(f"Step {name}: fact {template['fact']} is not the contract's {value_name}")
    files = {set_name: value["file"] for set_name, value in shape.get("lookups", {}).items() if "file" in value}
    declared = read.get("lookup_sets") or {}
    if files and set(files) != set(declared):
        raise ValueError(f"Step {name}: its lookup sets are the contract's {sorted(declared)}")
    for set_name, file_name in files.items():
        spec, values = declared[set_name], run.run_files[file_name]
        pairs = bool(spec.get("pairs"))
        if (not isinstance(values, list) or len(values) > spec["max_values"]
                or any(not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) for x in v))
                       if pairs else not isinstance(v, str) for v in values)
                or len(canonical(values).encode()) > min(spec["max_bytes"], RECEIPT_BYTES)):
            raise ValueError(f"Step {name}: run file {file_name} is not lookup set {set_name} "
                             f"({'pairs' if pairs else 'values'} of text, within its bounds)")


def bound(name: str, shape: dict, body: dict, run) -> dict:
    """The contract with each `bind` token replaced by its run fact (text) or run file's digest.
    Only whole string values equal to a token are replaced; a token the contract never carries is refused."""
    tokens = shape.get("bind")
    if not tokens:
        return body
    values = {}
    for token, ref in tokens.items():
        if "fact" in ref:
            if not isinstance(run.facts[ref["fact"]], str):
                raise ValueError(f"Step {name}: fact {ref['fact']} binds {token}, which takes text")
            values[token] = run.facts[ref["fact"]]
        else:
            values[token] = digest(run.run_files[ref["digest"]])
    found = set()

    def walk(value):
        if isinstance(value, str):
            if value in values:
                found.add(value)
                return values[value]
            return value
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return value
    result = walk(body)
    if missing := sorted(set(values) - found):
        raise ValueError(f"Step {name}: its contract carries no {missing}")
    return result


def form(step: dict, run, units: dict) -> list[dict]:
    """The units of one `source.read` step."""
    name, shape = step["name"], step.get("input", {})
    body = bound(name, shape, run.contracts[contract_of(step)], run)
    _check_run_inputs(name, shape, body, run)
    if shape.get("references"):  # a reference the contract declares empty, filled from a run file
        body = {**body, "read": {**body["read"], "references": {
            **body["read"].get("references", {}),
            **{ref: run.run_files[value["file"]] for ref, value in shape["references"].items()}}}}
        if len(canonical(body).encode()) > CONTRACT_BYTES:
            raise ValueError(f"Step {name}: the contract with its references filled is over 1 MiB; "
                             "give a large set as a lookup set instead")
    contract = run.store.put(run.inputs, body)
    if "pieces" in shape:
        if "run" in shape["pieces"]:  # another run's combine, read as it was verified (ticket 190)
            (before,) = run_units(run, shape["pieces"]["run"])
            slot = before
        else:
            if run.by_name[shape["pieces"]["step"]]["operation"] != "source.combine":
                raise ValueError(f"Step {name}: pieces are read from a source.combine step")
            (before,) = units[shape["pieces"]["step"]]
            slot = {"step": shape["pieces"]["step"], "key": before["keys"]["unit"]}
        given = {value_name: context_value(template, name, run) for value_name, template in shape.get("context", {}).items()}
        return [unit(f"{run.root}/{name}/reading.json", {"unit": name}, {"compose": {
            "document": {"version": 4, "contract": contract, "pieces": {"slot": "pieces"}, **({"context": given} if given else {})},
            "slots": {"pieces": slot}}})]
    keys = [shape["runfile"]] if "runfile" in shape else [
        key for key in run.keys if fnmatch.fnmatchcase(key, shape.get("files", "*"))]
    if not keys:
        raise ValueError(f"Step {name}: no document of the bundle matches {shape.get('files', '*')!r}")
    lookups = shape.get("lookups", {})
    from_files = bool(lookups) and all("file" in value for value in lookups.values())
    for value in ([] if from_files else lookups.values()):
        if "run" in value:  # another run's step, read whole (ticket 120)
            continue
        if value.get("over") == "all":  # every unit of the prerequisite, in one reading (ticket 177, slice 4)
            if not 1 <= len(units[value["from"]]) <= COMPOSE_LIST:
                raise ValueError(f"Step {name}: a lookup over all reads 1..{COMPOSE_LIST} units of {value['from']}")
            continue
        if run.by_name[value["from"]].get("units") != {"each": "file"}:
            raise ValueError(f"Step {name}: a lookup reads the same file's unit of a step whose units are each file")
    found = []
    for key_of_unit, label, documents in _cut(step, run, keys):
        artifacts, slots = [], {}
        for position, key in enumerate(documents):
            source = _document(step, run, key)
            artifact = {"input": source}
            if "context" in shape or lookups:  # a lookup needs a context receipt, empty values when none is declared
                artifact["context"] = run.store.put(run.inputs, {"version": 1, "input": source, "values": {
                    value_name: context_value(template, key, run) for value_name, template in shape.get("context", {}).items()}})
            if from_files:  # each set given whole by a run file
                artifact["lookups"] = run.store.put(run.inputs, {"version": 1, "input": source, "sets": {
                    set_name: run.run_files[value["file"]] for set_name, value in lookups.items()}})
            elif lookups:
                slot = f"file_{position}"
                artifact["lookups"] = {"slot": slot}
                slots[slot] = {"compose": {
                    "document": {"version": 2, "input": source, "sets": {
                        set_name: {"readings": {"slot": set_name} if "run" in value or value.get("over") == "all"
                                   else [{"slot": set_name}],
                                   **{k: v for k, v in value.items() if k not in ("from", "run", "over")}}
                        for set_name, value in lookups.items()}},
                    "slots": {set_name: run_units(run, value["run"]) if "run" in value
                              else [{"step": value["from"], "key": u["keys"]["unit"]} for u in units[value["from"]]]
                              if value.get("over") == "all" else {"step": value["from"], "key": pair(key)}
                              for set_name, value in lookups.items()}}}
            artifacts.append(artifact)
        document = raw_capture.request(contract, artifacts)
        output = f"{run.root}/{name}/{label}.reading.json"
        source = {"compose": {"document": document, "slots": slots}} if slots else run.store.put(run.inputs, document)
        found.append(unit(output, {"unit": key_of_unit}, source))
    return found
