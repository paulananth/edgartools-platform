"""Opt-in MDM handlers on the existing MDM command entry points."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from functools import partial
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, event, text

from . import limits
from .activation import check_policy
from .adapters import UnsupportedRecord, normalize
from .run import RunCoordinator
from .evidence import deferred_record
from .merge import MergeStage
from .quality import counts as quality_counts
from .quality import profile as quality_profile
from .store import Conflict, Store, current_reading, reading_at


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
    found = batch_input(batch, root, store, policy_digest=policy_digest)
    return found["assertions"], found["deferred"]


def batch_input(
    batch: dict,
    root: Path,
    store: Store,
    *,
    policy_digest: str | None = None,
    mapping_versions: dict[str, int] | None = None,
) -> dict:
    """A batch's readings, its deferred records, and each reading's bronze object.

    A pinned source row may name the bronze object it was read from
    (`_origin.bronze`: object, sha256, locator). That is where the record was
    delivered, not what it says, so it travels beside the reading as an
    occurrence and the Stage keeps the winner's (ticket 10).

    A run passes the `mapping_versions` its scope pins; without them the batch
    is read under the source's newest reading.
    """
    if "input" not in batch:
        return {
            "assertions": batch.get("assertions", []),
            "deferred": batch.get("deferred", []),
            "occurrences": batch.get("occurrences", []),
        }
    if batch.get("assertions") or batch.get("deferred"):
        raise ValueError("A source batch cannot mix file input and inline evidence")
    spec = batch["input"]
    file = (root / spec["path"]).resolve()
    if not file.is_relative_to(root):
        raise ValueError("Source member must be inside the manifest directory")
    # Hash and parse the same bounded bytes, even if the file changes in place.
    with file.open("rb") as source:
        raw = source.read(limits.RECORDS_FILE_BYTES + 1)
    if len(raw) > limits.RECORDS_FILE_BYTES:
        raise ValueError(f"Source member exceeds {limits.RECORDS_FILE_BYTES:,} bytes; partition the manifest")
    if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
        raise Conflict("Source artifact digest mismatch")
    code = spec["source_code"]
    with store.engine.connect() as conn:
        if mapping_versions is None:
            reading = current_reading(conn, code)
            if reading is None:
                raise Conflict("Unregistered dataset")
        else:
            reading = reading_at(conn, code, mapping_versions[code])
    # A corrected mapping applies to publications read from here on, and every
    # record says which reading produced it (ticket 01, decision 4).
    mapping_version, contract = reading
    # The pinned policy is read only when the contract names a classification
    # rule: every other contract states its kind and needs no policy to read.
    policy = None
    if contract["adapter"].get("classification"):
        with store.engine.connect() as conn:
            policy = conn.scalar(
                text("SELECT body FROM mdm.policy WHERE digest=:digest"),
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
    occurrences: list[dict] = []
    retains_deferred = contract["adapter"].get("retain_deferred", False)
    if retains_deferred and type(spec.get("record_count")) is not int:
        raise ValueError("A source member requires an exact record_count")
    for ordinal, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        if len(result) + len(deferred) >= limits.BATCH_RECORDS:
            raise ValueError(
                f"Source member exceeds bounded {limits.BATCH_RECORDS}-record batch; partition the manifest"
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
            bronze = (row.get("_origin") or {}).get("bronze")
            if bronze is not None:
                if not isinstance(bronze, dict):
                    raise Conflict("Invalid bronze occurrence")
                # Named field by field: a row names only its own reading.
                occurrences.append(
                    {
                        "assertion_id": result[-1]["assertion_id"],
                        "object": bronze.get("object"),
                        "sha256": bronze.get("sha256"),
                        "locator": bronze.get("locator"),
                    }
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
                    probable_kind=exc.probable_kind,
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
    return {"assertions": result, "deferred": deferred, "occurrences": occurrences}


def pinned_mapping_versions(store: Store, manifest: dict, scope: dict | None) -> dict[str, int]:
    """The mapping version of each source the manifest reads, for the whole run.

    Chosen once, when the run first starts, and kept in its frozen scope: a
    corrected mapping registered part way through applies to the next run,
    never to this run's later batches or its resume (rebuild ticket 103).
    """
    codes = sorted({b["input"]["source_code"] for b in manifest["batches"] if "input" in b})
    if scope is not None:
        pinned = scope.get("mapping_versions", {})
        if missing := [code for code in codes if code not in pinned]:
            raise Conflict(f"Run scope pins no reading of {', '.join(missing)}")
        return pinned
    pinned = {}
    with store.engine.connect() as conn:
        for code in codes:
            reading = current_reading(conn, code)
            if reading is None:
                raise Conflict(f"Unregistered dataset {code}")
            pinned[code] = reading[0]
    return pinned


def execute_manifest(
    store: Store,
    coordinator: RunCoordinator,
    *,
    path: str,
    run_id: str,
    stage: str,
    limit: int,
    preview: bool = False,
) -> dict:
    if not 1 <= limit <= limits.BATCH_RECORDS:
        raise ValueError(
            f"MDM --limit must be 1..{limits.BATCH_RECORDS} source records per invocation"
        )
    UUID(run_id)
    manifest, manifest_hash, root = read_manifest(path)
    if "native_source" in manifest:
        # The native GLEIF path was retired (Issue 20 L6): GLEIF is read by its contract.
        raise Conflict("Native publication manifests are retired; GLEIF is read by its contract")
    handled = 0
    committed = []
    with store.engine.connect() as conn:
        observed = set(
            conn.scalars(
                text(
                    "SELECT batch_id FROM mdm.run_batch WHERE run_id=CAST(:run AS uuid)"
                ),
                {"run": run_id},
            )
        )
        retained = set(
            conn.scalars(
                text("SELECT batch_id FROM mdm.batch WHERE batch_id=ANY(:ids)"),
                {"ids": [b["batch_id"] for b in manifest["batches"]]},
            )
        )
    mapping_versions = pinned_mapping_versions(store, manifest, coordinator.scope(run_id))
    if not preview:
        coordinator.start(
            run_id,
            [b["batch_id"] for b in manifest["batches"]],
            manifest_digest=manifest_hash,
            mapping_versions=mapping_versions,
        )
    prerequisites = set()
    quality: Counter = Counter()
    for batch in manifest["batches"]:
        if batch["batch_id"] in observed:
            prerequisites.add(batch["batch_id"])
            continue
        if batch["stage"] != stage:
            prerequisites.add(batch["batch_id"])
            continue
        if not prerequisites <= observed:
            raise Conflict("Complete preceding manifest batches before this stage")
        found = batch_input(
            batch,
            root,
            store,
            policy_digest=manifest["policy_digest"],
            mapping_versions=mapping_versions,
        )
        assertions, deferred = found["assertions"], found["deferred"]
        occurrences = found["occurrences"]
        batch_quality = quality_counts(assertions, deferred)
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
        if occurrences:
            command["occurrences"] = occurrences
        for key in (
            "source_family",
            "publication_family",
            "committed_publication",
            "continuity_proof",
        ):
            if key in batch:
                command[key] = batch[key]
        if preview:
            result = MergeStage(store).apply(**command)
        else:
            # The batch's run report profile is kept with its finished event,
            # and the run's report (`reconcile`, below) sums them as `checks`.
            result = coordinator.execute(
                run_id, batch["batch_id"], partial(MergeStage(store).apply, **command),
                checks={"as_of": manifest["as_of"], "profile": quality_profile(assertions, deferred)},
            )
        if preview:
            return result  # Preview one atomic batch against the current generation.
        committed.append(result)
        observed.add(batch["batch_id"])
        prerequisites.add(batch["batch_id"])
        if not result["duplicate"]:
            handled += cost
            quality.update(batch_quality)
    if preview:
        return {"preview": True, "commits": [], "records_processed": 0}
    return {
        "commits": committed,
        "records_processed": handled,
        # What the data quality rule did to this run's records, per fix and check.
        **({"quality": dict(sorted(quality.items()))} if quality else {}),
        **coordinator.reconcile(run_id),
    }


def prepare_clean_company(args) -> int:
    from .company_prepare import write_company_manifest

    report = write_company_manifest(
        capture=args.capture,
        documents=args.documents,
        population=args.population,
        catalog=args.catalog,
        capture_run=args.capture_run,
        catalog_run=args.catalog_run,
        observed_at=args.observed_at,
        name_census=args.name_census,
        output=args.output,
        as_of=args.as_of,
        revision=args.revision,
        force=args.all,
    )
    print(json.dumps(report, sort_keys=True))
    return 0


def prepare_capture(args) -> int:
    from .capture_prepare import write_capture_manifest

    report = write_capture_manifest(
        source=args.source,
        capture=args.capture,
        documents=args.documents,
        capture_run=args.capture_run,
        output=args.output,
        as_of=args.as_of,
        revision=args.revision,
        force=args.all,
    )
    print(json.dumps(report, sort_keys=True))
    return 0


def name_census(args) -> int:
    from .name_frequency import write_name_frequency

    report = write_name_frequency(
        capture=args.capture,
        population=args.population,
        gleif_reading={"uri": Path(args.gleif_reading).resolve().as_uri(), "sha256": args.gleif_reading_sha256},
        gleif_metadata=args.gleif_metadata,
        output=args.output,
    )
    print(json.dumps(report, sort_keys=True))
    return 0


def _print_mdm_report(read) -> int:
    """Run one read on the MDM database as the application role and print it."""
    mdm = engine_from_env("MDM_DATABASE_URL")
    try:
        with mdm.connect() as conn:
            report = read(conn)
    finally:
        mdm.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0


def check_connectivity(args) -> int:
    return _print_mdm_report(lambda conn: {
        "sql": conn.scalar(text("SELECT 1")) == 1,
        "migrations": conn.scalar(text("SELECT count(*) FROM mdm.migration")),
    })


def counts(args) -> int:
    return _print_mdm_report(lambda conn: dict(conn.execute(text(
        "SELECT 'entity',count(*) FROM mdm.current_entity "
        "UNION ALL SELECT object_type,count(*) FROM mdm.current_record "
        "WHERE object_type<>'entity' GROUP BY object_type"
    )).all()))


def force_publish(args) -> int:
    """Force publish (ticket 22): write the current snapshot for one consumer as
    forced pages (`mdm.force_publish`, no master data changes), then the input
    manifest of a publish target with one unit a page, for `rules run`. The
    same --run-id gives the same pages, so a stopped command is run again."""
    from uuid import UUID, uuid4

    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts

    run_id = str(UUID(args.run_id)) if args.run_id else str(uuid4())
    mdm = engine_from_env("MDM_DATABASE_URL")
    pages, after = [], {"object_type": "", "object_id": ""}
    try:
        while after is not None:
            with mdm.begin() as conn:
                page = conn.scalar(text(
                    "SELECT mdm.force_publish(:c,CAST(:r AS uuid),:p,:t,:i,:n)"),
                    {"c": args.consumer, "r": run_id, "p": len(pages) + 1, "t": after["object_type"],
                     "i": after["object_id"], "n": args.page_size})
            pages.append(page)
            after = page["next"]
    finally:
        mdm.dispose()
    store = Artifacts()
    root = Path(args.output).resolve().as_uri()
    units = [{"keys": {"batch_id": page["batch_id"], "consumer": args.consumer},
              # A page as MDM holds it; whether this call wrote it is not part of it.
              "input": store.put(f"{root}/pages", {"version": 1, "forced": True,
                                                   **{k: page[k] for k in ("batch_id", "generation", "records")}}),
              "output": f"{root}/published/{n}.json", "cursor": {}}
             for n, page in enumerate(pages, 1)]
    manifest = store.put(root, {"version": 2, "steps": {args.step: units}})
    print(json.dumps({"run_id": run_id, "consumer": args.consumer, "forced": True, "pages": len(pages),
                      "records": sum(page["records"] for page in pages), "manifest": manifest}, sort_keys=True))
    return 0
