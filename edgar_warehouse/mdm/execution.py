"""A prepared batch's records, read from its file under the source's registered reading.

`mastering.merge` reads each batch with `batch_input`; `runtime_files` names the code a merge pins.
"""

from __future__ import annotations

import hashlib
import json
import math
from inspect import getfile
from pathlib import Path
from typing import Any


from . import limits
from .activation import check_policy
from .adapters import UnsupportedRecord, normalize
from .evidence import deferred_record
from .store import Conflict, Store, current_reading, reading_at, storage_adapter


def runtime_files() -> list[Path]:
    """The execution module owns the code its caller must pin."""
    from edgar_warehouse.bookkeeping.clean import config, destinations
    from edgar_warehouse.mdm import (
        activation, adapters, assessment, binding, cascade, catalog, classification,
        correction, evidence, identifier_types, identity, matching, merge, registration, retirement,
        name_count, names, prepared, prepared_registry, prepared_publication, prepared_runs, master_reads, master_index, master_search, detail_lookups, record_reads, primitives, quality, relationships, run, schema, scope, store, survivorship,
    )
    from edgar_warehouse.rules import files, source_engine
    from edgar_warehouse.workers import source_mapping

    # Explicit execution dependencies, including destination authority.
    # CLI presentation is not executable merge behavior. This is not
    # the separately tracked complete environment/reproducibility fingerprint.
    modules = (activation, adapters, assessment, binding, cascade, catalog, classification, config,
               correction, destinations, evidence, files, identifier_types,
               identity, limits, matching, merge, name_count, names, prepared, prepared_registry, prepared_publication, prepared_runs, master_reads, master_index, master_search, detail_lookups, record_reads, primitives, quality,
               relationships, registration, retirement, run, schema, scope, source_mapping, store, survivorship)
    adapter = store.storage_adapter()
    adapter_files = [Path(getfile(adapter)).with_name(name) for name in
                     ("database_adapter.py", "adapter_model.py", "adapter_sql.py", "registry_migration.py")]
    return [Path(__file__), *[Path(getfile(module)) for module in modules],
            *source_engine.runtime_files(), catalog.path(), *adapter_files,
            *[Path(store.__file__).parent / "migrations" / module.MIGRATION
              for module in (registration, retirement)]]


def _reject_json_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


def _finite_json_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("JSON number exceeds finite float range")
    return result


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
            policy = storage_adapter().registered_policy(conn, policy_digest)
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
    row: Any  # JSON is unvalidated until normalize accepts it or retains its refusal.
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
