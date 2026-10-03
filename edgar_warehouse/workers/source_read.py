"""source.read: a hash-pinned YAML contract and at most two captured artifacts.

Runs configured Rust parsing through Python; no discovery, acquisition or
mastering. Bookkeeping sees only task envelopes and immutable output receipts.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from edgar_warehouse.rules import files, source_engine


def runtime_files() -> list[Path]:
    """Pin the facade, value registry and loaded Rust extension with this worker."""
    return [*source_engine.runtime_files(), Path(files.__file__)]


def _output(envelope: dict, artifacts) -> bytes:
    if set(envelope["checks"]) != {"source.output"}:
        raise ValueError("source.read verifies source.output only")
    manifest = artifacts.json(envelope["input"])
    if (set(manifest) != {"version", "contract", "artifacts"}
            or type(manifest["version"]) is not int or manifest["version"] != 1):
        raise ValueError("Source input names version 1, contract and artifacts")
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
    engine = source_engine.SourceEngine(contract)
    max_bytes = contract["read"].get("limits", {}).get("max_bytes", 32 * 1024**2)
    max_records = contract["read"].get("limits", {}).get("max_records")
    if max_bytes > 32 * 1024**2:
        raise ValueError("source.read accepts at most 32 MiB per artifact")
    if type(max_records) is not int or not 1 <= max_records <= 100000:
        raise ValueError("source.read requires a limit of at most 100000 records")

    def read(ref):
        result = engine.read(artifacts.verified(ref, max_bytes=max_bytes))
        return {"input": ref, "tables": result.tables, "deferred": result.deferred}

    with ThreadPoolExecutor(max_workers=execution["workers"]) as pool:
        readings = list(pool.map(read, inputs))
    return json.dumps({"version": 1, "contract": manifest["contract"], "artifacts": readings},
                      sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def execute(envelope: dict, artifacts) -> dict:
    return artifacts.put_bytes(envelope["output"], _output(envelope, artifacts))


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    expected = _output(envelope, artifacts)
    found = artifacts.verified(envelope["candidate"], max_bytes=128 * 1024**2)
    if found != expected:
        raise ValueError("Written source output differs from the configured reading")
    return {name: True for name in envelope["checks"]}, []
