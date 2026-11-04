"""A receipt-bound raw capture, read through configured workers.

A capture is a folder with `receipts.jsonl` (each captured object's key and
sha256) and the objects under `bronze/`, keyed as `warehouse/bronze/...`; or a
receipt names its object by `file`, a path inside the capture folder. A
receipt may also hold a companion file's sha256 (a request beside its answer). Name
Frequency, Company preparation and a declared target's manifest
(`target_manifest`) read its documents only through here: a
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


def rows(raw: bytes) -> dict[str, dict]:
    """Each receipt by its key: `key`, else `file`."""
    found = {}
    for row in map(json.loads, raw.decode("utf-8").splitlines()):
        found[row["key"] if "key" in row else row["file"]] = row
    return found


def receipts(capture: Path) -> tuple[bytes, dict[str, str]]:
    """The receipts file's bytes and {key: sha256}."""
    raw = read_bounded(capture / "receipts.jsonl", RECEIPTS_BYTES)
    return raw, {key: row["sha256"] for key, row in rows(raw).items()}


def path(capture: Path, key: str) -> Path:
    """Where a key's object is: under `bronze/` for a bronze key, else the capture-relative file."""
    relative = "bronze/" + key[len(BRONZE):] if key.startswith(BRONZE) else key
    if not relative or relative.startswith("/") or ".." in relative.split("/"):
        raise Conflict(f"A capture key stays inside the capture: {key}")
    return capture / relative


def verified(capture: Path, key: str, sha256: str) -> tuple[dict, bytes]:
    """A file's reference and bytes, equal to the sha256 a receipt gives for it."""
    data = path(capture, key).read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise Conflict(f"Captured document differs from its receipt: {key}")
    return {"uri": path(capture, key).as_uri(), "sha256": sha256}, data


def document(capture: Path, found: dict[str, str], key: str) -> dict:
    """A captured document's reference, {uri, sha256}, when its receipt names it."""
    if key not in found:
        raise Conflict(f"The capture's receipts do not name {key}")
    return {"uri": path(capture, key).as_uri(), "sha256": found[key]}


def document_bytes(capture: Path, found: dict[str, str], key: str) -> bytes:
    """A captured document's bytes, equal to its receipt."""
    document(capture, found, key)
    return verified(capture, key, found[key])[1]


def slices(sized: list[tuple[str, int]], max_bytes: int, max_documents: int) -> list[list[str]]:
    """Consecutive documents cut where the next would pass either bound; a larger document reads alone."""
    found, current, total = [], [], 0
    for key, size in sized:
        if current and (total + size > max_bytes or len(current) == max_documents):
            found.append(current)
            current, total = [], 0
        current.append(key)
        total += size
    return found + [current] if current else found


def cik(key: str) -> int:
    return int(key.split("/cik=", 1)[1].split("/", 1)[0])


def request(contract: dict, artifacts: list) -> dict:
    """A `source.read` request: artifacts that carry lookups go as version 3, those that all
    carry a context as version 2, others as version 1 (their inputs only)."""
    version = 3 if all("lookups" in a for a in artifacts) else 2 if all("context" in a for a in artifacts) else 1
    return {"version": version, "contract": contract,
            "artifacts": artifacts if version > 1 else [a["input"] for a in artifacts]}


def read_unit(store, folder: Path, name: str, contract: dict, artifacts: list) -> tuple[dict, dict]:
    """One `source.read` unit, executed then verified: its task and its reading's reference."""
    request_ref = store.put(folder.as_uri(), request(store.put(folder.as_uri(), contract), artifacts))
    task = {"input": request_ref, "output": (folder / f"{name}.reading.json").as_uri(), "checks": ["source.output"]}
    candidate = source_read.execute(task, store)
    if source_read.verify({**task, "candidate": candidate}, store) != ({"source.output": True}, []):
        raise ValueError("Configured reading verification failed")
    return task, candidate
