"""source.read: a hash-pinned YAML contract and at most two captured artifacts.

Runs configured Rust parsing through Python; no discovery, acquisition or
mastering. Bookkeeping sees only task envelopes and immutable output receipts.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import edgar_warehouse.bookkeeping.clean.artifacts as artifact_store
from edgar_warehouse.rules import files, source_engine
from . import source_stream, source_readings

OUTPUT_BYTES = 128 * 1024**2


def runtime_files() -> list[Path]:
    """Pin the facade, value registry and loaded Rust extension with this worker."""
    return [*source_engine.runtime_files(), Path(files.__file__), Path(artifact_store.__file__),
            Path(source_stream.__file__), Path(source_readings.__file__)]


def _documents(envelope: dict, artifacts):
    if set(envelope["checks"]) != {"source.output"}:
        raise ValueError("source.read verifies source.output only")
    manifest = artifacts.json(envelope["input"])
    if (set(manifest) != {"version", "contract", "artifacts"}
            or type(manifest["version"]) is not int or manifest["version"] not in (1, 2)):
        raise ValueError("Source input names version 1 or 2, contract and artifacts")
    contract = files.loads(artifacts.verified(manifest["contract"], max_bytes=1024**2).decode("utf-8"))
    execution = contract.get("execution")
    if (not isinstance(execution, dict) or set(execution) != {"profile", "workers", "max_artifacts"}
            or execution["profile"] != "source.read"
            or any(type(execution[key]) is not int or not 1 <= execution[key] <= 2
                   for key in ("workers", "max_artifacts"))):
        raise ValueError("Source execution requires source.read with 1..2 workers and artifacts")
    inputs = manifest["artifacts"]
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= execution["max_artifacts"]:
        raise ValueError("Source input exceeds the contract's bounded artifact count")
    return manifest, contract, execution, inputs


def _context(manifest, entry, artifacts):
    if manifest["version"] == 1:
        return entry, {}, {}
    if not isinstance(entry, dict) or set(entry) != {"input", "context"}:
        raise ValueError("Version-2 artifact names input and context receipts")
    ref = entry["input"]
    bound = artifact_store.json_value(artifacts.verified(entry["context"], max_bytes=32 * 1024))
    if (not isinstance(bound, dict) or set(bound) != {"version", "input", "values"}
            or type(bound["version"]) is not int or bound["version"] != 1
            or bound["input"] != ref or not isinstance(bound["values"], dict)):
        raise ValueError("Context document must bind its values to the exact input receipt")
    return ref, bound["values"], {"context": entry["context"]}


def _output(envelope: dict, artifacts, documents=None) -> bytes:
    manifest, contract, execution, inputs = documents or _documents(envelope, artifacts)
    engine = source_engine.SourceEngine(contract)
    max_bytes = contract["read"].get("limits", {}).get("max_bytes", 32 * 1024**2)
    max_records = contract["read"].get("limits", {}).get("max_records")
    if max_bytes > 32 * 1024**2:
        raise ValueError("source.read accepts at most 32 MiB per artifact")
    if type(max_records) is not int or not 1 <= max_records <= 100000:
        raise ValueError("source.read requires a limit of at most 100000 records")

    def read(entry):
        ref, context, evidence = _context(manifest, entry, artifacts)
        result = engine.read(artifacts.verified(ref, max_bytes=max_bytes), context=context)
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
        output = source_stream.output(envelope, artifacts, documents, _context, publish=True,
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
        expected = source_stream.output(envelope, artifacts, documents, _context, publish=False,
                                        max_index_bytes=OUTPUT_BYTES)
    else:
        expected = _output(envelope, artifacts, documents)
    found = artifacts.verified(envelope["candidate"], max_bytes=OUTPUT_BYTES)
    if found != expected:
        raise ValueError("Written source output differs from the configured reading")
    return {name: True for name in envelope["checks"]}, []
