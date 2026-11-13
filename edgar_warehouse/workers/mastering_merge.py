"""mastering.merge: the preparation's manifest through the three-operation merge, one file a batch.

The envelope's input is the manifest `mdm.prepare` wrote. Each batch's records go to `merge_file`,
which commits one file at a time, so a retry skips what is done. The receipt names each file and its
record count, and the check reads the same rows back. The database lock, not a
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


def _quiet(engine, deferred: list[dict], known: dict) -> dict:
    """The reasons each source leaves quiet; a source's contract is read once a unit, kept in `known`."""
    from edgar_warehouse.database_connections import storage_adapter

    missing = {r["source_code"] for r in deferred} - known.keys()
    if missing:
        with engine.connect() as conn:
            contracts = storage_adapter().dataset_contracts(conn, missing)
        known.update({code: set(body.get("nonblocking_deferred_reasons", [])) for code, body in contracts.items()})
    return {r["source_code"]: known[r["source_code"]] for r in deferred if r["source_code"] in known}


EVENT_TYPE = "batch.merged"


def _batch_key(source: str, identity: str, spec: dict) -> str:
    """One batch's Change Journal key: its source, the identity it was read under, its content hash and its file."""
    return f"{EVENT_TYPE}:{source}:{identity}:{spec['sha256']}:{spec['path']}"


def _identity(engine, manifest: dict, spec: dict, known: dict) -> str:
    """What a batch's records depend on besides its bytes: the reading, the policy and the publication it carries."""
    from edgar_warehouse.control_contract import digest
    from edgar_warehouse.mdm.store import current_reading

    code = spec["source_code"]
    if code not in known:
        with engine.connect() as conn:
            found = current_reading(conn, code)
        known[code] = None if found is None else found[0]
    return digest({"policy": manifest["policy_digest"], "reading": known[code], "publication": spec["publication"]})


def _recorded(journal, keys: list[str]) -> dict[str, list[list]]:
    """The files of each batch the journal holds, as [file, records]: the batch is not parsed again."""
    from edgar_warehouse.mdm import changed_files

    found = {}
    for start in range(0, len(keys), 400):
        for key, receipt in journal.get_many(changed_files.PRODUCER, keys[start:start + 400]).items():
            found[key] = [item.split(":") for item in receipt["event"]["scope"]["files"].split(",") if item]
    return found


def _record(journal, envelope: dict, manifest: dict, spec: dict, key: str, files: list[dict]) -> None:
    """Record a merged batch after its files committed; a batch another run recorded first keeps its record."""
    from edgar_warehouse.change_journal import JournalConflict
    from edgar_warehouse.change_journal.store import envelope as event
    from edgar_warehouse.mdm import changed_files

    value = event(producer=changed_files.PRODUCER, event_key=key, run_id=envelope["claim"]["run_id"],
                  source=spec["source_code"], feed="mastering", event_type=EVENT_TYPE, occurred_at=manifest["as_of"],
                  scope={"files": ",".join(f"{f['file']}:{f['records']}" for f in files)},
                  evidence=[{"uri": f"batch:{spec['path']}", "sha256": spec["sha256"]}])
    try:
        journal.append(value)
    except JournalConflict:
        pass


def execute(envelope: dict, artifacts) -> dict:
    from edgar_warehouse.mastering import merge
    from edgar_warehouse.mastering.store import open_store
    from edgar_warehouse.mdm import changed_files
    from edgar_warehouse.mdm.execution import batch_input
    from edgar_warehouse.mdm.store import Store

    if set(envelope["checks"]) != {CHECK}:
        raise ValueError(f"mastering.merge verifies {CHECK} only")
    engine = _engine(restricted=True)
    db = open_store(engine)
    files = []
    known: dict = {}
    settings: dict = {}
    readings: dict = {}
    journal = changed_files.journal()
    try:
        with tempfile.TemporaryDirectory(prefix="mastering-") as folder:
            path, manifest = _stage(envelope, artifacts, Path(folder))
            keys = {}
            for batch in manifest["batches"]:
                spec = batch.get("input")
                if spec is not None:
                    keys[id(batch)] = _batch_key(spec["source_code"], _identity(engine, manifest, spec, readings), spec)
            recorded = _recorded(journal, list(keys.values()))
            for batch in manifest["batches"]:
                key = keys.get(id(batch))
                if key in recorded:
                    files.extend({"file": name, "records": int(count)} for name, count in recorded[key])
                    continue
                start = len(files)
                found = batch_input(batch, path.parent, Store(engine), policy_digest=manifest["policy_digest"])
                kinds = defaultdict(list)
                for record in found["assertions"]:
                    kinds[record["kind"]].append(record)
                deferred = found["deferred"]
                quiet = _quiet(engine, deferred, known)
                for kind, records in sorted(kinds.items()) or [("", [])]:
                    if kind not in settings:
                        settings[kind] = _settings(engine, manifest, kind)
                    done = merge.merge_file(db, settings[kind], records, deferred=deferred, quiet=quiet)
                    files.append({"file": done["file"], "records": len(records)})
                    deferred = ()
                if key is not None:
                    _record(journal, envelope, manifest, batch["input"], key, files[start:])
        files.sort(key=lambda item: item["file"])
        return artifacts.put_bytes(envelope["output"], json.dumps({"version": 1, "files": files}, sort_keys=True,
                                                                  separators=(",", ":")).encode())
    finally:
        db.close()
        engine.dispose()


def check(envelope: dict, artifacts) -> tuple[dict, list]:
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
