"""Opt-in Clean MDM handlers on the existing MDM command entry points."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, event, text

from .adapters import normalize
from .bookkeeping import RunCoordinator
from .merge import MergeStage
from .publication import JournalMirror, LocalContractSink
from .store import Conflict, Store


def engine_from_env(name: str, *, restricted: bool = True):
    engine = create_engine(os.environ[name], pool_pre_ping=True)
    if restricted:
        role = os.environ.get("MDM_APPLICATION_ROLE", "application")
        quoted = engine.dialect.identifier_preparer.quote(role)

        @event.listens_for(engine, "connect")
        def select_role(dbapi_connection, _):
            with dbapi_connection.cursor() as cursor:
                cursor.execute(f"SET ROLE {quoted}")
            dbapi_connection.commit()

    return engine


def read_manifest(path: str) -> tuple[dict, str, Path]:
    file = Path(path).resolve()
    raw = file.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("contract_version") != 2 or not manifest.get("batches"):
        raise ValueError("A nonempty version-2 input manifest is required")
    ids = [b["batch_id"] for b in manifest["batches"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate manifest batch identity")
    allowed = {"mastering", "derive-relationships", "stewardship"}
    if any(b.get("stage") not in allowed for b in manifest["batches"]):
        raise ValueError("Unsupported manifest stage")
    return manifest, hashlib.sha256(raw).hexdigest(), file.parent


def batch_assertions(batch: dict, root: Path, store: Store) -> list[dict]:
    if "input" not in batch:
        return batch.get("assertions", [])
    spec = batch["input"]
    file = (root / spec["path"]).resolve()
    if not file.is_relative_to(root):
        raise ValueError("Source member must be inside the manifest directory")
    # Hash and parse the same bounded bytes, even if the file changes in place.
    with file.open("rb") as source:
        raw = source.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("Source member exceeds 16 MiB; partition the manifest")
    if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
        raise Conflict("Source artifact digest mismatch")
    with store.engine.connect() as conn:
        contract = conn.scalar(
            text("SELECT body FROM mdm_v2.dataset WHERE source_code=:code"),
            {"code": spec["source_code"]},
        )
    if contract is None:
        raise Conflict("Unregistered dataset")
    result = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if len(result) >= 1000:
            raise ValueError(
                "Source member exceeds bounded 1000-record batch; partition the manifest"
            )
        result.append(
            normalize(
                json.loads(line),
                source_code=spec["source_code"],
                contract=contract,
                publication={
                    **spec["publication"],
                    "artifact_sha256": spec["sha256"],
                    "member": spec["path"],
                },
            )
        )
    return result


def execute_manifest(
    store: Store,
    coordinator: RunCoordinator,
    *,
    path: str,
    run_id: str,
    stage: str,
    limit: int,
) -> dict:
    if not 1 <= limit <= 1000:
        raise ValueError(
            "Clean MDM --limit must be 1..1000 source records per invocation"
        )
    UUID(run_id)
    manifest, manifest_hash, root = read_manifest(path)
    coordinator.start(
        run_id,
        [b["batch_id"] for b in manifest["batches"]],
        manifest_digest=manifest_hash,
    )
    handled = 0
    committed = []
    with store.engine.connect() as conn:
        observed = set(
            conn.scalars(
                text(
                    "SELECT batch_id FROM mdm_v2.observation WHERE run_id=CAST(:run AS uuid)"
                ),
                {"run": run_id},
            )
        )
        retained = set(
            conn.scalars(
                text("SELECT batch_id FROM mdm_v2.batch WHERE batch_id=ANY(:ids)"),
                {"ids": [b["batch_id"] for b in manifest["batches"]]},
            )
        )
    prerequisites = set()
    for batch in manifest["batches"]:
        if batch["batch_id"] in observed:
            prerequisites.add(batch["batch_id"])
            continue
        if batch["stage"] != stage:
            prerequisites.add(batch["batch_id"])
            continue
        if not prerequisites <= observed:
            raise Conflict("Complete preceding manifest batches before this stage")
        assertions = batch_assertions(batch, root, store)
        cost = (
            0
            if batch["batch_id"] in retained
            else max(
                1,
                len(assertions),
                len(batch.get("decisions", [])),
                len(batch.get("identities", [])),
            )
        )
        if handled + cost > limit:
            if handled == 0:
                raise ValueError(f"Next atomic batch requires --limit at least {cost}")
            break
        result = MergeStage(store).apply(
            batch_id=batch["batch_id"],
            run_id=run_id,
            policy_digest=manifest["policy_digest"],
            consumer=batch["consumer"],
            expected_checkpoint=batch["expected_checkpoint"],
            checkpoint=batch["checkpoint"],
            as_of=manifest["as_of"],
            assertions=assertions,
            identities=batch.get("identities", []),
            decisions=batch.get("decisions", []),
        )
        committed.append(result)
        observed.add(batch["batch_id"])
        prerequisites.add(batch["batch_id"])
        if not result["duplicate"]:
            handled += cost
    return {
        "commits": committed,
        "records_processed": handled,
        **coordinator.reconcile(run_id),
    }


def handle(command: str, args) -> int:
    supported = {
        "mastering",
        "apply-decisions",
        "derive-relationships",
        "publish",
        "reconcile",
        "counts",
        "publication-status",
    }
    if command not in supported:
        raise ValueError(
            f"{command} is not enabled for Clean MDM; refusing the legacy mutation path"
        )
    mdm = engine_from_env("MDM_DATABASE_URL")
    book = None
    ledger = None
    try:
        store = Store(mdm)
        if command == "counts":
            with mdm.connect() as conn:
                report = dict(
                    conn.execute(
                        text(
                            "SELECT object_type,count(*) FROM mdm_v2.projection GROUP BY object_type"
                        )
                    ).all()
                )
            print(json.dumps(report))
            return 0
        run_id = getattr(args, "run_id", None)
        if not run_id:
            raise ValueError("Clean MDM requires the same --run-id for every stage")
        book = engine_from_env("BOOKKEEPING_DATABASE_URL")
        coordinator = RunCoordinator(book, store)
        if command in {"mastering", "derive-relationships", "apply-decisions"}:
            if not getattr(args, "manifest", None):
                raise ValueError("Clean MDM requires a pinned --manifest")
            if (
                getattr(args, "cik", None)
                or getattr(args, "entity_type", "all") != "all"
            ):
                raise ValueError(
                    "Clean MDM scope is frozen in the manifest; do not combine it with legacy filters"
                )
            report = execute_manifest(
                store,
                coordinator,
                path=args.manifest,
                run_id=run_id,
                stage="stewardship" if command == "apply-decisions" else command,
                limit=100 if getattr(args, "limit", None) is None else args.limit,
            )
        elif command == "publish":
            consumer = getattr(args, "consumer", None)
            if consumer == "journal":
                ledger = engine_from_env("CHANGE_LEDGER_DATABASE_URL")
                publisher = JournalMirror(ledger)
            elif consumer in {"export", "graph"}:
                if not getattr(args, "contract_output", None):
                    raise ValueError("Offline export/graph requires --contract-output")
                publisher = LocalContractSink(args.contract_output)
            else:
                raise ValueError("Choose --consumer journal, export or graph")
            count = 0
            limit = 100 if getattr(args, "limit", None) is None else args.limit
            if not 1 <= limit <= 1000:
                raise ValueError("Publication limit must be 1..1000 batches")
            while count < limit and store.deliver_one(
                consumer, f"cli:{run_id}", publisher
            ):
                count += 1
            report = {"delivered": count, **coordinator.reconcile(run_id)}
        else:
            report = coordinator.reconcile(run_id)
        print(json.dumps(report, sort_keys=True))
        return (
            0
            if command not in {"reconcile", "publication-status"}
            or report["end_to_end_complete"]
            else 2
        )
    finally:
        mdm.dispose()
        if book is not None:
            book.dispose()
        if ledger is not None:
            ledger.dispose()
