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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    FetchLease,
    FetchTransitionRole,
    FetchWorkState,
    SourceChangeStatus,
)
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.infrastructure.object_storage import (
    StorageLocation,
    read_bytes,
    sanitize_relative_path,
)


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
        except Exception:
            ledger.finalize_fetch(
                status.decision_id,
                worker_id=worker_id,
                fencing_token=lease.fencing_token,
                final_state=FetchWorkState.FAILED,
                actor_role=FetchTransitionRole.ACQUISITION_WORKER,
            )
            raise
        ledger.finalize_fetch(
            status.decision_id,
            worker_id=worker_id,
            fencing_token=lease.fencing_token,
            final_state=FetchWorkState.CAPTURED,
            artifact_reference=artifact.bronze_relative_path,
            actor_role=FetchTransitionRole.ACQUISITION_WORKER,
        )
        return artifact

    return capture


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
