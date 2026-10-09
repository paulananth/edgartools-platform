"""source.read: a hash-pinned YAML contract and at most two captured artifacts.

Runs configured Rust parsing through Python; no discovery, acquisition or
mastering. Bookkeeping sees only task envelopes and immutable output receipts.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import edgar_warehouse.bookkeeping.clean.artifacts as artifact_store
import edgar_warehouse.control_contract as control_contract
from edgar_warehouse.rules import files, source_engine
from edgar_warehouse.control_contract import canonical, reference
from . import source_stream, source_readings, source_parquet

OUTPUT_BYTES = 128 * 1024**2
# Capture the actual loaded codec location; later wrapper metadata changes
# do not relocate this dependency.
ARTIFACT_CODEC_FILE = Path(artifact_store.__file__).with_name("config.py")


def runtime_files() -> list[Path]:
    """Pin the facade, value registry and loaded Rust extension with this worker."""
    return [*source_engine.runtime_files(), Path(files.__file__), Path(artifact_store.__file__),
            Path(source_stream.__file__), Path(source_readings.__file__),
            Path(source_parquet.__file__), *source_parquet.runtime_files(),
            # Artifacts' codec dependency is pinned as bytes, without importing
            # Bookkeeping control internals into the worker's execution surface.
            ARTIFACT_CODEC_FILE, Path(control_contract.__file__)]


def _documents(envelope: dict, artifacts):
    if set(envelope["checks"]) != {"source.output"}:
        raise ValueError("source.read verifies source.output only")
    manifest = artifacts.json(envelope["input"])
    if (set(manifest) != {"version", "contract", "artifacts"}
            or type(manifest["version"]) is not int or manifest["version"] not in (1, 2, 3)):
        raise ValueError("Source input names version 1, 2 or 3, contract and artifacts")
    contract = files.loads(artifacts.verified(manifest["contract"], max_bytes=1024**2).decode("utf-8"))
    execution = contract.get("execution")
    required = {"profile", "workers", "max_artifacts"}
    if (not isinstance(execution, dict) or not required <= set(execution)
            or set(execution) - required - {"input_sha256s", "max_input_bytes"}
            or execution["profile"] != "source.read"
            or any(type(execution[key]) is not int or not 1 <= execution[key] <= 2
                   for key in ("workers", "max_artifacts"))):
        raise ValueError("Source execution requires source.read with 1..2 workers and artifacts")
    if "max_input_bytes" in execution and (type(execution['max_input_bytes']) is not int
            or not 1 <= execution['max_input_bytes'] <= 256*1024**2):
        raise ValueError('Source max_input_bytes is 1..256 MiB')
    read = contract.get("read")
    if "max_input_bytes" in execution and isinstance(read, dict) and "stream" in read:
        raise ValueError('Streamed framing declares its own physical input bounds')
    inputs = manifest["artifacts"]
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= execution["max_artifacts"]:
        raise ValueError("Source input exceeds the contract's bounded artifact count")
    for entry in inputs:
        _entry(manifest, entry)
    if "input_sha256s" in execution:
        pins = execution["input_sha256s"]
        if not isinstance(pins,list) or len(pins) != len(inputs):
            raise ValueError("Source input_sha256s pins every artifact in order")
        for pin,entry in zip(pins,inputs):
            reference({"uri":"approved-input", "sha256":pin})
            entry = _entry(manifest, entry)
            if reference(entry)["sha256"] != pin:
                raise ValueError("Source input differs from approved artifact hash")
    return manifest, contract, execution, inputs


def _entry(manifest, entry):
    if manifest["version"] == 1:
        return reference(entry)
    required = {"input", "context"} | ({"lookups"} if manifest["version"] == 3 else set())
    if not isinstance(entry, dict) or set(entry) != required:
        raise ValueError(f"Version-{manifest['version']} source artifact names exact input/context"
                         + ("/lookup receipts" if manifest["version"] == 3 else " receipts"))
    for receipt in entry.values():
        reference(receipt)
    return entry["input"]


def _lookups(manifest, entry, artifacts, contract):
    """Authenticate a bounded immutable indexed scope before opening its source."""
    declared = contract["read"].get("lookup_sets", {})
    if manifest["version"] != 3:
        if declared:
            raise ValueError("Declared lookup sets require a version-3 input receipt")
        return {}, {}
    ref = _entry(manifest, entry)
    bound = artifact_store.json_value(artifacts.verified(entry["lookups"], max_bytes=64 * 1024**2))
    if (not isinstance(bound, dict) or set(bound) != {"version", "input", "sets"}
            or type(bound["version"]) is not int or bound["version"] not in (1, 2)
            or bound["input"] != ref or not isinstance(bound["sets"], dict)
            or set(bound["sets"]) != set(declared)):
        raise ValueError("Lookup document binds exactly declared sets to the input receipt")
    sets = (bound["sets"] if bound["version"] == 1
            else _derived_sets(bound["sets"], declared, artifacts))
    total = 0
    for name, values in sets.items():
        spec = declared[name]
        if not isinstance(values, list) or len(values) > spec["max_values"]:
            raise ValueError("Lookup raw values exceed their declared count or list shape")
        size = 0
        for value in values:
            if not isinstance(value, str):
                raise ValueError("Lookup values require exact text")
            length = len(value.encode("utf-8"))
            if length > spec["max_value_bytes"]:
                raise ValueError("Lookup value exceeds its declared UTF-8 bound")
            size += length
            if size > spec["max_bytes"]:
                raise ValueError("Lookup raw values exceed their declared UTF-8 byte bound")
        total += size
        if total > 64 * 1024**2:
            raise ValueError("Lookup sets exceed the aggregate UTF-8 byte bound")
    return sets, {"lookups": entry["lookups"]}


def _derived_sets(specs, declared, artifacts):
    """Exhaust authenticated producer readings before making indexed scopes.

    Values stay raw until the existing count/UTF-8 bounds validate them;
    duplicate rows therefore cannot evade those limits through deduplication.
    """
    result = {}
    named = lambda value: isinstance(value, str) and source_readings.NAME.fullmatch(value) is not None
    for name, spec in specs.items():
        required = {"readings", "table", "column", "max_input_bytes", "max_input_rows"}
        if (not isinstance(spec, dict) or set(spec) != required
                or not isinstance(spec["readings"], list) or not 1 <= len(spec["readings"]) <= 256
                or not named(spec["table"]) or not named(spec["column"])
                or type(spec["max_input_bytes"]) is not int or not 1 <= spec["max_input_bytes"] <= 64 * 1024**2
                or type(spec["max_input_rows"]) is not int or not 1 <= spec["max_input_rows"] <= 100000):
            raise ValueError("Derived lookup requires complete readings, named table/column and explicit bounds")
        for ref in spec["readings"]:
            reference(ref)
        values, consumed, rows, size = [], 0, 0, 0
        bounds = declared[name]
        for ref in spec["readings"]:
            used = 0
            for _, _, chunk, used in source_readings.iter_load(
                    ref, artifacts, max_bytes=spec["max_input_bytes"] - consumed,
                    max_rows=spec["max_input_rows"] - rows, allow_lookup_receipts=True):
                if chunk["deferred"] or spec["table"] not in chunk["tables"]:
                    raise ValueError("Derived lookup requires resolved records and its declared table")
                rows += sum(len(table) for table in chunk["tables"].values())
                for row in chunk["tables"][spec["table"]]:
                    value = row.get(spec["column"])
                    if not isinstance(value, str):
                        raise ValueError("Derived lookup columns require present exact text")
                    length = len(value.encode("utf-8"))
                    if (len(values) >= bounds["max_values"] or length > bounds["max_value_bytes"]
                            or size + length > bounds["max_bytes"]):
                        raise ValueError("Derived lookup exceeds declared raw value bounds")
                    values.append(value)
                    size += length
            consumed += used
        result[name] = values
    return result


def _context(manifest, entry, artifacts):
    if manifest["version"] == 1:
        return entry, {}, {}
    ref = _entry(manifest, entry)
    bound = artifact_store.json_value(artifacts.verified(entry["context"], max_bytes=32 * 1024))
    if (not isinstance(bound, dict) or type(bound.get("version")) is not int
            or bound.get("input") != ref):
        raise ValueError("Context document must bind its values to the exact input receipt")
    if bound["version"] == 1:
        if set(bound) != {"version", "input", "values"} or not isinstance(bound["values"], dict):
            raise ValueError("Context document must bind its values to the exact input receipt")
        values = bound["values"]
    elif bound["version"] == 2:
        values = _derived_context(bound, artifacts)
    else:
        raise ValueError("Context document requires version 1 or 2")
    return ref, values, {"context": entry["context"]}


def _derived_context(bound, artifacts):
    """Use one verified producer row, after complete traversal and checks."""
    required = {"version", "input", "reading", "table", "columns", "checks", "max_bytes", "max_rows"}
    if set(bound) != required:
        raise ValueError("Derived context requires exact reading, table, columns, checks and limits")
    reference(bound["reading"])
    named = lambda value: isinstance(value, str) and source_readings.NAME.fullmatch(value) is not None
    if (not named(bound["table"]) or not isinstance(bound["columns"], dict)
            or not 1 <= len(bound["columns"]) <= 64
            or not all(named(name) and named(column) for name, column in bound["columns"].items())
            or not isinstance(bound["checks"], dict) or not 1 <= len(bound["checks"]) <= 64
            or not all(named(name) for name in bound["checks"])
            or type(bound["max_bytes"]) is not int or not 1 <= bound["max_bytes"] <= 64 * 1024**2
            or type(bound["max_rows"]) is not int or not 1 <= bound["max_rows"] <= 100000):
        raise ValueError("Derived context has invalid named fields or explicit bounds")
    checks = {}
    input_checks = set()
    for column, expected in bound["checks"].items():
        if isinstance(expected, dict):
            if set(expected) == {"column"} and named(expected["column"]):
                checks[column] = expected
                continue
            if set(expected) != {"input"} or expected["input"] not in ("uri", "sha256"):
                raise ValueError("Derived context check requires a scalar or exact input identity field")
            input_checks.add(expected["input"])
            expected = bound["input"][expected["input"]]
        elif expected is not None and type(expected) not in (str, bool, int):
            raise ValueError("Derived context checks compare exact JSON scalars")
        checks[column] = expected
    if input_checks != {"uri", "sha256"}:
        raise ValueError("Derived context must check producer columns against exact input URI and hash")
    selected = None
    for _, _, chunk, _ in source_readings.iter_load(
            bound["reading"], artifacts, max_bytes=bound["max_bytes"],
            max_rows=bound["max_rows"], allow_lookup_receipts=True):
        if chunk["deferred"] or bound["table"] not in chunk["tables"]:
            raise ValueError("Derived context requires resolved records and a declared metadata table")
        for row in chunk["tables"][bound["table"]]:
            for column, expected in checks.items():
                if isinstance(expected, dict):
                    other = expected["column"]
                    if other not in row:
                        raise ValueError("Derived context check names a missing comparison column")
                    expected = row[other]
                if expected is not None and type(expected) not in (str, bool, int):
                    raise ValueError("Derived context comparison columns require scalar values")
                if column not in row or canonical(row[column]) != canonical(expected):
                    raise ValueError(f"Derived context producer check failed: {column}")
            if selected is not None:
                raise ValueError("Derived context requires exactly one metadata row")
            selected = {}
            for name, column in bound["columns"].items():
                if column not in row or (row[column] is not None and type(row[column]) not in (str, bool, int)):
                    raise ValueError("Derived context values require present scalar columns")
                selected[name] = row[column]
    if selected is None:
        raise ValueError("Derived context requires exactly one metadata row")
    if len(canonical(selected).encode()) > 32 * 1024:
        raise ValueError("Derived context values exceed scalar byte budget")
    return selected


def _output(envelope: dict, artifacts, documents=None) -> bytes:
    manifest, contract, execution, inputs = documents or _documents(envelope, artifacts)
    read = contract.get("read")
    parquet = isinstance(read, dict) and read.get("format") == "parquet"
    engine = source_engine.SourceEngine(source_parquet.engine_contract(contract) if parquet else contract)
    max_bytes = contract["read"].get("limits", {}).get("max_bytes", 32 * 1024**2)
    max_records = contract["read"].get("limits", {}).get("max_records")
    if max_bytes > execution.get("max_input_bytes", 32 * 1024**2):
        raise ValueError("source.read accepts at most 32 MiB per artifact")
    if type(max_records) is not int or not 1 <= max_records <= 100000:
        raise ValueError("source.read requires a limit of at most 100000 records")

    def read(entry):
        ref, context, evidence = _context(manifest, entry, artifacts)
        lookups, lookup_evidence = _lookups(manifest, entry, artifacts, contract)
        evidence.update(lookup_evidence)
        data = artifacts.verified(ref, max_bytes=execution.get("max_input_bytes", max_bytes))
        result = engine.read(source_parquet.document(data, contract) if parquet else data,
                             context=context, lookups=lookups)
        return {"input": ref, **evidence, "tables": result.tables, "deferred": result.deferred}

    with ThreadPoolExecutor(max_workers=execution["workers"]) as pool:
        readings = list(pool.map(read, inputs))
    output = json.dumps({"version": 1, "contract": manifest["contract"], "artifacts": readings},
                      sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(output) > OUTPUT_BYTES:
        raise ValueError("source.read output exceeds the verifier byte budget; partition the inputs")
    return output


def execute(envelope: dict, artifacts) -> dict:
    documents = _documents(envelope, artifacts)
    read = documents[1].get("read")
    if isinstance(read, dict) and "stream" in read:
        output = source_stream.output(envelope, artifacts, documents, _context, _lookups, publish=True,
                                      max_index_bytes=OUTPUT_BYTES)
    else:
        output = _output(envelope, artifacts, documents)
    return artifacts.put_bytes(envelope["output"], output)


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    documents = _documents(envelope, artifacts)
    read = documents[1].get("read")
    if isinstance(read, dict) and "stream" in read:
        expected = source_stream.output(envelope, artifacts, documents, _context, _lookups, publish=False,
                                        max_index_bytes=OUTPUT_BYTES)
    else:
        expected = _output(envelope, artifacts, documents)
    found = artifacts.verified(envelope["candidate"], max_bytes=OUTPUT_BYTES)
    if found != expected:
        raise ValueError("Written source output differs from the configured reading")
    return {name: True for name in envelope["checks"]}, []
