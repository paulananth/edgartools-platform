"""Workflow entrypoint for the ``capture-filing-artifact`` acquisition command.

Ticket 15: carries one explicitly authorized SEC filing-artifact request
through the ledger-gated acquisition Facade into verified immutable Bronze
evidence and finalized ledger state. This command is genuinely new (there is
no legacy dispatch branch for it to preserve), so unlike
``load-daily-form-index-for-date`` it does not delegate into the legacy
``execute_standard_command``/``_execute_warehouse`` engine -- it drives the
Ticket 14 ledger and the Ticket 15 Facade directly.

It still writes the same declared run-manifest layers Ticket 13's
registration seam promises (bronze/staging/artifacts + a consolidated
run_manifest) using ``resolve_scope``/``planned_writes`` from its own
registration, so those two bundled behaviors are genuinely exercised at
runtime and not just unit-tested in isolation.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from edgar_warehouse.acquisition.facade import build_capture_facade
from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    DecisionOwnerRole,
    FetchDecisionRequest,
    FetchDisposition,
    execute_source_request,
)
from edgar_warehouse.acquisition.source_family_registry import (
    FILING_ARTIFACT_SOURCE_FAMILY,
    build_source_family_registry,
)
from edgar_warehouse.application.acquisition_command_registry import (
    acquisition_command_registration,
)
from edgar_warehouse.application.warehouse_orchestrator import _build_warehouse_context
from edgar_warehouse.infrastructure.run_manifest_builder import (
    layer_manifest,
    run_manifest,
    run_manifest_relative_path,
)
from edgar_warehouse.mdm.database import get_engine

DEFAULT_LEASE_SECONDS = 300
COMMAND_NAME = "capture-filing-artifact"


def run_capture_filing_artifact(args: Any) -> int:
    context = _build_warehouse_context(COMMAND_NAME)
    now = datetime.now(UTC)
    run_id = getattr(args, "run_id", None) or uuid.uuid4().hex
    arguments = {
        "candidate_id": args.candidate_id,
        "logical_source_key": args.logical_source_key,
        "source_url": args.source_url,
        "cause_reference": args.cause_reference,
    }

    registration = acquisition_command_registration(COMMAND_NAME)
    assert registration is not None, f"{COMMAND_NAME} is not registered"
    scope = registration.resolve_scope(arguments=arguments, now=now, silver_root=None)
    manifest_writes = _write_declared_layer_manifests(
        context=context, run_id=run_id, arguments=arguments, scope=scope, now=now
    )

    engine = get_engine()
    ledger = AcquisitionLedger(engine)
    registry = build_source_family_registry(identity=context.identity)
    worker_id = getattr(args, "worker_id", None) or f"capture-filing-artifact-{os.getpid()}"
    lease_seconds = getattr(args, "lease_seconds", None) or DEFAULT_LEASE_SECONDS

    request = FetchDecisionRequest(
        candidate_id=args.candidate_id,
        source_family=FILING_ARTIFACT_SOURCE_FAMILY,
        logical_source_key=args.logical_source_key,
        source_url=args.source_url,
        cause=DecisionCause.OPERATOR_REQUEST,
        cause_reference=args.cause_reference,
        disposition=FetchDisposition.FETCH_AUTHORIZED,
        blocker=None,
        next_action="FETCH_SOURCE",
        owner_role=DecisionOwnerRole.ACQUISITION_OPERATOR,
    )
    facade = build_capture_facade(ledger, context.bronze_root, registry, worker_id=worker_id)

    result = execute_source_request(
        ledger,
        request,
        facade,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )

    _write_consolidated_run_manifest(
        context=context,
        run_id=run_id,
        arguments=arguments,
        scope=scope,
        now=now,
        manifest_writes=manifest_writes,
    )

    payload: dict[str, Any] = {
        "decision_id": result.status.decision_id,
        "candidate_id": result.status.candidate_id,
        "source_family": result.status.source_family,
        "fetch_disposition": result.status.fetch_disposition.value,
        "is_terminal": result.status.is_terminal,
        "run_id": run_id,
    }
    if result.adapter_result is not None:
        artifact = result.adapter_result
        payload["artifact"] = {
            "raw_evidence_hash": artifact.raw_evidence_hash,
            "bronze_relative_path": artifact.bronze_relative_path,
            "byte_size": artifact.byte_size,
        }
    print(json.dumps(payload, sort_keys=True))
    return 0


def _write_declared_layer_manifests(
    *,
    context: Any,
    run_id: str,
    arguments: dict[str, Any],
    scope: dict[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    """Write the run-manifest layers ``planned_writes`` declared for this run.

    Mirrors ``warehouse_orchestrator._execute_warehouse_infrastructure_validation``'s
    write loop, scoped to what this command actually declares (bronze/staging/
    artifacts -- no silver/gold, this command never touches those layers).
    """
    registration = acquisition_command_registration(COMMAND_NAME)
    assert registration is not None, f"{COMMAND_NAME} is not registered"
    planned = registration.planned_writes(
        command_path=COMMAND_NAME, run_id=run_id, scope=scope
    )
    writes: list[dict[str, Any]] = []
    for layer, relative_path in planned.items():
        target = context.bronze_root if layer == "bronze" else context.storage_root
        manifest = layer_manifest(
            COMMAND_NAME,
            run_id,
            layer,
            relative_path,
            arguments,
            scope,
            now,
            context.runtime_mode,
        )
        writes.append(
            {
                "layer": layer,
                "path": target.write_json(relative_path, manifest),
                "relative_path": relative_path,
            }
        )
    return writes


def _write_consolidated_run_manifest(
    *,
    context: Any,
    run_id: str,
    arguments: dict[str, Any],
    scope: dict[str, Any],
    now: datetime,
    manifest_writes: list[dict[str, Any]],
) -> dict[str, Any]:
    relative_path = run_manifest_relative_path(COMMAND_NAME, run_id)
    payload = run_manifest(
        command_name=COMMAND_NAME,
        run_id=run_id,
        command_path=COMMAND_NAME,
        arguments=arguments,
        scope=scope,
        now=now,
        runtime_mode=context.runtime_mode,
        environment_name=context.environment_name,
        manifest_writes=manifest_writes,
        row_counts={},
    )
    return {
        "layer": "run_manifest",
        "path": context.bronze_root.write_json(relative_path, payload),
        "relative_path": relative_path,
    }
