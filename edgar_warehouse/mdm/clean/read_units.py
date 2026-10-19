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

from . import raw_capture


def unit(output: str, keys: dict, source: dict) -> dict:
    """A manifest unit: its keys (with its output as `destination`), its input and its output."""
    return {"keys": {**keys, "destination": output}, "input": source, "output": output, "cursor": {}}


def fill(template, key: str, facts: dict | None = None):
    """A template filled for one document; a run fact (`{fact: <name>}`) its value; a literal as it is."""
    if isinstance(template, dict):
        return (facts or {})[template["fact"]]
    if not isinstance(template, str):
        return template
    folder, name = posixpath.split(key)
    return template.replace("{dir}", folder).replace("{base}", name.split(".", 1)[0]).replace("{name}", name)


def contract_of(step: dict) -> str:
    """The rules file a step reads with: its `input.contract`, default `source.yaml`."""
    return step.get("input", {}).get("contract", "source.yaml")


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
    if beside is None:
        return raw_capture.document(run.folder, run.receipts, key)
    companion = fill(beside["path"], key)
    return raw_capture.verified(run.folder, companion, dict(run.companions[key])[companion])[0]


def form(step: dict, run, units: dict) -> list[dict]:
    """The units of one `source.read` step."""
    name, shape = step["name"], step.get("input", {})
    body = run.contracts[contract_of(step)]
    if shape.get("references"):  # a reference the contract leaves empty, filled from a run file
        body = {**body, "read": {**body["read"], "references": {
            **body["read"].get("references", {}),
            **{ref: run.run_files[value["file"]] for ref, value in shape["references"].items()}}}}
    contract = run.store.put(run.inputs, body)
    if "pieces" in shape:
        if run.by_name[shape["pieces"]["step"]]["operation"] != "source.combine":
            raise ValueError(f"Step {name}: pieces are read from a source.combine step")
        (before,) = units[shape["pieces"]["step"]]
        return [unit(f"{run.root}/{name}/reading.json", {"unit": name}, {"compose": {
            "document": {"version": 4, "contract": contract, "pieces": {"slot": "pieces"}},
            "slots": {"pieces": {"step": shape["pieces"]["step"], "key": before["keys"]["unit"]}}}})]
    keys = [key for key in run.keys if fnmatch.fnmatchcase(key, shape.get("files", "*"))]
    if not keys:
        raise ValueError(f"Step {name}: no document of the bundle matches {shape.get('files', '*')!r}")
    lookups = shape.get("lookups", {})
    from_files = bool(lookups) and all("file" in value for value in lookups.values())
    for value in ([] if from_files else lookups.values()):
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
                    value_name: fill(template, key, run.facts) for value_name, template in shape.get("context", {}).items()}})
            if from_files:  # each set given whole by a run file
                artifact["lookups"] = run.store.put(run.inputs, {"version": 1, "input": source, "sets": {
                    set_name: run.run_files[value["file"]] for set_name, value in lookups.items()}})
            elif lookups:
                slot = f"file_{position}"
                artifact["lookups"] = {"slot": slot}
                slots[slot] = {"compose": {
                    "document": {"version": 2, "input": source, "sets": {
                        set_name: {"readings": [{"slot": set_name}],
                                   **{k: v for k, v in value.items() if k != "from"}}
                        for set_name, value in lookups.items()}},
                    "slots": {set_name: {"step": value["from"], "key": pair(key)}
                              for set_name, value in lookups.items()}}}
            artifacts.append(artifact)
        document = raw_capture.request(contract, artifacts)
        output = f"{run.root}/{name}/{label}.reading.json"
        source = {"compose": {"document": document, "slots": slots}} if slots else run.store.put(run.inputs, document)
        found.append(unit(output, {"unit": key_of_unit}, source))
    return found
