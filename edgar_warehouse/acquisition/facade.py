"""Non-bypassable ledger-gated acquisition Facade (Ticket 15).

Carries an already-fenced Source Fetch Decision through content-addressed
immutable Bronze capture and ledger finalization. Every field this module
touches (source family, logical key, source URL) comes from the fenced
``SourceChangeStatus`` the caller hands in -- the Facade never invents a
URL, a logical key, a cause, or an authorization; it only ever runs after
``execute_source_request`` (ledger.py) has already created the decision and
claimed its fenced lease.

Per the change-propagation spec's Ticket 03 GoF constraints: source-family
variation lives behind the narrow ``SourceFamilyPolicy`` protocol as
first-class objects, selected by the caller-supplied registry -- this
module stays a Facade, not a second orchestrator, so it never branches on
source family itself. Authorization, hashing, Bronze finalization, and
ledger transitions are the Facade's own job and stay out of every Strategy.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    FetchDecisionRequest,
    FetchDisposition,
    FetchLease,
    FetchTransitionRole,
    FetchWorkState,
    SourceChangeStatus,
    StaleFencingToken,
    execute_source_request,
)
from edgar_warehouse.infrastructure.sec_client import download_sec_conditionally
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import (
    StorageLocation,
    read_bytes,
    sanitize_relative_path,
)

# Ticket 17 bullet 4: bounded retry around the CAPTURED finalize call only --
# not the fetch/write path, which already has its own retry story in
# sec_client.py. A transient DB hiccup right after a verified Bronze write
# must not immediately quarantine real evidence; a deterministic rejection
# (StaleFencingToken, a bad call shape) must never be retried at all, since
# retrying it would only delay recognizing a state that will never change.
DEFAULT_FINALIZE_CAPTURE_ATTEMPTS = 3
DEFAULT_FINALIZE_CAPTURE_RETRY_BASE_SECONDS = 0.5
_MAX_FAILURE_DETAIL_LENGTH = 2000


class SourceFamilyPolicy(Protocol):
    """Executable per-family fetch and completeness behavior.

    Deliberately narrow -- discovery, fetch, and completeness proof only.
    Shared authorization, hashing, Bronze finalization, and ledger
    transitions live in this module's Facade, never in a Strategy.
    """

    def fetch(self, source_url: str) -> bytes: ...

    def is_complete(self, payload: bytes) -> bool: ...


class SourceCaptureFailed(WarehouseRuntimeError):
    """A fenced decision's fetch, completeness proof, or Bronze capture failed."""


class OrphanedBronzeCapture(SourceCaptureFailed):
    """Bronze holds verified evidence that the ledger could not finalize.

    The fetch, write, and read-back verification all genuinely succeeded --
    this is raised only when every bounded attempt to finalize the CAPTURED
    disposition itself failed (e.g. sustained DB unavailability). Recording
    FAILED here would be a lie (the artifact *was* captured) and could mask
    real evidence behind a false failure, so the work row is deliberately
    left exactly as it was: LEASED, under this same fenced lease. Recovery
    is lease-gated, not immediately retryable -- a caller that retries
    before the lease expires gets ``ActiveFetchConflict`` from
    ``claim_fetch``, not a fresh attempt. Once the lease expires, a new
    claim on this SAME decision_id (never a different one -- an orphan can
    only ever attach back to the decision whose fenced lease produced it)
    re-fetches (idempotent by content hash -- no duplicate Bronze write) and
    retries finalization.
    """

    def __init__(
        self,
        *,
        decision_id: str,
        bronze_relative_path: str,
        raw_evidence_hash: str,
        cause: str,
    ) -> None:
        super().__init__(
            f"Bronze artifact {bronze_relative_path!r} for decision_id={decision_id} "
            "was verified but could not be finalized in the ledger after "
            f"{_finalize_capture_attempts()} attempt(s); it remains quarantined "
            "(no finalized decision references it) until the work lease expires "
            f"and a retry reclaims decision_id={decision_id} -- cause: {cause}"
        )
        self.decision_id = decision_id
        self.bronze_relative_path = bronze_relative_path
        self.raw_evidence_hash = raw_evidence_hash


@dataclass(frozen=True)
class CapturedArtifact:
    """The finalized outcome of one ledger-gated Bronze capture."""

    decision_id: str
    source_family: str
    logical_source_key: str
    raw_evidence_hash: str
    bronze_relative_path: str
    bronze_destination: str
    byte_size: int


CaptureFacade = Callable[[SourceChangeStatus, FetchLease], CapturedArtifact]


def build_capture_facade(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    registry: Mapping[str, SourceFamilyPolicy],
    *,
    worker_id: str,
) -> CaptureFacade:
    """Bind the shared ledger-gated capture sequence to one worker identity.

    The returned callable matches ``execute_source_request``'s
    ``source_adapter`` shape (``ledger.py``): that helper already performed
    authorization and lease fencing before ever invoking it, so everything
    this closure sees -- source family, logical key, URL -- is read from the
    already-fenced ``SourceChangeStatus``, never supplied by a caller of the
    returned callable.
    """

    def capture(status: SourceChangeStatus, lease: FetchLease) -> CapturedArtifact:
        if lease.decision_id != status.decision_id or lease.worker_id != worker_id:
            raise SourceCaptureFailed(
                "capture facade invoked with a lease that does not match the "
                "fenced decision it was handed"
            )
        if not status.may_fetch:
            raise SourceCaptureFailed(
                f"decision_id={status.decision_id} is not in a fetchable state "
                f"(disposition={status.fetch_disposition}, state={status.fetch_state})"
            )
        try:
            policy = registry.get(status.source_family)
            if policy is None:
                raise SourceCaptureFailed(
                    f"no Source Family Registry entry for source_family="
                    f"{status.source_family!r}"
                )
            payload = policy.fetch(status.source_url)
            if not policy.is_complete(payload):
                raise SourceCaptureFailed(
                    f"incomplete source payload for decision_id={status.decision_id} "
                    f"source_family={status.source_family!r}"
                )
            artifact = _capture_bronze_evidence(bronze_root, status, payload)
        except Exception as error:
            ledger.finalize_fetch(
                status.decision_id,
                worker_id=worker_id,
                fencing_token=lease.fencing_token,
                final_state=FetchWorkState.FAILED,
                failure_detail=_failure_detail(error),
                actor_role=FetchTransitionRole.ACQUISITION_WORKER,
            )
            raise
        _finalize_captured_with_retry(ledger, status, lease, artifact, worker_id=worker_id)
        return artifact

    return capture


class NoVerifiedCapture(SourceCaptureFailed):
    """A due re-poll was requested for a logical key that has never been CAPTURED."""


def execute_due_repoll(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    registry: Mapping[str, SourceFamilyPolicy],
    *,
    source_family: str,
    logical_source_key: str,
    source_url: str,
    identity: str,
    worker_id: str,
    lease_seconds: int = 300,
) -> SourceChangeStatus:
    """Create a DUE_POLICY decision and conditionally re-fetch one logical key.

    Ticket 28: a new Fetch Decision (CAPTURED cannot be reclaimed), validators
    from ``latest_verified_capture``, 304 links the prior Bronze reference
    with no write, 200 goes through the existing content-addressed capture.
    """

    prior = ledger.latest_verified_capture(source_family, logical_source_key)
    if prior is None:
        raise NoVerifiedCapture(
            f"no CAPTURED observation for {source_family}/{logical_source_key}"
        )
    policy = registry.get(source_family)
    if policy is None:
        raise SourceCaptureFailed(
            f"no Source Family Registry entry for source_family={source_family!r}"
        )

    request = FetchDecisionRequest(
        candidate_id=f"due-policy/{source_family}/{logical_source_key}/{uuid.uuid4().hex}",
        source_family=source_family,
        logical_source_key=logical_source_key,
        source_url=source_url,
        cause=DecisionCause.DUE_POLICY,
        cause_reference=f"due-policy:{prior.decision_id}",
        disposition=FetchDisposition.FETCH_AUTHORIZED,
        blocker=None,
        next_action="FETCH_SOURCE",
    )

    def _adapter(status: SourceChangeStatus, lease: FetchLease):
        try:
            response = download_sec_conditionally(
                status.source_url,
                identity,
                etag=prior.etag,
                last_modified=prior.last_modified,
            )
            if response.not_modified:
                linked = CapturedArtifact(
                    decision_id=status.decision_id,
                    source_family=source_family,
                    logical_source_key=logical_source_key,
                    raw_evidence_hash="",
                    bronze_relative_path=prior.captured_artifact_reference,
                    bronze_destination=prior.captured_artifact_reference,
                    byte_size=0,
                )
                _finalize_captured_with_retry(
                    ledger,
                    status,
                    lease,
                    linked,
                    worker_id=worker_id,
                    etag=response.etag or prior.etag,
                    last_modified=response.last_modified or prior.last_modified,
                )
                return None
            if not policy.is_complete(response.content):
                raise SourceCaptureFailed(
                    f"incomplete source payload for decision_id={status.decision_id} "
                    f"source_family={source_family!r}"
                )
            artifact = _capture_bronze_evidence(bronze_root, status, response.content)
        except Exception as error:
            ledger.finalize_fetch(
                status.decision_id,
                worker_id=worker_id,
                fencing_token=lease.fencing_token,
                final_state=FetchWorkState.FAILED,
                failure_detail=_failure_detail(error),
                actor_role=FetchTransitionRole.ACQUISITION_WORKER,
            )
            raise
        _finalize_captured_with_retry(
            ledger,
            status,
            lease,
            artifact,
            worker_id=worker_id,
            etag=response.etag,
            last_modified=response.last_modified,
        )
        return artifact

    result = execute_source_request(
        ledger,
        request,
        _adapter,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    return ledger.source_change_status(result.status.decision_id)


def _finalize_captured_with_retry(
    ledger: AcquisitionLedger,
    status: SourceChangeStatus,
    lease: FetchLease,
    artifact: CapturedArtifact,
    *,
    worker_id: str,
    etag: str | None = None,
    last_modified: str | None = None,
) -> None:
    """Finalize CAPTURED with a bounded retry for transient ledger failures.

    Never falls back to finalize(FAILED) -- see OrphanedBronzeCapture's
    docstring for why. A StaleFencingToken is never retried: it means a
    newer attempt already owns this decision, so this artifact was never
    orphaned in the first place, just superseded.
    """

    attempts = _finalize_capture_attempts()
    base_delay = _finalize_capture_retry_base_seconds()
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            ledger.finalize_fetch(
                status.decision_id,
                worker_id=worker_id,
                fencing_token=lease.fencing_token,
                final_state=FetchWorkState.CAPTURED,
                artifact_reference=artifact.bronze_relative_path,
                etag=etag,
                last_modified=last_modified,
                actor_role=FetchTransitionRole.ACQUISITION_WORKER,
            )
            return
        except StaleFencingToken:
            raise
        except Exception as error:  # noqa: BLE001 -- bounded retry, re-raised below
            last_error = error
            if attempt < attempts:
                time.sleep(base_delay * attempt)
    raise OrphanedBronzeCapture(
        decision_id=status.decision_id,
        bronze_relative_path=artifact.bronze_relative_path,
        raw_evidence_hash=artifact.raw_evidence_hash,
        cause=str(last_error),
    ) from last_error


def _finalize_capture_attempts() -> int:
    return int(
        os.environ.get(
            "WAREHOUSE_ACQUISITION_FINALIZE_CAPTURE_ATTEMPTS",
            DEFAULT_FINALIZE_CAPTURE_ATTEMPTS,
        )
    )


def _finalize_capture_retry_base_seconds() -> float:
    return float(
        os.environ.get(
            "WAREHOUSE_ACQUISITION_FINALIZE_CAPTURE_RETRY_BASE_SECONDS",
            DEFAULT_FINALIZE_CAPTURE_RETRY_BASE_SECONDS,
        )
    )


def _failure_detail(error: Exception) -> str:
    detail = f"{error.__class__.__name__}: {error}"
    return detail[:_MAX_FAILURE_DETAIL_LENGTH]


def _capture_bronze_evidence(
    bronze_root: StorageLocation, status: SourceChangeStatus, payload: bytes
) -> CapturedArtifact:
    """Content-addressed immutable write, plus an independent read-back check.

    ``write_immutable_bytes`` already does a byte-for-byte compare on the
    conflict path it takes when an object already exists at the key
    (create-once, verify-and-reuse) -- it does not read back a *fresh*
    write. This function performs its own read-back against the returned
    destination regardless of which internal path ran, so "content-addressed
    write, read-back verification, finalization of the exact artifact
    reference" (Ticket 15) holds on every capture, not only a repeat one.

    Keying by the raw evidence hash is what lets identical bytes reuse one
    Bronze object across different observations/decisions while each
    observation still gets its own ledger transition row -- the object
    write is idempotent by content; the ledger lineage is not shared.
    """
    raw_evidence_hash = hashlib.sha256(payload).hexdigest()
    relative_path = sanitize_relative_path(
        f"{status.source_family}/{raw_evidence_hash}"
    )
    destination = bronze_root.write_immutable_bytes(relative_path, payload)
    verified_payload = read_bytes(destination)
    if verified_payload != payload:
        raise SourceCaptureFailed(
            f"Bronze read-back mismatch for {relative_path!r} "
            f"(decision_id={status.decision_id})"
        )
    return CapturedArtifact(
        decision_id=status.decision_id,
        source_family=status.source_family,
        logical_source_key=status.logical_source_key,
        raw_evidence_hash=raw_evidence_hash,
        bronze_relative_path=relative_path,
        bronze_destination=destination,
        byte_size=len(payload),
    )
