"""mastering.merge: the preparation's manifest through the three-operation merge, one file a batch.

The envelope's input is the manifest `mdm.prepare` wrote. Each batch's records go to `merge_file`,
which commits one file at a time, so a retry skips what is done. The receipt names each file and its
record count, and the verifier reads the same rows with its own login. The database lock, not a
lease, keeps writers apart.
"""
from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from pathlib import Path

CHECK = "mdm.committed"


def runtime_files() -> list[Path]:
    from edgar_warehouse import mastering
    from edgar_warehouse.mastering import merge, store
    from edgar_warehouse.mdm import connections, execution

    return [Path(mastering.__file__), Path(merge.__file__), Path(store.__file__), Path(connections.__file__),
            *execution.runtime_files()]


def _stage(envelope: dict, artifacts, folder: Path) -> tuple[Path, dict]:
    """The manifest and each input file it names, by their own digests."""
    from edgar_warehouse.mdm import limits

    raw = artifacts.verified(envelope["input"], max_bytes=limits.MANIFEST_BYTES)
    manifest = json.loads(raw)
    path = folder / "manifest.json"
    path.write_bytes(raw)
    base = envelope["input"]["uri"].rsplit("/", 1)[0]
    for batch in manifest.get("batches", []):
        spec = batch.get("input")
        if spec is None:
            continue
        name = Path(spec["path"])
        if name.is_absolute() or ".." in name.parts or name == Path("manifest.json"):
            raise ValueError("A manifest input must be a file beside the manifest")
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifacts.verified({"uri": f"{base}/{name.as_posix()}", "sha256": spec["sha256"]},
                                              max_bytes=limits.RECORDS_FILE_BYTES))
    return path, manifest


def _engine(*, restricted: bool):
    from edgar_warehouse.mdm.connections import engine_from_env

    return engine_from_env("MDM_DATABASE_URL", restricted=restricted)


def _settings(engine, manifest: dict, kind: str):
    from edgar_warehouse.database_connections import storage_adapter
    from edgar_warehouse.mastering.merge import Settings

    with engine.connect() as conn:
        policy = storage_adapter().registered_policy(conn, manifest["policy_digest"])
    if policy is None:
        raise ValueError("The manifest's policy is not registered")
    return Settings(policy, manifest["policy_digest"], kind, manifest["as_of"])


def _quiet(engine, deferred: list[dict]) -> dict:
    from edgar_warehouse.database_connections import storage_adapter

    if not deferred:
        return {}
    with engine.connect() as conn:
        contracts = storage_adapter().dataset_contracts(conn, {r["source_code"] for r in deferred})
    return {code: set(body.get("nonblocking_deferred_reasons", [])) for code, body in contracts.items()}


def execute(envelope: dict, artifacts) -> dict:
    from edgar_warehouse.mastering import merge
    from edgar_warehouse.mastering.store import open_store
    from edgar_warehouse.mdm.execution import batch_input
    from edgar_warehouse.mdm.store import Store

    if set(envelope["checks"]) != {CHECK}:
        raise ValueError(f"mastering.merge verifies {CHECK} only")
    engine = _engine(restricted=True)
    db = open_store(engine)
    files = []
    try:
        with tempfile.TemporaryDirectory(prefix="mastering-") as folder:
            path, manifest = _stage(envelope, artifacts, Path(folder))
            for batch in manifest["batches"]:
                found = batch_input(batch, path.parent, Store(engine), policy_digest=manifest["policy_digest"])
                kinds = defaultdict(list)
                for record in found["assertions"]:
                    kinds[record["kind"]].append(record)
                deferred = found["deferred"]
                quiet = _quiet(engine, deferred)
                for kind, records in sorted(kinds.items()) or [("", [])]:
                    done = merge.merge_file(db, _settings(engine, manifest, kind), records, deferred=deferred, quiet=quiet)
                    files.append({"file": done["file"], "records": len(records)})
                    deferred = ()
        files.sort(key=lambda item: item["file"])
        return artifacts.put_bytes(envelope["output"], json.dumps({"version": 1, "files": files}, sort_keys=True,
                                                                  separators=(",", ":")).encode())
    finally:
        db.close()
        engine.dispose()


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    from edgar_warehouse.mastering.store import open_store

    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    claimed = json.loads(artifacts.verified(envelope["candidate"], max_bytes=64 * 1024 * 1024))["files"]
    engine = _engine(restricted=False)
    db = open_store(engine)
    try:
        held = db.done_files([item["file"] for item in claimed])
    finally:
        db.close()
        engine.dispose()
    if len(held) != len({item["file"] for item in claimed}) or any(held[i["file"]] != i["records"] for i in claimed):
        raise ValueError("The receipt differs from what mastering holds")
    return {CHECK: True}, []
