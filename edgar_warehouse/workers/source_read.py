"""source.read: a hash-pinned YAML contract and at most two captured artifacts.

Runs configured Rust parsing through Python; no discovery, acquisition or
mastering. Bookkeeping sees only task envelopes and immutable output receipts.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import edgar_warehouse.bookkeeping.clean.artifacts as artifact_store
import edgar_warehouse.control_contract as control_contract
from edgar_warehouse.rules import files, source_engine
from edgar_warehouse.control_contract import canonical, reference
from . import Redo, source_stream, source_readings, source_parquet, source_traversal

# The whole-output form is kept up to the index bound, the size every consumer
# reads a reading's index under (a reduction refused a 112 MB whole output). A
# larger reading is written in pieces of at most PART_BYTES behind an index
# (ticket 83): no size refusal, and the worker and verifier hold one input's
# reading at a time.
OUTPUT_BYTES = source_readings.INDEX_BYTES
# The ceilings a contract may declare for one file, which is read whole in
# memory (ticket 83: no fixed cap below the machine; a larger file streams).
INPUT_BYTES = 16 * 1024**3
INPUT_RECORDS = 100_000_000
# Public ceiling retained for worker/engine compatibility; enforcement lives
# with Source Extract evidence and is shared by consumers and the worker.
LOOKUP_AGGREGATE_BYTES = source_readings.LOOKUP_AGGREGATE_BYTES
# Capture the actual loaded codec location; later wrapper metadata changes
# do not relocate this dependency.
ARTIFACT_CODEC_FILE = Path(artifact_store.__file__).with_name("config.py")


def runtime_files() -> list[Path]:
    """Pin the facade, value registry and loaded Rust extension with this worker."""
    return [*source_engine.runtime_files(), Path(files.__file__), Path(artifact_store.__file__),
            Path(source_stream.__file__), Path(source_readings.__file__), *source_traversal.runtime_files(),
            Path(source_parquet.__file__), *source_parquet.runtime_files(),
            # Artifacts' codec dependency is pinned as bytes, without importing
            # Bookkeeping control internals into the worker's execution surface.
            ARTIFACT_CODEC_FILE, Path(control_contract.__file__)]


def _pieces(envelope: dict, manifest: dict, artifacts) -> tuple[dict, dict]:
    """Version 4 (ticket 111): one verified reading or combination, read piece by
    piece, so a step after a combine is one unit known before the run. A large
    output's pieces are its parts; a small one's rows are inline, so each becomes
    a file beside this step's output, named by its hash, which the verifier reads
    back by that hash. The worker's own version-1 input, and the inline pieces'
    bytes, written only once the whole input has passed its checks."""
    if set(manifest) != {"version", "contract", "pieces"}:
        raise ValueError("Version-4 source input names its contract and the reading it reads in pieces")
    index = source_readings.index(reference(manifest["pieces"]), artifacts)
    refs, inline = [], {}
    for artifact in index["artifacts"]:
        if index["version"] == 2:
            parts = artifact.get("partitions") if isinstance(artifact, dict) else None
            if not isinstance(parts, list) or any(not isinstance(part, dict) or "receipt" not in part for part in parts):
                raise ValueError("A reading's index names each part by its receipt")
            refs += [reference(part["receipt"]) for part in parts]
            continue
        if (not isinstance(artifact, dict) or not isinstance(artifact.get("tables"), dict)
                or not isinstance(artifact.get("deferred"), list)):
            raise ValueError("A reading's artifact holds its tables and deferred records")
        data = _encode({"version": 1, "tables": artifact["tables"], "deferred": artifact["deferred"]})
        sha = hashlib.sha256(data).hexdigest()
        ref = {"uri": f"{envelope['output']}.pieces/{sha}.json", "sha256": sha}
        inline[ref["uri"]] = (ref, data)
        refs.append(ref)
    # An empty reading has no piece: refused below, as any input naming no file is.
    return {"version": 1, "contract": manifest["contract"], "artifacts": refs}, inline


def _documents(envelope: dict, artifacts, *, publish: bool = False):
    if set(envelope["checks"]) != {"source.output"}:
        raise ValueError("source.read verifies source.output only")
    manifest, inline = artifacts.json(envelope["input"]), {}
    if isinstance(manifest, dict) and manifest.get("version") == 4:
        manifest, inline = _pieces(envelope, manifest, artifacts)
    if (set(manifest) != {"version", "contract", "artifacts"}
            or type(manifest["version"]) is not int or manifest["version"] not in (1, 2, 3)):
        raise ValueError("Source input names version 1, 2 or 3, contract and artifacts")
    contract = files.loads(artifacts.verified(manifest["contract"], max_bytes=1024**2).decode("utf-8"))
    execution = contract.get("execution")
    required = {"profile", "workers", "max_artifacts"}
    if (not isinstance(execution, dict) or not required <= set(execution)
            or set(execution) - required - {"input_sha256s", "max_input_bytes"}
            or execution["profile"] != "source.read"
            or type(execution["workers"]) is not int or not 1 <= execution["workers"] <= 2
            or type(execution["max_artifacts"]) is not int or not 1 <= execution["max_artifacts"] <= source_readings.MAX_ARTIFACTS):
        raise ValueError(f"Source execution requires source.read with 1..2 workers and 1..{source_readings.MAX_ARTIFACTS} artifacts")
    if "max_input_bytes" in execution and (type(execution['max_input_bytes']) is not int
            or not 1 <= execution['max_input_bytes'] <= INPUT_BYTES):
        raise ValueError('Source max_input_bytes is 1..16 GiB')
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
    if publish:  # each inline piece, before the output that names it
        for ref, data in inline.values():
            source_readings.publish(artifacts)(ref, data)
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
    """Validate worker input versions, then authenticate shared lookup evidence."""
    if manifest["version"] != 3:
        if contract["read"].get("lookup_sets", {}):
            raise ValueError("Declared lookup sets require a version-3 input receipt")
        return {}, {}
    ref = _entry(manifest, entry)
    return source_readings.lookup_sets(ref, entry["lookups"], artifacts, contract), {"lookups": entry["lookups"]}


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


def _limits(contract, execution) -> tuple[int, int]:
    """The contract's per-file byte and record limits, within the step's bounds."""
    max_bytes = contract["read"].get("limits", {}).get("max_bytes", 32 * 1024**2)
    max_records = contract["read"].get("limits", {}).get("max_records")
    if max_bytes > execution.get("max_input_bytes", 32 * 1024**2):
        raise ValueError("source.read reads a file of at most its max_input_bytes (32 MiB unless declared)")
    if type(max_records) is not int or not 1 <= max_records <= INPUT_RECORDS:
        raise ValueError(f"source.read requires a limit of 1..{INPUT_RECORDS} records")
    return max_bytes, max_records


def _receipts(manifest, entry) -> dict:
    """The receipts an output artifact names for one input: the file, and its
    context and lookup documents where the manifest version has them."""
    return {"input": _entry(manifest, entry),
            **({"context": entry["context"]} if manifest["version"] >= 2 else {}),
            **({"lookups": entry["lookups"]} if manifest["version"] == 3 else {})}


def _encode(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _output(envelope: dict, artifacts, documents=None, sink=None) -> bytes:
    """The output's bytes: the whole reading, or, past OUTPUT_BYTES, the index
    of its pieces, each handed to `sink` as it is made. Readings are spooled
    to a private file one input at a time, so memory holds one input's
    reading and one piece, never the whole output."""
    manifest, contract, execution, inputs = documents or _documents(envelope, artifacts)
    read = contract.get("read")
    parquet = isinstance(read, dict) and read.get("format") == "parquet"
    engine = source_engine.SourceEngine(source_parquet.engine_contract(contract) if parquet else contract)
    max_bytes, _ = _limits(contract, execution)
    names = list(read["tables"])

    def read_one(entry):
        ref, context, evidence = _context(manifest, entry, artifacts)
        lookups, lookup_evidence = _lookups(manifest, entry, artifacts, contract)
        evidence.update(lookup_evidence)
        data = artifacts.verified(ref, max_bytes=execution.get("max_input_bytes", max_bytes))
        result = engine.read(source_parquet.document(data, contract) if parquet else data,
                             context=context, lookups=lookups)
        reading = {"input": ref, **evidence, "tables": result.tables, "deferred": result.deferred}
        return _encode(reading), len(data)

    with tempfile.TemporaryFile(mode="w+b") as spool:
        spooled = []  # (offset, length, input bytes) per input, in order
        with ThreadPoolExecutor(max_workers=execution["workers"]) as pool:
            batch = 4 * execution["workers"]
            for start in range(0, len(inputs), batch):
                for encoded, input_bytes in pool.map(read_one, inputs[start:start + batch]):
                    spooled.append((spool.tell(), len(encoded), input_bytes))
                    spool.write(encoded)

        def each():
            for offset, length, input_bytes in spooled:
                spool.seek(offset)
                yield spool.read(length), input_bytes

        whole = (len(b'{"artifacts":[],"contract":') + len(_encode(manifest["contract"])) + len(b',"version":1}')
                 + sum(length for _, length, _ in spooled) + max(0, len(spooled) - 1))
        if whole <= OUTPUT_BYTES:
            output = (b'{"artifacts":[' + b",".join(encoded for encoded, _ in each())
                      + b'],"contract":' + _encode(manifest["contract"]) + b',"version":1}')
            return output
        index = []
        for encoded, input_bytes in each():
            reading = json.loads(encoded)
            evidence = {k: v for k, v in reading.items() if k not in ("tables", "deferred")}
            index.append(source_readings.pieces(envelope["output"], evidence, reading["tables"],
                                                reading["deferred"], names, input_bytes, sink))
        output = _encode({"version": 2, "contract": manifest["contract"], "artifacts": index})
        if len(output) > source_readings.INDEX_BYTES:
            raise ValueError("source.read index exceeds its byte bound")
        return output


def execute(envelope: dict, artifacts) -> dict:
    documents = _documents(envelope, artifacts, publish=True)
    read = documents[1].get("read")
    if isinstance(read, dict) and "stream" in read:
        output = source_stream.output(envelope, artifacts, documents, _context, _lookups, publish=True,
                                      max_index_bytes=OUTPUT_BYTES)
    else:
        # Every piece is written as it is made, before the index that names it.
        output = _output(envelope, artifacts, documents, source_readings.publish(artifacts))
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
        expected = _output(envelope, artifacts, documents, source_readings.check(artifacts))
    found = artifacts.verified(envelope["candidate"], max_bytes=source_readings.INDEX_BYTES)
    if found != expected:
        raise ValueError("Written source output differs from the configured reading")
    return {name: True for name in envelope["checks"]}, []


def confirm(envelope: dict, artifacts) -> tuple[dict, list]:
    """The check without redoing the work (ticket 72). The inputs and contract
    pass the step's own checks, and the written output parses, names this
    contract and, in order, each input's file, context and lookup receipts,
    and holds only the contract's tables. (The record limit bounds a file's
    input records, not the rows it gives, so it is not checked here.) Bookkeeping pins the worker's runtime for the run and hashes the
    input and the output; the check loop still redoes a sample of units."""
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    manifest, contract, execution, inputs = _documents(envelope, artifacts)
    read = contract.get("read")
    if isinstance(read, dict) and "stream" in read:
        raise Redo("a streamed source extract has its own output shape")
    _limits(contract, execution)  # the contract's limits, as the work checks them
    body = artifact_store.json_value(artifacts.verified(envelope["candidate"], max_bytes=source_readings.INDEX_BYTES))
    if isinstance(body, dict) and body.get("version") == 2:
        raise Redo("a source extract written in pieces is checked by redoing it")
    if (not isinstance(body, dict) or set(body) != {"version", "contract", "artifacts"} or body["version"] != 1
            or body["contract"] != manifest["contract"] or not isinstance(body["artifacts"], list)
            or len(body["artifacts"]) != len(inputs)):
        raise ValueError("Written source output does not name this contract and these inputs")
    declared = set(read["tables"])
    for artifact, entry in zip(body["artifacts"], inputs):
        if not isinstance(artifact, dict) or {k: v for k, v in artifact.items() if k not in ("tables", "deferred")} != _receipts(manifest, entry):
            raise ValueError("Written source output does not name these inputs in order")
        tables = artifact.get("tables")
        if (not isinstance(tables, dict) or not set(tables) <= declared or not isinstance(artifact.get("deferred"), list)
                or any(not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows) for rows in tables.values())):
            raise ValueError("Written source output holds tables the contract does not declare")
    return {name: True for name in envelope["checks"]}, []
