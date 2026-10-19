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
    return {"keys": {**keys, "destination": output}, "input": source, "output": output, "cursor": {}}


def fill(template, key: str):
    """A template filled for one document; a literal stays as it is."""
    if not isinstance(template, str):
        return template
    folder, name = posixpath.split(key)
    return template.replace("{dir}", folder).replace("{base}", name.split(".", 1)[0]).replace("{name}", name)


def pair(key: str) -> str:
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


def _document(step: dict, run, key: str) -> dict:
    """What one document is read as: itself, or its companion."""
    beside = step.get("input", {}).get("beside")
    if beside is None:
        return raw_capture.document(run.folder, run.receipts, key)
    companion = fill(beside["path"], key)
    sha256 = run.rows[key].get(beside["sha256"])
    if not isinstance(sha256, str):
        raise ValueError(f"Step {step['name']}: the receipt of {key} holds no {beside['sha256']}")
    return raw_capture.verified(run.folder, companion, sha256)[0]


def form(step: dict, run, units: dict) -> list[dict]:
    """The units of one `source.read` step."""
    name, shape = step["name"], step.get("input", {})
    contract = run.store.put(run.inputs, run.contracts[shape.get("contract", "source.yaml")])
    if "pieces" in shape:
        if step.get("units", "one") != "one":
            raise ValueError(f"Step {name}: a read of pieces is one unit")
        (before,) = units[shape["pieces"]["step"]]
        return [unit(f"{run.root}/{name}/reading.json", {"unit": name}, {"compose": {
            "document": {"version": 4, "contract": contract, "pieces": {"slot": "pieces"}},
            "slots": {"pieces": {"step": shape["pieces"]["step"], "key": before["keys"]["unit"]}}}})]
    keys = [key for key in run.keys if fnmatch.fnmatchcase(key, shape.get("files", "*"))]
    if not keys:
        raise ValueError(f"Step {name}: no document of the bundle matches {shape.get('files', '*')!r}")
    lookups = shape.get("lookups", {})
    for value in lookups.values():
        if run.by_name[value["from"]].get("units") != {"each": "file"}:
            raise ValueError(f"Step {name}: a lookup reads the same file's unit of a step whose units are each file")
    if lookups and "groups" not in step.get("units", {}) and step.get("units") != {"each": "file"}:
        raise ValueError(f"Step {name}: a read with lookups is cut into groups or each file (a slot per file)")
    found = []
    for key_of_unit, label, documents in _cut(step, run, keys):
        artifacts, slots = [], {}
        for position, key in enumerate(documents):
            source = _document(step, run, key)
            artifact = {"input": source}
            if "context" in shape:
                artifact["context"] = run.store.put(run.inputs, {"version": 1, "input": source, "values": {
                    value_name: fill(template, key) for value_name, template in shape["context"].items()}})
            if lookups:
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
        # As raw_capture.read_unit: lookups make a version-3 request, a context version 2.
        version = 3 if lookups else 2 if "context" in shape else 1
        document = {"version": version, "contract": contract,
                    "artifacts": artifacts if version > 1 else [a["input"] for a in artifacts]}
        output = f"{run.root}/{name}/{label}.reading.json"
        source = {"compose": {"document": document, "slots": slots}} if slots else run.store.put(run.inputs, document)
        found.append(unit(output, {"unit": key_of_unit}, source))
    return found
