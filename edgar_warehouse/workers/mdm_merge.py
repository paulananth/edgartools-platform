"""mdm.merge: one Clean MDM input manifest through the Merge Stage (mastering to-do 20e).

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
from pathlib import Path
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

CHECK = "mdm.committed"
STAGE = "mastering"
# execute_manifest's own bound per call; the worker calls it until the run's
# expected batches are all observed.
LIMIT = 1000


def runtime_files() -> list[Path]:
    """The Merge Stage is part of what a run pins for this profile."""
    from edgar_warehouse.mdm.clean import cli, merge, run, store

    return [Path(m.__file__) for m in (cli, merge, run, store)]


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
    from edgar_warehouse.mdm.clean.cli import engine_from_env
    from edgar_warehouse.mdm.clean.store import Store

    return Store(engine_from_env("MDM_DATABASE_URL", restricted=restricted),
                 lease_authority=None if envelope is None else Lease(envelope))


def _stage(envelope: dict, artifacts, folder: Path) -> tuple[Path, dict]:
    """The manifest and each input file it names, by their own digests."""
    raw = artifacts.verified(envelope["input"], max_bytes=32 * 1024**2)
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
                                              max_bytes=16 * 1024**2))
    return path, manifest


def receipt(store, manifest: dict, run_id: str, manifest_digest: str) -> bytes:
    """What MDM holds for the manifest's batches under this run, read back."""
    ids = [b["batch_id"] for b in manifest["batches"]]
    with store.engine.connect() as conn:
        scope = conn.scalar(text("SELECT scope FROM mdm.run WHERE run_id=CAST(:r AS uuid)"),
                            {"r": run_id})
        if (scope is None or scope.get("manifest_digest") != manifest_digest
                or scope.get("expected_batches") != sorted(ids)):
            raise ValueError("MDM run scope differs from the input manifest")
        observed = set(conn.scalars(text("SELECT batch_id FROM mdm.run_batch WHERE run_id=CAST(:r AS uuid)"),
                                    {"r": run_id}))
        rows = {r["batch_id"]: dict(r) for r in conn.execute(text(
            "SELECT batch_id, request_hash, policy_digest, consumer, checkpoint, generation "
            "FROM mdm.batch WHERE batch_id = ANY(:ids)"), {"ids": ids}).mappings()}
    missing = sorted(set(ids) - observed)
    if missing or set(rows) != set(ids):
        raise ValueError(f"MDM has not committed every batch of this run: {missing or sorted(set(ids) - set(rows))}")
    body = {"version": 1, "mdm_run": run_id, "policy_digest": manifest["policy_digest"],
            "batches": [rows[i] for i in sorted(ids)]}
    if any(row["policy_digest"] != manifest["policy_digest"] for row in body["batches"]):
        raise ValueError("A committed batch names a different policy")
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def execute(envelope: dict, artifacts) -> dict:
    from edgar_warehouse.mdm.clean.cli import execute_manifest
    from edgar_warehouse.mdm.clean.run import RunCoordinator

    if set(envelope["checks"]) != {CHECK}:
        raise ValueError(f"mdm.merge verifies {CHECK} only")
    store, run_id = _store(restricted=True, envelope=envelope), mdm_run(envelope)
    try:
        with tempfile.TemporaryDirectory(prefix="mdm-merge-") as folder:
            path, manifest = _stage(envelope, artifacts, Path(folder))
            if any(b["stage"] != STAGE for b in manifest["batches"]):
                raise ValueError("mdm.merge runs mastering batches only")
            coordinator = RunCoordinator(store)
            while True:
                result = execute_manifest(store, coordinator, path=str(path), run_id=run_id, stage=STAGE,
                                          limit=LIMIT)
                if not result["missing_batches"]:
                    break
                if not result["commits"]:
                    raise ValueError(f"MDM made no progress on {result['missing_batches']}")
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
    if artifacts.verified(envelope["candidate"], max_bytes=32 * 1024**2) != expected:
        raise ValueError("The receipt differs from what MDM holds")
    return {CHECK: True}, []
