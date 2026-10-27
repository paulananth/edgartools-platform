"""mdm.merge: one MDM input manifest through the Merge Stage (mastering to-do 20e).

The envelope's input names a version-2 MDM manifest; a batch's `input.path`
is a file beside it, fetched by its own sha256. The worker runs the existing
Merge Stage (`execute_manifest`) under an MDM run whose id is fixed by the
envelope's effect key, so a retry or a lost acknowledgement resumes the same
MDM run and never merges twice. Its output is a receipt read back from MDM:
each manifest batch's committed request, policy, consumer, checkpoint and
generation. The verifier, with its own MDM login, reads the same rows and
reports `mdm.committed` only when they equal the candidate. Bookkeeping sees
the envelope, the receipt and the report, never MDM.

MDM_DATABASE_URL is this process's MDM login: the application login for the
worker, a reader for the verifier. Every MDM commit is fenced by the
envelope's live lease (`bookkeeping init-guard` installs the fence in the MDM
database); without it the worker fails closed.
"""
from __future__ import annotations

import json
import tempfile
from inspect import getfile
from pathlib import Path
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5


from edgar_warehouse.mdm.clean import limits

CHECK = "mdm.committed"
STAGE = "mastering"


def runtime_files() -> list[Path]:
    """The Merge Stage is part of what a run pins for this profile."""
    from edgar_warehouse.mdm.clean import connections, execution

    return [Path(getfile(connections)), *execution.runtime_files()]


def mdm_run(envelope: dict) -> str:
    return str(uuid5(NAMESPACE_URL, f"edgartools:mdm.merge:{envelope['effect_key']}"))


class Lease:
    """The envelope's live lease proof, for MDM's own transaction fence
    (`bookkeeping_guard.authorize` in each commit): a lapsed or taken-over
    lease is refused by MDM itself, not only later by Bookkeeping."""

    def __init__(self, envelope: dict):
        self.envelope = envelope

    def current(self):
        return SimpleNamespace(proof=self.envelope["claim"]["proof"])


def _store(*, restricted: bool, envelope: dict | None = None):
    from edgar_warehouse.mdm.clean.connections import engine_from_env
    from edgar_warehouse.mdm.clean.store import Store

    return Store(engine_from_env("MDM_DATABASE_URL", restricted=restricted),
                 lease_authority=None if envelope is None else Lease(envelope))


def _stage(envelope: dict, artifacts, folder: Path) -> tuple[Path, dict]:
    """The manifest and each input file it names, by their own digests."""
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


def receipt(store, manifest: dict, run_id: str, manifest_digest: str) -> bytes:
    """What MDM holds for the manifest's batches under this run, read back."""
    from edgar_warehouse.mdm.clean.prepared_runs import receipt as prepared_receipt
    return prepared_receipt(store,manifest,run_id,manifest_digest)


def execute(envelope: dict, artifacts) -> dict:
    from edgar_warehouse.mdm.clean.execution import execute_manifest

    if set(envelope["checks"]) != {CHECK}:
        raise ValueError(f"mdm.merge verifies {CHECK} only")
    store, run_id = _store(restricted=True, envelope=envelope), mdm_run(envelope)
    try:
        with tempfile.TemporaryDirectory(prefix="mdm-merge-") as folder:
            path, manifest = _stage(envelope, artifacts, Path(folder))
            if any(b["stage"] != STAGE for b in manifest["batches"]):
                raise ValueError("mdm.merge runs mastering batches only")
            execute_manifest(store, path=str(path), run_id=run_id, stage=STAGE)
            return artifacts.put_bytes(envelope["output"], receipt(store, manifest, run_id, envelope["input"]["sha256"]))
    finally:
        store.engine.dispose()


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    store = _store(restricted=False)
    try:
        manifest = artifacts.json(envelope["input"])
        expected = receipt(store, manifest, mdm_run(envelope), envelope["input"]["sha256"])
    finally:
        store.engine.dispose()
    if artifacts.verified(envelope["candidate"], max_bytes=limits.MANIFEST_BYTES) != expected:
        raise ValueError("The receipt differs from what MDM holds")
    return {CHECK: True}, []
