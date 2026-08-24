from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Generic, TypeVar

from sqlalchemy import Engine, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from edgar_warehouse.acquisition.models import (
    SourceFetchDecisionRecord,
    SourceFetchTransitionRecord,
    SourceFetchWorkRecord,
    SourceObservationCursor,
)


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


class FetchWorkState(StrEnum):
    READY = "READY"
    LEASED = "LEASED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"


class FetchTransitionRole(StrEnum):
    ACQUISITION_COORDINATOR = "ACQUISITION_COORDINATOR"
    ACQUISITION_WORKER = "ACQUISITION_WORKER"
    ACQUISITION_OPERATOR = "ACQUISITION_OPERATOR"


class ProcessingTransitionRole(StrEnum):
    """The database roles that own the processing lifecycle (Ticket 18/19).

    Ticket 03's authority model gives fetch and processing separate ledger
    lifecycles with separate owners -- and within processing, splits
    "processors claim work" from "the Silver finalizer verifies and
    finalizes publications" as two distinct owners. ``ACQUISITION_PROCESSOR``
    (Ticket 18) seals what a revision requires (materializes the revision,
    seals its expected Silver producer set); ``ACQUISITION_SILVER_FINALIZER``
    (Ticket 19) is the only role that may record a producer's verified
    outcome. Kept as two members of one enum rather than two separate enums
    since both are still "processing lifecycle" roles in Ticket 03's sense,
    distinct from ``FetchTransitionRole``.
    """

    ACQUISITION_PROCESSOR = "ACQUISITION_PROCESSOR"
    ACQUISITION_SILVER_FINALIZER = "ACQUISITION_SILVER_FINALIZER"


class RegistryTransitionRole(StrEnum):
    """The database role that owns Source Family Registry versioning (Ticket 20).

    A distinct responsibility from every fetch/processing role above:
    deciding *what's in scope* (opening a draft version, advancing catch-up
    progress, activating or blocking a version) is governance over the
    acquisition universe itself, not a step within it. One member, not a
    pair like ``ProcessingTransitionRole`` -- registry versioning has no
    equivalent split responsibility the way "seal expected work" and
    "verify the outcome" are split in Ticket 19.
    """

    ACQUISITION_REGISTRY_OWNER = "ACQUISITION_REGISTRY_OWNER"


class CandidateDecisionConflict(RuntimeError):
    """A candidate identity was reused for a different immutable decision."""


class UnauthorizedDecisionRole(PermissionError):
    """The caller role does not own the requested decision cause."""


class ActiveFetchConflict(RuntimeError):
    """Another decision already owns active fetch work for the logical key."""


class StaleFencingToken(RuntimeError):
    """A worker tried to mutate fetch work after losing its fenced lease."""


class UnauthorizedTransitionRole(PermissionError):
    """A non-owner role attempted a fetch-work transition."""


class InvalidDecisionEvidence(ValueError):
    """A terminal no-download decision lacks its authoritative proof reference."""


TERMINAL_NO_DOWNLOAD_DISPOSITIONS = frozenset(
    {
        FetchDisposition.ALREADY_CAPTURED_VERIFIED,
        FetchDisposition.OUT_OF_SCOPE,
        FetchDisposition.OPERATOR_EXCLUDED,
    }
)


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


@dataclass(frozen=True)
class SourceChangeStatus:
    decision_id: str
    candidate_id: str
    source_family: str
    logical_source_key: str
    source_url: str
    observation_position: int
    cause: DecisionCause
    fetch_disposition: FetchDisposition
    fetch_state: FetchWorkState | None
    captured_artifact_reference: str | None
    blocker: str | None
    next_action: str
    is_terminal: bool

    @property
    def may_fetch(self) -> bool:
        return (
            self.fetch_disposition is FetchDisposition.FETCH_AUTHORIZED
            and self.fetch_state is FetchWorkState.LEASED
        )


class AcquisitionLedger:
    """Transaction boundary for source-fetch decisions and status reads."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_fetch_decision(
        self, request: FetchDecisionRequest
    ) -> SourceChangeStatus:
        _validate_decision_owner(request)
        _validate_terminal_evidence(request)
        try:
            with Session(self._engine) as session, session.begin():
                set_postgres_role(session, request.owner_role.value)
                existing = session.scalar(
                    select(SourceFetchDecisionRecord).where(
                        SourceFetchDecisionRecord.candidate_id == request.candidate_id
                    )
                )
                if existing is not None:
                    if not _decision_matches_request(existing, request):
                        raise CandidateDecisionConflict(
                            f"candidate_id={request.candidate_id} already has a different "
                            "Source Fetch Decision"
                        )
                    work = session.get(SourceFetchWorkRecord, existing.decision_id)
                    return _status_from_record(existing, work)

                position = reserve_observation_position(
                    session, request.source_family, request.logical_source_key
                )

                decision = SourceFetchDecisionRecord(
                    candidate_id=request.candidate_id,
                    source_family=request.source_family,
                    logical_source_key=request.logical_source_key,
                    source_url=request.source_url,
                    observation_position=position,
                    cause=request.cause.value,
                    cause_reference=request.cause_reference,
                    owner_role=request.owner_role.value,
                    fetch_disposition=request.disposition.value,
                    blocker=request.blocker,
                    next_action=request.next_action,
                    next_eligible_at=request.next_eligible_at,
                    verified_evidence_reference=request.verified_evidence_reference,
                    scope_proof_reference=request.scope_proof_reference,
                    operator_authorization_reference=(
                        request.operator_authorization_reference
                    ),
                )
                session.add(decision)
                session.flush()
                work = None
                if request.disposition is FetchDisposition.FETCH_AUTHORIZED:
                    work = SourceFetchWorkRecord(
                        decision_id=decision.decision_id,
                        source_family=request.source_family,
                        logical_source_key=request.logical_source_key,
                        fetch_state=FetchWorkState.READY.value,
                        fencing_token=0,
                        lease_owner=None,
                        lease_expires_at=None,
                        last_transition_role=request.owner_role.value,
                    )
                    session.add(work)
                    session.flush()
                    if self._engine.dialect.name == "postgresql":
                        session.execute(
                            text(
                                "SELECT record_initial_source_fetch_transition("
                                ":decision_id, :owner_role)"
                            ),
                            {
                                "decision_id": decision.decision_id,
                                "owner_role": request.owner_role.value,
                            },
                        )
                    else:
                        session.add(
                            SourceFetchTransitionRecord(
                                decision_id=decision.decision_id,
                                from_state=None,
                                to_state=FetchWorkState.READY.value,
                                owner_role=request.owner_role.value,
                                fencing_token=0,
                                worker_id=None,
                                reason="FETCH_AUTHORIZED",
                                # SQLite's CURRENT_TIMESTAMP server_default is
                                # second-granularity, so a decision, claim, and
                                # finalize created within the same wall-clock
                                # second would otherwise tie on created_at and
                                # make latest_transition_reason's ordering
                                # ambiguous -- set it explicitly here with
                                # Python's microsecond-precision clock.
                                created_at=datetime.now(UTC),
                            )
                        )
                    session.flush()
                return _status_from_record(decision, work)
        except IntegrityError as error:
            if "source_fetch_work" in str(error):
                raise ActiveFetchConflict(
                    f"active fetch already exists for "
                    f"{request.source_family}/{request.logical_source_key}"
                ) from error
            raise

    def source_change_status(self, decision_id: str) -> SourceChangeStatus:
        with Session(self._engine) as session:
            set_postgres_role(session, DecisionOwnerRole.ACQUISITION_COORDINATOR.value)
            decision = session.scalar(
                select(SourceFetchDecisionRecord).where(
                    SourceFetchDecisionRecord.decision_id == decision_id
                )
            )
            if decision is None:
                raise KeyError(
                    f"No Source Fetch Decision with decision_id={decision_id}"
                )
            work = session.get(SourceFetchWorkRecord, decision_id)
            return _status_from_record(decision, work)

    def claim_fetch(
        self,
        decision_id: str,
        *,
        worker_id: str,
        lease_seconds: int,
        now: datetime | None = None,
        actor_role: FetchTransitionRole = FetchTransitionRole.ACQUISITION_WORKER,
    ) -> FetchLease:
        _require_worker_role(actor_role)
        claim_time = now or datetime.now(UTC)
        if self._engine.dialect.name == "postgresql":
            with Session(self._engine) as session, session.begin():
                set_postgres_role(
                    session, FetchTransitionRole.ACQUISITION_WORKER.value
                )
                row = session.execute(
                    text(
                        "SELECT fencing_token, lease_expires_at "
                        "FROM claim_source_fetch(:decision_id, :worker_id, "
                        ":lease_seconds, :claimed_at)"
                    ),
                    {
                        "decision_id": decision_id,
                        "worker_id": worker_id,
                        "lease_seconds": lease_seconds,
                        "claimed_at": claim_time,
                    },
                ).one()
                return FetchLease(
                    decision_id=decision_id,
                    worker_id=worker_id,
                    fencing_token=int(row.fencing_token),
                    lease_expires_at=_require_datetime(row.lease_expires_at),
                )
        with Session(self._engine) as session, session.begin():
            work = session.get(SourceFetchWorkRecord, decision_id)
            if work is None:
                raise KeyError(f"No active fetch work for decision_id={decision_id}")
            previous_state = FetchWorkState(work.fetch_state)
            previous_token = work.fencing_token
            previous_expiry = _normalized_datetime(work.lease_expires_at)
            claimable = previous_state in {
                FetchWorkState.READY,
                FetchWorkState.FAILED,
            } or (
                previous_state is FetchWorkState.LEASED
                and previous_expiry is not None
                and previous_expiry <= claim_time
            )
            if not claimable:
                raise ActiveFetchConflict(
                    f"fetch work is not claimable for {decision_id}"
                )
            result = session.execute(
                update(SourceFetchWorkRecord)
                .where(
                    SourceFetchWorkRecord.decision_id == decision_id,
                    SourceFetchWorkRecord.fetch_state == previous_state.value,
                    SourceFetchWorkRecord.fencing_token == previous_token,
                    or_(
                        SourceFetchWorkRecord.fetch_state == FetchWorkState.READY.value,
                        SourceFetchWorkRecord.fetch_state
                        == FetchWorkState.FAILED.value,
                        SourceFetchWorkRecord.lease_expires_at <= claim_time,
                    ),
                )
                .values(
                    fetch_state=FetchWorkState.LEASED.value,
                    fencing_token=previous_token + 1,
                    lease_owner=worker_id,
                    lease_expires_at=claim_time + timedelta(seconds=lease_seconds),
                    last_transition_role="ACQUISITION_WORKER",
                    updated_at=claim_time,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise ActiveFetchConflict(f"fetch lease raced for {decision_id}")
            token = previous_token + 1
            session.add(
                SourceFetchTransitionRecord(
                    decision_id=decision_id,
                    from_state=previous_state.value,
                    to_state=FetchWorkState.LEASED.value,
                    owner_role="ACQUISITION_WORKER",
                    fencing_token=token,
                    worker_id=worker_id,
                    reason="LEASE_ACQUIRED",
                    created_at=claim_time,
                )
            )
            session.flush()
            return FetchLease(
                decision_id=decision_id,
                worker_id=worker_id,
                fencing_token=token,
                lease_expires_at=claim_time + timedelta(seconds=lease_seconds),
            )

    def finalize_fetch(
        self,
        decision_id: str,
        *,
        worker_id: str,
        fencing_token: int,
        final_state: FetchWorkState,
        artifact_reference: str | None = None,
        failure_detail: str | None = None,
        now: datetime | None = None,
        actor_role: FetchTransitionRole = FetchTransitionRole.ACQUISITION_WORKER,
    ) -> SourceChangeStatus:
        _require_worker_role(actor_role)
        if final_state not in {FetchWorkState.CAPTURED, FetchWorkState.FAILED}:
            raise ValueError("final_state must be CAPTURED or FAILED")
        if final_state is FetchWorkState.CAPTURED and not (artifact_reference or "").strip():
            raise ValueError("artifact_reference is required when final_state is CAPTURED")
        if final_state is FetchWorkState.CAPTURED and (failure_detail or "").strip():
            raise ValueError("failure_detail must not be set when final_state is CAPTURED")
        reason = (failure_detail or "").strip() or f"FETCH_{final_state.value}"
        finalize_time = now or datetime.now(UTC)
        if self._engine.dialect.name == "postgresql":
            with Session(self._engine) as session, session.begin():
                set_postgres_role(
                    session, FetchTransitionRole.ACQUISITION_WORKER.value
                )
                try:
                    session.execute(
                        text(
                            "SELECT finalize_source_fetch(:decision_id, :worker_id, "
                            ":fencing_token, :final_state, :finalized_at, "
                            ":artifact_reference, :failure_detail)"
                        ),
                        {
                            "decision_id": decision_id,
                            "worker_id": worker_id,
                            "fencing_token": fencing_token,
                            "final_state": final_state.value,
                            "finalized_at": finalize_time,
                            "artifact_reference": artifact_reference,
                            "failure_detail": failure_detail,
                        },
                    )
                except SQLAlchemyError as error:
                    # finalize_source_fetch's stale-token RAISE EXCEPTION
                    # surfaces here as a generic driver error, not the
                    # Python StaleFencingToken type the SQLite/generic
                    # branch below raises directly -- translate it so
                    # callers (e.g. the Facade's bounded finalize retry,
                    # which must never retry a deterministic "someone newer
                    # already won" race) can catch one type regardless of
                    # dialect.
                    if "stale fencing token" in str(error.orig or error):
                        raise StaleFencingToken(
                            f"stale fencing token {fencing_token} for "
                            f"decision_id={decision_id}"
                        ) from error
                    raise
            return self.source_change_status(decision_id)
        with Session(self._engine) as session, session.begin():
            result = session.execute(
                update(SourceFetchWorkRecord)
                .where(
                    SourceFetchWorkRecord.decision_id == decision_id,
                    SourceFetchWorkRecord.fetch_state == FetchWorkState.LEASED.value,
                    SourceFetchWorkRecord.lease_owner == worker_id,
                    SourceFetchWorkRecord.fencing_token == fencing_token,
                    SourceFetchWorkRecord.lease_expires_at > finalize_time,
                )
                .values(
                    fetch_state=final_state.value,
                    lease_owner=None,
                    lease_expires_at=None,
                    last_transition_role="ACQUISITION_WORKER",
                    captured_artifact_reference=artifact_reference,
                    updated_at=finalize_time,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise StaleFencingToken(
                    f"stale fencing token {fencing_token} for decision_id={decision_id}"
                )
            session.add(
                SourceFetchTransitionRecord(
                    decision_id=decision_id,
                    from_state=FetchWorkState.LEASED.value,
                    to_state=final_state.value,
                    owner_role="ACQUISITION_WORKER",
                    fencing_token=fencing_token,
                    worker_id=worker_id,
                    reason=reason,
                    created_at=finalize_time,
                )
            )
            session.flush()
            decision = session.get(SourceFetchDecisionRecord, decision_id)
            work = session.get(SourceFetchWorkRecord, decision_id)
            if decision is None or work is None:
                raise KeyError(
                    f"No Source Fetch Decision with decision_id={decision_id}"
                )
            session.refresh(work)
            return _status_from_record(decision, work)

    def latest_transition_reason(self, decision_id: str) -> str | None:
        """Return the most recent transition's durable reason/detail, if any.

        The primary read path for Fetch Attempt evidence (Ticket 17 bullet
        3): a non-success finalize records its failure detail (or a generic
        fallback) in ``source_fetch_transition.reason`` -- this makes that
        evidence queryable independently of whatever exception the original
        caller happened to catch, e.g. for an operator inspecting a
        long-since-failed decision in a different process.
        """

        with Session(self._engine) as session:
            set_postgres_role(session, DecisionOwnerRole.ACQUISITION_COORDINATOR.value)
            row = session.execute(
                select(SourceFetchTransitionRecord.reason)
                .where(SourceFetchTransitionRecord.decision_id == decision_id)
                .order_by(SourceFetchTransitionRecord.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            return row


AdapterResult = TypeVar("AdapterResult")


@dataclass(frozen=True)
class SourceRequestResult(Generic[AdapterResult]):
    status: SourceChangeStatus
    fetch_lease: FetchLease | None
    adapter_result: AdapterResult | None


@dataclass(frozen=True)
class FetchLease:
    decision_id: str
    worker_id: str
    fencing_token: int
    lease_expires_at: datetime


def execute_source_request(
    ledger: AcquisitionLedger,
    request: FetchDecisionRequest,
    source_adapter: Callable[[SourceChangeStatus, FetchLease], AdapterResult],
    *,
    worker_id: str,
    lease_seconds: int = 300,
) -> SourceRequestResult[AdapterResult]:
    """Commit and fence the PostgreSQL decision before a network request."""

    status = ledger.create_fetch_decision(request)
    if status.fetch_disposition is not FetchDisposition.FETCH_AUTHORIZED:
        return SourceRequestResult(status=status, fetch_lease=None, adapter_result=None)
    lease = ledger.claim_fetch(
        status.decision_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    leased_status = ledger.source_change_status(status.decision_id)
    if not leased_status.may_fetch:
        raise ActiveFetchConflict(
            f"decision_id={status.decision_id} did not enter fenced LEASED state"
        )
    return SourceRequestResult(
        status=leased_status,
        fetch_lease=lease,
        adapter_result=source_adapter(leased_status, lease),
    )


def _status_from_record(
    decision: SourceFetchDecisionRecord, work: SourceFetchWorkRecord | None = None
) -> SourceChangeStatus:
    disposition = FetchDisposition(decision.fetch_disposition)
    fetch_state = FetchWorkState(work.fetch_state) if work is not None else None
    next_action = decision.next_action
    if fetch_state is FetchWorkState.LEASED:
        next_action = "FETCH_SOURCE"
    elif fetch_state is FetchWorkState.CAPTURED:
        next_action = "MATERIALIZE_SOURCE_REVISION"
    elif fetch_state is FetchWorkState.FAILED:
        next_action = "RETRY_FETCH"
    return SourceChangeStatus(
        decision_id=decision.decision_id,
        candidate_id=decision.candidate_id,
        source_family=decision.source_family,
        logical_source_key=decision.logical_source_key,
        source_url=decision.source_url,
        observation_position=decision.observation_position,
        cause=DecisionCause(decision.cause),
        fetch_disposition=disposition,
        fetch_state=fetch_state,
        captured_artifact_reference=(
            work.captured_artifact_reference if work is not None else None
        ),
        blocker=decision.blocker,
        next_action=next_action,
        is_terminal=disposition in TERMINAL_NO_DOWNLOAD_DISPOSITIONS,
    )


def reserve_observation_position(
    session: Session, source_family: str, logical_source_key: str
) -> int:
    """Atomically reserve the next per-key Source Observation Position.

    Shared by decision creation (ledger.py) and revision materialization
    (revisions.py, Ticket 18) -- both a Fetch Decision and a standalone
    reinterpretation revision occupy one unified per-key position timeline,
    so they share this one atomic counter rather than each keeping its own.
    """

    insert_factory = (
        sqlite_insert
        if session.get_bind().dialect.name == "sqlite"
        else postgresql_insert
    )
    statement = insert_factory(SourceObservationCursor).values(
        source_family=source_family,
        logical_source_key=logical_source_key,
        last_position=1,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[
            SourceObservationCursor.source_family,
            SourceObservationCursor.logical_source_key,
        ],
        set_={"last_position": SourceObservationCursor.last_position + 1},
    ).returning(SourceObservationCursor.last_position)
    return int(session.execute(statement).scalar_one())


def _validate_decision_owner(request: FetchDecisionRequest) -> None:
    expected_role = (
        DecisionOwnerRole.ACQUISITION_OPERATOR
        if request.cause is DecisionCause.OPERATOR_REQUEST
        else DecisionOwnerRole.ACQUISITION_COORDINATOR
    )
    if request.owner_role is not expected_role:
        raise UnauthorizedDecisionRole(
            f"{request.cause.value} decisions require {expected_role.value}"
        )


def _validate_terminal_evidence(request: FetchDecisionRequest) -> None:
    required_reference = {
        FetchDisposition.ALREADY_CAPTURED_VERIFIED: (
            "verified_evidence_reference",
            request.verified_evidence_reference,
        ),
        FetchDisposition.OUT_OF_SCOPE: (
            "scope_proof_reference",
            request.scope_proof_reference,
        ),
        FetchDisposition.OPERATOR_EXCLUDED: (
            "operator_authorization_reference",
            request.operator_authorization_reference,
        ),
    }.get(request.disposition)
    if required_reference is not None and (
        not required_reference[1] or not required_reference[1].strip()
    ):
        raise InvalidDecisionEvidence(
            f"{request.disposition.value} requires {required_reference[0]}"
        )


def _require_worker_role(actor_role: FetchTransitionRole) -> None:
    if actor_role is not FetchTransitionRole.ACQUISITION_WORKER:
        raise UnauthorizedTransitionRole(
            f"fetch-work transitions require {FetchTransitionRole.ACQUISITION_WORKER.value}"
        )


def require_processor_role(actor_role: ProcessingTransitionRole) -> None:
    """Shared by revisions.py (Ticket 18) and processing.py (Ticket 19,
    sealing) -- see ``_require_worker_role``.
    """

    if actor_role is not ProcessingTransitionRole.ACQUISITION_PROCESSOR:
        raise UnauthorizedTransitionRole(
            "processing transitions require "
            f"{ProcessingTransitionRole.ACQUISITION_PROCESSOR.value}"
        )


def require_silver_finalizer_role(actor_role: ProcessingTransitionRole) -> None:
    """Shared by processing.py (Ticket 19, recording producer outcomes).

    Distinct from ``require_processor_role`` -- Ticket 03 gives "processors
    claim work" and "the Silver finalizer verifies and finalizes
    publications" separate owners; only this role may record a verified or
    failed producer outcome.
    """

    if actor_role is not ProcessingTransitionRole.ACQUISITION_SILVER_FINALIZER:
        raise UnauthorizedTransitionRole(
            "Silver finalization requires "
            f"{ProcessingTransitionRole.ACQUISITION_SILVER_FINALIZER.value}"
        )


def require_registry_owner_role(actor_role: RegistryTransitionRole) -> None:
    """Shared by registry_ledger.py (Ticket 20, versioning the acquisition universe)."""

    if actor_role is not RegistryTransitionRole.ACQUISITION_REGISTRY_OWNER:
        raise UnauthorizedTransitionRole(
            "registry transitions require "
            f"{RegistryTransitionRole.ACQUISITION_REGISTRY_OWNER.value}"
        )


def set_postgres_role(session: Session, role: str) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    allowed_roles = {
        DecisionOwnerRole.ACQUISITION_COORDINATOR.value,
        DecisionOwnerRole.ACQUISITION_OPERATOR.value,
        FetchTransitionRole.ACQUISITION_WORKER.value,
        ProcessingTransitionRole.ACQUISITION_PROCESSOR.value,
        ProcessingTransitionRole.ACQUISITION_SILVER_FINALIZER.value,
        RegistryTransitionRole.ACQUISITION_REGISTRY_OWNER.value,
    }
    if role not in allowed_roles:
        raise UnauthorizedTransitionRole(f"Unknown acquisition database role {role}")
    session.execute(text(f"SET LOCAL ROLE edgartools_{role.lower()}"))


def _decision_matches_request(
    decision: SourceFetchDecisionRecord, request: FetchDecisionRequest
) -> bool:
    return (
        decision.source_family == request.source_family
        and decision.logical_source_key == request.logical_source_key
        and decision.source_url == request.source_url
        and decision.cause == request.cause.value
        and decision.cause_reference == request.cause_reference
        and decision.owner_role == request.owner_role.value
        and decision.fetch_disposition == request.disposition.value
        and decision.blocker == request.blocker
        and decision.next_action == request.next_action
        and decision.verified_evidence_reference == request.verified_evidence_reference
        and decision.scope_proof_reference == request.scope_proof_reference
        and decision.operator_authorization_reference
        == request.operator_authorization_reference
        and _normalized_datetime(decision.next_eligible_at)
        == _normalized_datetime(request.next_eligible_at)
    )


def _normalized_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_datetime(value: datetime | None) -> datetime:
    normalized = _normalized_datetime(value)
    if normalized is None:
        raise RuntimeError("PostgreSQL returned a fetch lease without an expiry")
    return normalized
