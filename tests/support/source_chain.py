"""Configured rules over invented files, through the real workers (ticket 106).

Each step puts its manifest, runs its worker and asserts the worker's own
verifier admits the result: a source extract (`source.read`), a combination
(`source.combine`) and MDM preparation (`mdm.prepare`). `records` normalizes
the prepared lines through the Dataset Contract, as the Merge Stage reads them.
A test keeps what is its own: the files it writes, each artifact's context and
lookups, and the preparation keys.
"""

from __future__ import annotations

import json
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import adapters
from edgar_warehouse.rules import files
from edgar_warehouse.workers import mdm_prepare, source_combine, source_read


def read(store: Artifacts, root: Path, body: dict, artifacts: list[dict], version: int) -> dict:
    """A source extract of `artifacts` (each its input, context and lookups) under the contract `body`."""
    root.mkdir(parents=True, exist_ok=True)
    manifest = store.put(root.as_uri(), {"version": version, "contract": store.put(root.as_uri(), body),
                                         "artifacts": artifacts})
    task = {"input": manifest, "output": (root / "reading.json").as_uri(), "checks": ["source.output"]}
    out = source_read.execute(task, store)
    assert source_read.verify({**task, "candidate": out}, store) == ({"source.output": True}, [])
    return out


def combine(store: Artifacts, root: Path, contract: Path, readings: dict) -> dict:
    """A combination of named readings under the contract file `contract`."""
    root.mkdir(parents=True, exist_ok=True)
    manifest = store.put(root.as_uri(), {"version": 1, "contract": store.put(root.as_uri(), files.load(contract)),
                                         "readings": readings})
    task = {"input": manifest, "output": (root / "out.json").as_uri(), "checks": [source_combine.CHECK], "keys": {}}
    out = source_combine.execute(task, store)
    assert source_combine.verify({**task, "candidate": out}, store) == ({source_combine.CHECK: True}, [])
    return out


def prepare(store: Artifacts, root: Path, reading: dict, keys: dict) -> dict:
    """MDM preparation of `reading`; its batches are written under `root`."""
    task = {"input": reading, "output": (root / "manifest.json").as_uri(), "checks": ["mdm.prepared"], "keys": keys}
    prepared = mdm_prepare.execute(task, store)
    assert mdm_prepare.verify({**task, "candidate": prepared}, store) == ({"mdm.prepared": True}, [])
    return prepared


def records(store: Artifacts, root: Path, prepared: dict, code: str, contract: dict,
            refused: dict[str, str] | None = None, key: str | None = None) -> list[dict]:
    """The prepared records normalized under the Dataset Contract `code`. With
    `refused`, a record the contract sets aside is kept there by its `key`
    field, with its reason, instead of failing the test."""
    out = []
    for batch in store.json(prepared)["batches"]:
        data = batch["input"]
        for line in (root / data["path"]).read_bytes().splitlines():
            row = json.loads(line)
            try:
                out.append(adapters.normalize(row, source_code=code, contract=contract, publication={
                    **data["publication"], "semantics": "patch", "artifact_sha256": data["sha256"],
                    "member": data["path"], "record_locator": f"{data['sha256']}:{len(out)}"}))
            except adapters.UnsupportedRecord as error:
                if refused is None:
                    raise
                refused[row[key]] = error.reason
    return out
