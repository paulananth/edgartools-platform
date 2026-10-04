"""source.combine: declared keyed collections and joins over pinned readings.

Domain-free preparation between source.read and mdm.prepare. Every input,
contract and result is an immutable receipt; a verifier rebuilds exact bytes.
"""
from __future__ import annotations

import io
import hashlib
import json
import re
from pathlib import Path

import edgar_warehouse.bookkeeping.clean.artifacts as artifact_store
from edgar_warehouse import control_contract
from edgar_warehouse.control_contract import canonical, reference

CHECK = "source.combined"
INPUT_BYTES = 32 * 1024**2
TOTAL_BYTES = 64 * 1024**2
OUTPUT_BYTES = 32 * 1024**2
MAX_ROWS = 100_000
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
COLLECTION_MODES = frozenset(("collect", "collect_flat"))


def runtime_files() -> list[Path]:
    return [Path(artifact_store.__file__), Path(control_contract.__file__)]


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
        raise ValueError("Combination names max_rows 1..100000, groups and tables")
    groups = _mapping(plan["groups"], 32, "Groups")
    for spec in groups.values():
        required = {"source", "table", "key", "value", "mode", "order_by", "distinct", "skip_null_values", "checks", "where"}
        if not isinstance(spec, dict) or not required <= set(spec) or set(spec) - required - {"sort_values"}:
            raise ValueError("Group requires source, table, key, value, mode, order_by, distinct, skip_null_values, checks and where")
        _selection(spec, inputs)
        if not _name(spec["key"]) or not (_name(spec["value"]) or spec["value"] == "."):
            raise ValueError("Group key/value are column names; value may be the whole row (.)")
        if spec["mode"] not in ("collect", "collect_flat", "first", "last"):
            raise ValueError("Group mode is collect, collect_flat, first or last")
        if not isinstance(spec["order_by"], list) or len(spec["order_by"]) > 8 or not all(_name(k) for k in spec["order_by"]):
            raise ValueError("Group order_by names at most eight columns")
        if type(spec["distinct"]) is not bool or type(spec["skip_null_values"]) is not bool or (spec["mode"] not in COLLECTION_MODES and spec["distinct"]):
            raise ValueError("Group flags are booleans; distinct requires collect or collect_flat")
        if 'sort_values' in spec and (type(spec['sort_values']) is not bool or spec['mode'] not in COLLECTION_MODES):
            raise ValueError('sort_values requires a boolean and a collection mode')
    tables = _mapping(plan["tables"], 16, "Output tables")
    if not tables:
        raise ValueError("Combination requires an output table")
    for spec in tables.values():
        if not isinstance(spec, dict) or set(spec) != {"source", "table", "checks", "where", "joins"}:
            raise ValueError("Output table requires source, table, checks, where and joins")
        _selection(spec, inputs)
        for join in _mapping(spec["joins"], 32, "Joins").values():
            if not isinstance(join, dict) or set(join) != {"group", "key", "on_missing", "replace"}:
                raise ValueError("Join requires group, key, on_missing and replace")
            if not _name(join["group"]) or join["group"] not in groups or not _name(join["key"]) or join["on_missing"] not in ("empty", "error") or type(join["replace"]) is not bool:
                raise ValueError("Join declares a group, key, empty/error policy and boolean replace")
    return plan


def _column(row, name):
    if name not in row:
        raise ValueError(f"Combination row has no column {name}")
    return row[name]


def _key(value):
    if value is None:
        return None
    if type(value) not in (str, int):
        raise ValueError("Combination keys must be text, integer or null; no implicit conversion")
    return type(value).__name__, value


def _rows(spec, inputs):
    for source in _sources(spec):
        for artifact in inputs[source]["artifacts"]:
            rows = artifact["tables"].get(spec["table"])
            if rows is None:
                raise ValueError(f"Combination reading has no table {spec['table']}")
            for row in rows:
                for column, expected in spec["checks"].items():
                    if canonical(_column(row, column)) != canonical(expected):
                        raise ValueError(f"Combination row check failed: {column}")
                selected = [canonical(_column(row, column)) == canonical(expected)
                            for column, expected in spec["where"].items()]
                if all(selected):
                    yield row


def _group(spec, inputs, maximum=MAX_ROWS):
    grouped, kinds = {}, {}
    flattened = 0
    for row in _rows(spec, inputs):
        key = _key(_column(row, spec["key"]))
        if key is None:
            continue
        value = row if spec["value"] == "." else _column(row, spec["value"])
        if value is None and spec["skip_null_values"]:
            continue
        if spec["mode"] == "collect_flat" and not isinstance(value, list):
            raise ValueError("collect_flat requires list values; it flattens exactly one level")
        if spec["mode"] == "collect_flat":
            flattened += len(value)
            if flattened > maximum:
                raise ValueError("collect_flat exceeds the declared element budget")
        order = []
        for column in spec["order_by"]:
            item = _column(row, column)
            if type(item) not in (str, int, float, bool) or kinds.setdefault(column, type(item)) is not type(item):
                raise ValueError("Ordering columns must have one exact scalar type and no nulls")
            order.append(item)
        grouped.setdefault(key, []).append((order, value))
    result = {}
    for key, pairs in grouped.items():
        if spec["order_by"]:
            pairs.sort(key=lambda pair: pair[0])
        values, seen = [], set()
        for _, value in pairs:
            items = value if spec["mode"] == "collect_flat" else [value]
            for item in items:
                if spec["distinct"]:
                    token = canonical(item)
                    if token in seen:
                        continue
                    seen.add(token)
                values.append(item)
        if spec.get('sort_values', False):
            if values and (type(values[0]) not in (str, int, float, bool)
                           or any(type(item) is not type(values[0]) for item in values)):
                raise ValueError('sort_values requires one exact scalar type and no nulls')
            values.sort()
        result[key] = values if spec["mode"] in COLLECTION_MODES else values[0 if spec["mode"] == "first" else -1]
    return result


def _reading(data):
    body = artifact_store.json_value(data)
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


def _encode(body):
    """Bound output before publishing, including repeated joined collections."""
    buffer = io.BytesIO()
    for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).iterencode(body):
        data = chunk.encode()
        if buffer.tell() + len(data) > OUTPUT_BYTES:
            raise ValueError("Combined reading exceeds output byte budget; partition inputs")
        buffer.write(data)
    return buffer.getvalue()


def _documents(envelope, artifacts):
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
    plan = _contract(contract, refs)
    inputs, size, count = {}, 0, 0
    for name, ref in refs.items():
        data = artifacts.verified(ref, max_bytes=INPUT_BYTES)
        size += len(data)
        if size > TOTAL_BYTES:
            raise ValueError("Combination readings exceed total byte budget")
        reading, rows = _reading(data)
        count += rows
        if count > plan["max_rows"]:
            raise ValueError("Combination exceeds input row budget")
        inputs[name] = reading
    groups = {name: _group(spec, inputs, plan['max_rows']) for name, spec in plan["groups"].items()}
    tables, count = {}, 0
    for name, spec in plan["tables"].items():
        result = []
        for row in _rows(spec, inputs):
            output = dict(row)
            for field, join in spec["joins"].items():
                if field in output and not join["replace"]:
                    raise ValueError(f"Join would overwrite column {field}; declare replace explicitly")
                key = _key(_column(row, join["key"]))
                group = groups[join["group"]]
                if key not in group:
                    if join["on_missing"] == "error":
                        raise ValueError(f"No combination group match for {field}")
                    output[field] = [] if plan["groups"][join["group"]]["mode"] in COLLECTION_MODES else None
                else:
                    output[field] = group[key]
            result.append(output)
            count += 1
            if count > plan["max_rows"]:
                raise ValueError("Combination exceeds output row budget")
        tables[name] = result
    scope = canonical(manifest).encode()
    scope_hash = hashlib.sha256(scope).hexdigest()
    scope_ref = {"uri": f"{envelope['output'].rsplit('/', 1)[0]}/combine-inputs/{scope_hash}.json", "sha256": scope_hash}
    output = _encode({"version": 1, "contract": manifest["contract"], "readings": refs,
                      "artifacts": [{"input": scope_ref, "tables": tables, "deferred": []}]})
    return scope_ref, scope, output


def execute(envelope, artifacts):
    scope_ref, scope, output = _documents(envelope, artifacts)
    artifacts.put_bytes(scope_ref["uri"], scope)
    return artifacts.put_bytes(envelope["output"], output)


def verify(envelope, artifacts):
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from intended combined output")
    scope_ref, scope, expected = _documents(envelope, artifacts)
    if artifacts.verified(scope_ref, max_bytes=INPUT_BYTES) != scope:
        raise ValueError("Written combination scope differs from pinned inputs")
    if artifacts.verified(envelope["candidate"], max_bytes=OUTPUT_BYTES) != expected:
        raise ValueError("Written combined reading differs from pinned inputs and configuration")
    return {CHECK: True}, []
