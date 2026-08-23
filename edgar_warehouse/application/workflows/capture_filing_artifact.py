"""Workflow entrypoint for the ``capture-filing-artifact`` acquisition command.

Ticket 15: carries one explicitly authorized SEC filing-artifact request
through the ledger-gated acquisition Facade into verified immutable Bronze
evidence and finalized ledger state. This command is genuinely new (there is
no legacy dispatch branch for it to preserve), so unlike
``load-daily-form-index-for-date`` it does not delegate into the legacy
``execute_standard_command``/``_execute_warehouse`` engine -- it drives the
Ticket 14 ledger and the Ticket 15 Facade directly.
"""

from __future__ import annotations

import json
import os
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
from edgar_warehouse.application.warehouse_orchestrator import _build_warehouse_context
from edgar_warehouse.mdm.database import get_engine

DEFAULT_LEASE_SECONDS = 300


def run_capture_filing_artifact(args: Any) -> int:
    context = _build_warehouse_context("capture-filing-artifact")
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

    payload: dict[str, Any] = {
        "decision_id": result.status.decision_id,
        "candidate_id": result.status.candidate_id,
        "source_family": result.status.source_family,
        "fetch_disposition": result.status.fetch_disposition.value,
        "is_terminal": result.status.is_terminal,
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
