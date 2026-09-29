"""Pure acquisition decision vocabulary shared without a legacy store import."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DecisionCause(StrEnum):
    CAPTURED_DISCOVERY = "CAPTURED_DISCOVERY"
    DUE_POLICY = "DUE_POLICY"
    OPERATOR_REQUEST = "OPERATOR_REQUEST"


class DecisionOwnerRole(StrEnum):
    ACQUISITION_COORDINATOR = "ACQUISITION_COORDINATOR"
    ACQUISITION_OPERATOR = "ACQUISITION_OPERATOR"


class FetchDisposition(StrEnum):
    FETCH_AUTHORIZED = "FETCH_AUTHORIZED"
    DOWNLOAD_DEFERRED = "DOWNLOAD_DEFERRED"
    ALREADY_CAPTURED_VERIFIED = "ALREADY_CAPTURED_VERIFIED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    OPERATOR_EXCLUDED = "OPERATOR_EXCLUDED"


@dataclass(frozen=True)
class FetchDecisionRequest:
    candidate_id: str
    source_family: str
    logical_source_key: str
    source_url: str
    cause: DecisionCause
    cause_reference: str
    disposition: FetchDisposition
    blocker: str | None
    next_action: str
    next_eligible_at: datetime | None = None
    owner_role: DecisionOwnerRole = DecisionOwnerRole.ACQUISITION_COORDINATOR
    verified_evidence_reference: str | None = None
    scope_proof_reference: str | None = None
    operator_authorization_reference: str | None = None
    exclusion_reason: str | None = None


def validate_decision_owner(request: FetchDecisionRequest) -> None:
    expected = (DecisionOwnerRole.ACQUISITION_OPERATOR
                if request.cause is DecisionCause.OPERATOR_REQUEST
                else DecisionOwnerRole.ACQUISITION_COORDINATOR)
    if request.owner_role is not expected:
        raise ValueError(f"{request.cause.value} decisions require {expected.value}")


def validate_terminal_evidence(request: FetchDecisionRequest) -> None:
    required = {
        FetchDisposition.ALREADY_CAPTURED_VERIFIED: request.verified_evidence_reference,
        FetchDisposition.OUT_OF_SCOPE: request.scope_proof_reference,
        FetchDisposition.OPERATOR_EXCLUDED: request.operator_authorization_reference,
    }.get(request.disposition)
    if request.disposition in {FetchDisposition.ALREADY_CAPTURED_VERIFIED,
                               FetchDisposition.OUT_OF_SCOPE, FetchDisposition.OPERATOR_EXCLUDED} and not required:
        raise ValueError(f"{request.disposition.value} requires verified decision evidence")
    if request.disposition is FetchDisposition.OPERATOR_EXCLUDED and not request.exclusion_reason:
        raise ValueError("Operator exclusion requires an explicit reason")
