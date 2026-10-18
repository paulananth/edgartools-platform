"""source.combine: declared keyed collections and joins over pinned readings.

Domain-free preparation between source.read and mdm.prepare. Every input,
contract and result is an immutable receipt; a verifier rebuilds exact bytes.
"""
from __future__ import annotations

import io
import hashlib
import json
from pathlib import Path

import edgar_warehouse.bookkeeping.clean.artifacts as artifact_store
from edgar_warehouse import control_contract
from edgar_warehouse.control_contract import canonical, reference
from . import Redo, source_readings, source_reduction

CHECK = "source.combined"
# Bounds, not budgets (ticket 83): an output over the index bound is written in
# pieces, so neither the inputs nor the output are refused for their size.
INPUT_BYTES = 16 * 1024**3
TOTAL_BYTES = 16 * 1024**3
OUTPUT_BYTES = source_readings.INDEX_BYTES
MAX_ROWS = 40_000_000
NAME = source_readings.NAME
COLLECTION_MODES = frozenset(("collect", "collect_flat"))
ARTIFACT_CODEC_FILE = Path(artifact_store.__file__).with_name("config.py")


def runtime_files() -> list[Path]:
    from edgar_warehouse.rules.source_engine import runtime_files as engine_files
    return [Path(artifact_store.__file__), ARTIFACT_CODEC_FILE, Path(control_contract.__file__), Path(source_readings.__file__),
            Path(source_reduction.__file__), *engine_files()]


def _name(value):
    return isinstance(value, str) and NAME.fullmatch(value) is not None


def _mapping(value, maximum, label):
    if not isinstance(value, dict) or len(value) > maximum or not all(_name(k) for k in value):
        raise ValueError(f"{label} must be a named mapping of at most {maximum} entries")
    return value


def _sources(spec):
    return [spec["source"]] if isinstance(spec["source"], str) else spec["source"]


def _selection(spec, inputs):
    names = _sources(spec)
    if (not isinstance(names, list) or not 1 <= len(names) <= 8
            or not all(_name(name) and name in inputs for name in names)
            or len(set(names)) != len(names) or not _name(spec["table"])):
        raise ValueError("Combination selects distinct declared readings and a named table")
    _mapping(spec["checks"], 32, "Row checks")
    _mapping(spec["where"], 32, "Row filter")


def _contract(body, inputs):
    if (not isinstance(body, dict) or set(body) != {"execution", "combine"}
            or body["execution"] != {"profile": "source.combine"}):
        raise ValueError("Combination contract names execution profile source.combine and combine only")
    plan = body["combine"]
    if (not isinstance(plan, dict) or set(plan) != {"max_rows", "groups", "tables"}
            or type(plan["max_rows"]) is not int or not 1 <= plan["max_rows"] <= MAX_ROWS):
        raise ValueError(f"Combination names max_rows 1..{MAX_ROWS}, groups and tables")
    groups = _mapping(plan["groups"], 32, "Groups")
    for spec in groups.values():
        required = {"source", "table", "key", "value", "mode", "order_by", "distinct", "skip_null_values", "checks", "where"}
        if not isinstance(spec, dict) or not required <= set(spec) or set(spec) - required - {"sort_values", "skip_empty_text"}:
            raise ValueError("Group requires source, table, key, value, mode, order_by, distinct, skip_null_values, checks and where")
        _selection(spec, inputs)
        if not _name(spec["key"]) or not (_name(spec["value"]) or spec["value"] == "."):
            raise ValueError("Group key/value are column names; value may be the whole row (.)")
        if spec["mode"] not in ("collect", "collect_flat", "first", "last", "one"):
            raise ValueError("Group mode is collect, collect_flat, first, last or one")
        if not isinstance(spec["order_by"], list) or len(spec["order_by"]) > 8 or not all(_name(k) for k in spec["order_by"]):
            raise ValueError("Group order_by names at most eight columns")
        if type(spec["distinct"]) is not bool or type(spec["skip_null_values"]) is not bool or (spec["mode"] not in COLLECTION_MODES and spec["distinct"]):
            raise ValueError("Group flags are booleans; distinct requires collect or collect_flat")
        if 'skip_empty_text' in spec and (type(spec['skip_empty_text']) is not bool or spec['mode'] not in COLLECTION_MODES):
            raise ValueError('skip_empty_text requires a boolean and a collection mode')
        if 'sort_values' in spec and (type(spec['sort_values']) is not bool or spec['mode'] not in COLLECTION_MODES):
            raise ValueError('sort_values requires a boolean and a collection mode')
    tables = _mapping(plan["tables"], 16, "Output tables")
    if not tables:
        raise ValueError("Combination requires an output table")
    for spec in tables.values():
        required = {"source", "table", "checks", "where", "joins"}
        if not isinstance(spec, dict) or not required <= set(spec) or set(spec) - required - {"drop"}:
            raise ValueError("Output table requires source, table, checks, where and joins")
        _selection(spec, inputs)
        if "drop" in spec and (not isinstance(spec['drop'],list) or len(spec['drop']) > 64
                or any(not _name(name) for name in spec['drop']) or len(set(spec['drop'])) != len(spec['drop'])):
            raise ValueError("Output drop names at most 64 distinct columns")
        for join in _mapping(spec["joins"], 32, "Joins").values():
            required = {"group", "key", "on_missing", "replace"}
            if not isinstance(join, dict) or not required <= set(join) or set(join) - required - {"path"}:
                raise ValueError("Join requires group, key, on_missing and replace")
            if not _name(join["group"]) or join["group"] not in groups or not _name(join["key"]) or join["on_missing"] not in ("empty", "error", "skip") or type(join["replace"]) is not bool:
                raise ValueError("Join declares a group, key, empty/error policy and boolean replace")
            if 'path' in join and (not isinstance(join['path'],list) or not 1 <= len(join['path']) <= 8
                    or any(not _name(name) for name in join['path'])):
                raise ValueError("Join path names 1..8 nested object fields")
    return plan


def _reading(data):
    body = artifact_store.json_value(data)
    return _reading_body(body)


def _reading_body(body):
    if (not isinstance(body, dict) or type(body.get("version")) is not int or body["version"] != 1
            or not isinstance(body.get("artifacts"), list) or not body["artifacts"]):
        raise ValueError("Combination input is a version-1 reading with artifacts")
    rows = 0
    for artifact in body["artifacts"]:
        if not isinstance(artifact, dict) or not isinstance(artifact.get("tables"), dict):
            raise ValueError("Combination artifact must hold tables")
        reference(artifact.get("input"))
        if not isinstance(artifact.get("deferred"), list) or artifact["deferred"]:
            raise ValueError("Combination requires explicitly resolved deferred records")
        for table, records in artifact["tables"].items():
            if not _name(table) or not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
                raise ValueError("Combination tables contain object rows")
            rows += len(records)
    return body, rows


def _encode(body, max_bytes=None):
    """The body's bytes, refused past `max_bytes` (a reduction's declared output bound)."""
    buffer = io.BytesIO()
    for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).iterencode(body):
        data = chunk.encode()
        if max_bytes is not None and buffer.tell() + len(data) > max_bytes:
            raise ValueError("Combined reading exceeds its declared output byte bound")
        buffer.write(data)
    return buffer.getvalue()


def _checked(envelope, artifacts):
    """The combination's inputs and contract, checked without combining:
    (manifest, source-extract receipts, plan, whether the contract reduces)."""
    if set(envelope["checks"]) != {CHECK}:
        raise ValueError("source.combine verifies source.combined only")
    keys = envelope.get("keys", {})
    predecessor_keys = {"combine_contract_uri", "combine_contract_sha256", "reading_name"}
    extra_keys = {"readings_uri", "readings_sha256"}
    if (predecessor_keys | extra_keys) & set(keys):
        if (not predecessor_keys <= set(keys) or not _name(keys["reading_name"])
                or not all(isinstance(keys[key], str) and keys[key] for key in (predecessor_keys | extra_keys) & set(keys))):
            raise ValueError("Predecessor combination requires text contract URI/hash and reading_name")
        refs = {}
        if extra_keys & set(keys):
            if not extra_keys <= set(keys):
                raise ValueError("Additional readings require both readings_uri and readings_sha256")
            refs = _mapping(artifacts.json({"uri": keys["readings_uri"], "sha256": keys["readings_sha256"]}),
                            7, "Additional reading receipts")
        if keys["reading_name"] in refs:
            raise ValueError("Predecessor reading name collides with an additional reading")
        manifest = {"version": 1, "contract": {"uri": keys["combine_contract_uri"], "sha256": keys["combine_contract_sha256"]},
                    "readings": {**refs, keys["reading_name"]: envelope["input"]}}
    else:
        manifest = artifacts.json(envelope["input"])
    if set(manifest) != {"version", "contract", "readings"} or type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ValueError("Combination manifest names version 1, contract and readings")
    refs = _mapping(manifest["readings"], 8, "Reading receipts")
    if not refs:
        raise ValueError("Combination requires reading receipts")
    contract = artifacts.json(manifest["contract"])
    if isinstance(contract, dict) and "reduce" in contract:
        return manifest, refs, source_reduction.contract(contract, refs), True
    return manifest, refs, _contract(contract, refs), False


def _documents(envelope, artifacts, sink):
    manifest, refs, plan, reduced = _checked(envelope, artifacts)
    if reduced:
        tables = source_reduction.tables(plan, refs, artifacts)
        return _output(envelope, manifest, refs, tables, sink, max_bytes=plan["max_output_bytes"])
    inputs, size, count = {}, 0, 0
    for name, value in refs.items():
        listed = []
        for ref in source_readings.receipts(value):  # a name's readings, in order, as one
            body, consumed = source_readings.load(ref, artifacts, max_bytes=INPUT_BYTES, max_rows=plan["max_rows"],
                                                  allow_lookup_receipts=True)
            size += consumed
            if size > TOTAL_BYTES:
                raise ValueError("Combination readings exceed total byte budget")
            reading, rows = _reading_body(body)
            count += rows
            if count > plan["max_rows"]:
                raise ValueError("Combination exceeds input row budget")
            listed.append(reading)
        inputs[name] = listed[0] if len(listed) == 1 else {
            **listed[0], "artifacts": [artifact for reading in listed for artifact in reading["artifacts"]]}
    from edgar_warehouse.rules.source_engine import combine_tables
    tables = combine_tables(plan, inputs, canonical)
    return _output(envelope, manifest, refs, tables, sink)


def _scope(envelope, manifest):
    """The combination's pinned inputs, written beside its output: (receipt, bytes)."""
    scope = canonical(manifest).encode()
    scope_hash = hashlib.sha256(scope).hexdigest()
    return {"uri": f"{envelope['output'].rsplit('/', 1)[0]}/combine-inputs/{scope_hash}.json", "sha256": scope_hash}, scope


def _output(envelope, manifest, refs, tables, sink, *, max_bytes=None):
    """(scope receipt, scope bytes, output bytes). An output over the index
    bound is cut into pieces, each handed to `sink`, behind a version-2 index;
    its scope, which pins the readings, is its one input (ticket 83)."""
    scope_ref, scope = _scope(envelope, manifest)
    output = _encode({"version": 1, "contract": manifest["contract"], "readings": refs,
                      "artifacts": [{"input": scope_ref, "tables": tables, "deferred": []}]}, max_bytes)
    if len(output) <= OUTPUT_BYTES:
        return scope_ref, scope, output
    entry = source_readings.pieces(envelope["output"], {"input": scope_ref}, tables, [],
                                   list(tables), len(output), sink)
    index = _encode({"version": 2, "contract": manifest["contract"], "artifacts": [entry]})
    if len(index) > source_readings.INDEX_BYTES:
        raise ValueError("Combined reading index exceeds its byte bound")
    return scope_ref, scope, index


def execute(envelope, artifacts):
    # Every piece is written as it is made, before the index that names it.
    scope_ref, scope, output = _documents(envelope, artifacts, source_readings.publish(artifacts))
    artifacts.put_bytes(scope_ref["uri"], scope)
    return artifacts.put_bytes(envelope["output"], output)


def verify(envelope, artifacts):
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from intended combined output")
    scope_ref, scope, expected = _documents(envelope, artifacts, source_readings.check(artifacts))
    if artifacts.verified(scope_ref, max_bytes=source_readings.INDEX_BYTES) != scope:
        raise ValueError("Written combination scope differs from pinned inputs")
    if artifacts.verified(envelope["candidate"], max_bytes=source_readings.INDEX_BYTES) != expected:
        raise ValueError("Written combined reading differs from pinned inputs and configuration")
    return {CHECK: True}, []


def confirm(envelope, artifacts):
    """The check without combining again (ticket 72). The inputs and contract
    pass the step's own checks, the written scope equals these inputs, and the
    written output parses as one combination of this contract and these
    receipts, holding only the contract's tables within its output bounds.
    Bookkeeping pins the worker's runtime for the run and hashes the input and
    the output; the check loop still redoes a sample of units."""
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from intended combined output")
    manifest, refs, plan, reduced = _checked(envelope, artifacts)
    scope_ref, scope = _scope(envelope, manifest)
    if artifacts.verified(scope_ref, max_bytes=source_readings.INDEX_BYTES) != scope:
        raise ValueError("Written combination scope differs from pinned inputs")
    data = artifacts.verified(envelope["candidate"], max_bytes=source_readings.INDEX_BYTES)
    body = artifact_store.json_value(data)
    if isinstance(body, dict) and body.get("version") == 2:
        raise Redo("a combination written in pieces is checked by redoing it")
    if (not isinstance(body, dict) or set(body) != {"version", "contract", "readings", "artifacts"}
            or body["contract"] != manifest["contract"] or body["readings"] != refs):
        raise ValueError("Written combination does not name this contract and these receipts")
    _, rows = _reading_body(body)
    if [artifact["input"] for artifact in body["artifacts"]] != [scope_ref]:
        raise ValueError("Written combination does not name its scope")
    if not set(body["artifacts"][0]["tables"]) <= set(plan["groups"] if reduced else plan["tables"]):
        raise ValueError("Written combination holds tables the contract does not declare")
    if reduced and rows > plan["max_output_rows"]:
        raise ValueError("Written combination exceeds the contract's output rows")
    return {CHECK: True}, []
