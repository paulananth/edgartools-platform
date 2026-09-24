"""Opt-in Clean MDM handlers on the existing MDM command entry points."""

from __future__ import annotations

import hashlib
import json
import math
import os
from functools import partial
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, event, text

from .activation import check_policy
from .adapters import UnsupportedRecord, normalize
from .bookkeeping import RunCoordinator
from .evidence import deferred_record
from .merge import MergeStage
from .publication import JournalMirror, LocalContractSink
from .store import Conflict, Publisher, Store, current_reading


def _reject_json_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


def _finite_json_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("JSON number exceeds finite float range")
    return result


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
    with file.open("rb") as handle:
        raw = handle.read(32 * 1024**2 + 1)
    if len(raw) > 32 * 1024**2:
        raise ValueError("Input manifest exceeds 32 MiB")
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


def artifact_reader(root: str):
    """Confine acquisition references to an explicitly configured local/S3 root."""
    if root.startswith("s3://"):
        import fsspec

        prefix = root.rstrip("/") + "/"

        def read_s3(reference):
            if not reference.startswith(prefix) or any(
                p in {".", ".."} for p in reference.split("/")
            ):
                raise Conflict("Source artifact is outside the approved S3 root")
            return fsspec.open(reference, "rb").open()

        return read_s3
    approved = Path(root).resolve()

    def read_local(reference):
        path = (approved / reference).resolve()
        if not path.is_relative_to(approved):
            raise Conflict("Source artifact is outside the approved local root")
        return path.open("rb")

    return read_local


def batch_assertions(
    batch: dict, root: Path, store: Store, *, policy_digest: str | None = None
) -> list[dict]:
    assertions, deferred = batch_evidence(
        batch, root, store, policy_digest=policy_digest
    )
    if deferred:
        raise Conflict("Deferred records require the full batch_evidence contract")
    return assertions


def batch_evidence(
    batch: dict, root: Path, store: Store, *, policy_digest: str | None = None
) -> tuple[list[dict], list[dict]]:
    if "input" not in batch:
        return batch.get("assertions", []), batch.get("deferred", [])
    if batch.get("assertions") or batch.get("deferred"):
        raise ValueError("A source batch cannot mix file input and inline evidence")
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
        reading = current_reading(conn, spec["source_code"])
    if reading is None:
        raise Conflict("Unregistered dataset")
    # A corrected mapping applies to publications read from here on, and every
    # record says which reading produced it (ticket 01, decision 4).
    mapping_version, contract = reading
    # The pinned policy is read only when the contract names a classification
    # rule: every other contract states its kind and needs no policy to read.
    policy = None
    if contract["adapter"].get("classification"):
        with store.engine.connect() as conn:
            policy = conn.scalar(
                text("SELECT body FROM mdm_v2.policy WHERE digest=:digest"),
                {"digest": policy_digest},
            )
        if policy is None:
            # Fail before reading a record, not on the first one.
            raise Conflict(
                f"Contract {spec['source_code']} names a classification rule; "
                f"its pinned policy {policy_digest!r} is not registered"
            )
        # Checked here too, not only per batch: an activation decides a
        # record's kind at read time, before the Merge Stage sees the batch.
        check_policy(policy)
    result: list[dict] = []
    deferred: list[dict] = []
    retains_deferred = contract["adapter"].get("retain_deferred", False)
    if retains_deferred and type(spec.get("record_count")) is not int:
        raise ValueError("A source member requires an exact record_count")
    for ordinal, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        if len(result) + len(deferred) >= 1000:
            raise ValueError(
                "Source member exceeds bounded 1000-record batch; partition the manifest"
            )
        publication = {
            **spec["publication"],
            "artifact_sha256": spec["sha256"],
            "member": spec["path"],
        }
        if retains_deferred:
            publication["record_locator"] = f"{spec['sha256']}:line:{ordinal}"
        problem: str | None
        try:
            row = json.loads(
                line,
                parse_constant=_reject_json_constant,
                parse_float=_finite_json_float,
            )
        except (ValueError, UnicodeDecodeError):
            # The immutable file remains authoritative for malformed bytes.
            import base64

            row = {"raw_bytes_base64": base64.b64encode(line).decode("ascii")}
            problem = "invalid_json_record"
        else:
            problem = None
        try:
            if problem:
                raise UnsupportedRecord(problem)
            result.append(
                normalize(
                    row,
                    source_code=spec["source_code"],
                    contract=contract,
                    publication=publication,
                    mapping_version=mapping_version,
                    policy=policy,
                )
            )
        except UnsupportedRecord as exc:
            if not retains_deferred:
                raise
            deferred.append(
                deferred_record(
                    source_code=spec["source_code"],
                    publication_key=publication["publication_key"],
                    record_locator=publication["record_locator"],
                    schema_version=contract["schema_version"],
                    reason=exc.reason,
                    raw_record=row,
                    provenance={
                        "artifact_sha256": spec["sha256"],
                        "member": spec["path"],
                        "adapter_version": contract["adapter"]["version"],
                        **exc.detail,
                    },
                )
            )
    if "record_count" in spec and len(result) + len(deferred) != spec["record_count"]:
        raise Conflict("Source member record_count mismatch")
    return result, deferred


def execute_manifest(
    store: Store,
    coordinator: RunCoordinator,
    *,
    path: str,
    run_id: str,
    stage: str,
    limit: int,
    preview: bool = False,
    publication_verifier=None,
) -> dict:
    if not 1 <= limit <= 1000:
        raise ValueError(
            "Clean MDM --limit must be 1..1000 source records per invocation"
        )
    UUID(run_id)
    manifest, manifest_hash, root = read_manifest(path)
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
    native_scope = None
    native_batches = {}
    if "native_source" in manifest:
        from .native_consumption import prepare_native

        if stage != "mastering":
            raise ValueError("Native publication manifests run through mastering")
        native_scope, native_batches = prepare_native(
            manifest,
            store,
            coordinator,
            publication_verifier,
            observed=observed,
            limit=limit,
            run_id=run_id,
        )
    if not preview:
        coordinator.start(
            run_id,
            [b["batch_id"] for b in manifest["batches"]],
            manifest_digest=manifest_hash,
            native_consumption=native_scope,
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
        if native_scope is not None:
            if batch["batch_id"] not in native_batches:
                break
            native = native_batches[batch["batch_id"]]
            assertions, deferred = native["assertions"], native["deferred"]
        else:
            assertions, deferred = batch_evidence(
                batch, root, store, policy_digest=manifest["policy_digest"]
            )
        cost = (
            0
            if batch["batch_id"] in retained
            else max(
                1,
                len(assertions) + len(deferred),
                len(batch.get("decisions", [])),
                len(batch.get("identities", [])),
            )
        )
        if handled + cost > limit:
            if handled == 0:
                raise ValueError(f"Next atomic batch requires --limit at least {cost}")
            break
        command = {
            "batch_id": batch["batch_id"],
            "run_id": run_id,
            "policy_digest": manifest["policy_digest"],
            "consumer": batch["consumer"],
            "expected_checkpoint": batch["expected_checkpoint"],
            "checkpoint": batch["checkpoint"],
            "as_of": manifest["as_of"],
            "assertions": assertions,
            "identities": batch.get("identities", []),
            "decisions": batch.get("decisions", []),
            "preview": preview,
            "deferred": deferred,
        }
        for key in (
            "source_family",
            "publication_family",
            "committed_publication",
            "continuity_proof",
        ):
            if key in batch:
                command[key] = batch[key]
        if native_scope is not None:
            command.update(native_batches[batch["batch_id"]])
        if preview:
            result = MergeStage(store).apply(**command)
        else:
            result = coordinator.execute(
                run_id, batch["batch_id"], partial(MergeStage(store).apply, **command)
            )
        if preview:
            return result  # Preview one atomic batch against the current generation.
        committed.append(result)
        observed.add(batch["batch_id"])
        prerequisites.add(batch["batch_id"])
        if not result["duplicate"]:
            handled += cost
    if preview:
        return {"preview": True, "commits": [], "records_processed": 0}
    return {
        "commits": committed,
        "records_processed": handled,
        **coordinator.reconcile(run_id),
    }


def handle(command: str, args) -> int:
    if command == "prepare-clean-company":
        from .company_source import prepare_company_bundle

        report = prepare_company_bundle(
            landing_root=args.landing_root,
            landing_manifest=args.landing_manifest,
            output=args.output,
            limit=args.limit,
            as_of=args.as_of,
            revision=args.revision,
        )
        print(json.dumps(report, sort_keys=True))
        return 0
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
            verifier = None
            if "native_source" in read_manifest(args.manifest)[0]:
                from .source_publications import PublicationVerifier

                ledger = engine_from_env("CHANGE_LEDGER_DATABASE_URL", restricted=False)
                verifier = PublicationVerifier(
                    ledger, artifact_reader(os.environ["MDM_SOURCE_ARTIFACT_ROOT"])
                )
            report = execute_manifest(
                store,
                coordinator,
                path=args.manifest,
                run_id=run_id,
                stage="stewardship" if command == "apply-decisions" else command,
                limit=100 if getattr(args, "limit", None) is None else args.limit,
                preview=getattr(args, "dry_run", False),
                publication_verifier=verifier,
            )
        elif command == "publish":
            consumer = getattr(args, "consumer", None)
            publisher: Publisher
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
