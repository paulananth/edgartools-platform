"""A receipt-bound raw capture, read through configured workers.

A capture is a folder with `receipts.jsonl` (each captured object's key and
sha256) and the objects under `bronze/`, keyed as `warehouse/bronze/...`. Name
Frequency and Company preparation read its documents only through here: a
document is read only when its bytes equal its receipt, and each `source.read`
unit is executed, then verified, before anything uses its output.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from edgar_warehouse.workers import source_read

from .store import Conflict

BRONZE = "warehouse/bronze/"
RECEIPTS_BYTES = 64 * 1024**2


def read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path.name} exceeds {limit} bytes")
    return data


def receipts(capture: Path) -> tuple[bytes, dict[str, str]]:
    """The receipts file's bytes and {key: sha256}."""
    raw = read_bounded(capture / "receipts.jsonl", RECEIPTS_BYTES)
    return raw, {r["key"]: r["sha256"] for r in map(json.loads, raw.decode("utf-8").splitlines())}


def document(capture: Path, found: dict[str, str], key: str) -> dict:
    """A captured document's reference, {uri, sha256}, when its receipt names it."""
    if key not in found or not key.startswith(BRONZE):
        raise Conflict(f"The capture's receipts do not name {key}")
    return {"uri": (capture / "bronze" / key[len(BRONZE):]).as_uri(), "sha256": found[key]}


def document_bytes(capture: Path, found: dict[str, str], key: str) -> bytes:
    """A captured document's bytes, equal to its receipt."""
    ref = document(capture, found, key)
    data = (capture / "bronze" / key[len(BRONZE):]).read_bytes()
    if hashlib.sha256(data).hexdigest() != ref["sha256"]:
        raise Conflict(f"Captured document differs from its receipt: {key}")
    return data


def cik(key: str) -> int:
    return int(key.split("/cik=", 1)[1].split("/", 1)[0])


def read_unit(store, folder: Path, name: str, contract: dict, artifacts: list) -> tuple[dict, dict]:
    """One `source.read` unit, executed then verified: its task and its reading's reference.
    Artifacts that all carry a context are sent as a version-2 request, others as version 1."""
    version = 2 if all("context" in a for a in artifacts) else 1
    request = store.put(folder.as_uri(), {"version": version, "contract": store.put(folder.as_uri(), contract),
                                          "artifacts": artifacts if version == 2 else [a["input"] for a in artifacts]})
    task = {"input": request, "output": (folder / f"{name}.reading.json").as_uri(), "checks": ["source.output"]}
    candidate = source_read.execute(task, store)
    if source_read.verify({**task, "candidate": candidate}, store) != ({"source.output": True}, []):
        raise ValueError("Configured reading verification failed")
    return task, candidate
