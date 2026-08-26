"""Record and repair conflicting Bronze evidence for one immutable identity (Ticket 25).

Two responsibilities, kept in one small module because they share one
transactional boundary (resolving a conflict both closes the conflict row
and, when the conflicting evidence wins, materializes a new revision -- both
must commit together or neither does):

- ``record_evidence_conflict``: durably records a conflict a caller detected
  (typically by catching ``object_storage.ImmutableContentConflictError``
  around a Bronze write). Does not judge which evidence is right -- it only
  establishes, immutably, that two byte-sets both claimed one identity, with
  both retained (the conflicting payload's own quarantine object already
  exists in Bronze by the time this is called -- see that exception's own
  docstring).
- ``resolve_conflict``: the repair action (Ticket 25 bullet 2). An operator
  decision, authorized and reasoned, choosing which evidence is authoritative
  going forward -- ``"existing"`` (no new revision; the conflict simply
  closes, "without rewriting history" quite literally: nothing in
  ``source_revision`` changes) or ``"conflicting"`` (a new REPAIR child
  revision is materialized via ``revisions.SourceRevisionLedger.
  materialize_repair``, and the conflict closes pointing at it). Either way,
  ``repair_revision_id`` on the closed conflict names "the revision that is
  now authoritative for this identity" -- the pre-existing one if kept, a
  fresh REPAIR revision if not.

Both methods share the same database role as revision materialization
(``ProcessingTransitionRole.ACQUISITION_PROCESSOR``, migration 015's own
comment explains why this is not a new role) -- see ``ledger.py``'s
``require_processor_role``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from edgar_warehouse.acquisition.ledger import (
    ProcessingTransitionRole,
    require_processor_role,
    set_postgres_role,
)
from edgar_warehouse.acquisition.models import SourceEvidenceConflictRecord
from edgar_warehouse.acquisition.revisions import SourceRevision, SourceRevisionLedger

AcceptEvidence = Literal["existing", "conflicting"]


class ConflictNotFound(RuntimeError):
    """The referenced conflict does not exist."""


class ConflictAlreadyResolved(RuntimeError):
    """A resolution was attempted on a conflict that already settled."""


class InvalidResolutionEvidence(ValueError):
    """A resolution is missing its required operator authorization or reason."""


@dataclass(frozen=True)
class EvidenceConflict:
    conflict_id: str
    source_family: str | None
    logical_source_key: str | None
    relative_path: str
    existing_content_hash: str
    new_content_hash: str
    quarantine_bronze_reference: str
    status: str
    repair_revision_id: str | None
    operator_authorization_reference: str | None
    resolution_reason: str | None


def _conflict_from_record(record: SourceEvidenceConflictRecord) -> EvidenceConflict:
    return EvidenceConflict(
        conflict_id=record.conflict_id,
        source_family=record.source_family,
        logical_source_key=record.logical_source_key,
        relative_path=record.relative_path,
        existing_content_hash=record.existing_content_hash,
        new_content_hash=record.new_content_hash,
        quarantine_bronze_reference=record.quarantine_bronze_reference,
        status=record.status,
        repair_revision_id=record.repair_revision_id,
        operator_authorization_reference=record.operator_authorization_reference,
        resolution_reason=record.resolution_reason,
    )


class ConflictLedger:
    """Transaction boundary for recording and resolving evidence conflicts."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._revisions = SourceRevisionLedger(engine)

    def record_evidence_conflict(
        self,
        *,
        relative_path: str,
        existing_content_hash: str,
        new_content_hash: str,
        quarantine_bronze_reference: str,
        source_family: str | None = None,
        logical_source_key: str | None = None,
        actor_role: ProcessingTransitionRole = (
            ProcessingTransitionRole.ACQUISITION_PROCESSOR
        ),
    ) -> EvidenceConflict:
        """Record one conflict. Idempotent per ``quarantine_bronze_reference``
        (the same unique constraint that already prevents the underlying
        Bronze quarantine object from being written twice under different
        hashes -- see migration 015): a replayed detection of the exact same
        conflict returns the existing row rather than raising or duplicating.
        """

        require_processor_role(actor_role)
        with Session(self._engine) as session, session.begin():
            set_postgres_role(session, actor_role.value)
            existing = session.scalar(
                select(SourceEvidenceConflictRecord).where(
                    SourceEvidenceConflictRecord.quarantine_bronze_reference
                    == quarantine_bronze_reference
                )
            )
            if existing is not None:
                return _conflict_from_record(existing)
            record = SourceEvidenceConflictRecord(
                source_family=source_family,
                logical_source_key=logical_source_key,
                relative_path=relative_path,
                existing_content_hash=existing_content_hash,
                new_content_hash=new_content_hash,
                quarantine_bronze_reference=quarantine_bronze_reference,
            )
            session.add(record)
            session.flush()
            return _conflict_from_record(record)

    def list_pending_conflicts(
        self,
        *,
        actor_role: ProcessingTransitionRole = (
            ProcessingTransitionRole.ACQUISITION_PROCESSOR
        ),
    ) -> tuple[EvidenceConflict, ...]:
        """Every conflict awaiting operator repair, oldest first."""

        with Session(self._engine) as session:
            set_postgres_role(session, actor_role.value)
            records = session.scalars(
                select(SourceEvidenceConflictRecord)
                .where(SourceEvidenceConflictRecord.status == "PENDING")
                .order_by(SourceEvidenceConflictRecord.detected_at)
            ).all()
            return tuple(_conflict_from_record(record) for record in records)

    def resolve_conflict(
        self,
        conflict_id: str,
        *,
        parent_revision_id: str,
        accept: AcceptEvidence,
        operator_authorization_reference: str,
        reason: str,
        actor_role: ProcessingTransitionRole = (
            ProcessingTransitionRole.ACQUISITION_PROCESSOR
        ),
    ) -> tuple[EvidenceConflict, SourceRevision | None]:
        """Repair one conflict (Ticket 25 bullet 2).

        ``parent_revision_id`` is the revision the conflict's existing
        content corresponds to -- supplied by the caller (typically an
        operator who already looked it up via Source Change Status), not
        inferred here, since the conflict itself is recorded independently
        of any specific revision (see this module's own docstring).

        Idempotent per ``conflict_id``: a replayed resolve call against an
        already-``REPAIRED`` conflict returns its settled state rather than
        re-resolving or raising -- but only if the replay's own ``accept``
        argument agrees with what was actually decided the first time
        (``accept="conflicting"`` must find a ``repair_revision_id`` that is
        NOT the parent; ``accept="existing"`` must find one that IS). A
        mismatched replay is a genuine caller error (asking to resolve
        something already resolved differently), not a benign duplicate, so
        it raises ``ConflictAlreadyResolved`` rather than silently returning
        the wrong outcome.

        Race safety is a ``SELECT ... FOR UPDATE`` row lock on the conflict,
        not a read-then-write CAS -- deliberately: an earlier draft read the
        conflict, called ``materialize_repair`` (its own, separate
        transaction) for ``accept="conflicting"``, and only *then* attempted
        a conditional ``UPDATE``. Under a genuine race against a concurrent
        ``accept="existing"`` resolve, the loser's already-materialized
        REPAIR revision had no way to be un-created -- a permanent,
        audit-orphaned revision with nothing pointing at it. Locking the
        conflict row first serializes concurrent resolves of the *same*
        conflict: the second caller blocks until the first commits, then
        finds the row already ``REPAIRED`` and never calls
        ``materialize_repair`` at all.
        """

        if not operator_authorization_reference.strip():
            raise InvalidResolutionEvidence(
                "resolve_conflict requires a non-empty operator_authorization_reference"
            )
        if not reason.strip():
            raise InvalidResolutionEvidence("resolve_conflict requires a non-empty reason")

        require_processor_role(actor_role)
        with Session(self._engine) as session, session.begin():
            set_postgres_role(session, actor_role.value)
            conflict = session.execute(
                select(SourceEvidenceConflictRecord)
                .where(SourceEvidenceConflictRecord.conflict_id == conflict_id)
                .with_for_update()
            ).scalar_one_or_none()
            if conflict is None:
                raise ConflictNotFound(f"conflict_id={conflict_id} does not exist")

            if conflict.status == "REPAIRED":
                settled_as_conflicting = conflict.repair_revision_id != parent_revision_id
                if (accept == "conflicting") != settled_as_conflicting:
                    raise ConflictAlreadyResolved(
                        f"conflict_id={conflict_id} was already resolved with a different "
                        f"outcome than accept={accept!r} requests"
                    )
                # Already settled -- the conflict row itself (repair_revision_id)
                # is the durable record of the outcome; not re-fetching the full
                # SourceRevision object here to avoid reaching into
                # SourceRevisionLedger's private lookup from a caller outside it.
                return _conflict_from_record(conflict), None

            revision: SourceRevision | None = None
            if accept == "conflicting":
                # Safe to call while still holding the row lock: this opens
                # its own session/transaction against source_revision, a
                # different table, so it neither blocks on nor is blocked by
                # the lock held here.
                revision = self._revisions.materialize_repair(
                    parent_revision_id,
                    new_raw_evidence_hash=conflict.new_content_hash,
                    new_bronze_artifact_reference=conflict.quarantine_bronze_reference,
                    actor_role=actor_role,
                )
                repair_revision_id = revision.revision_id
            else:
                repair_revision_id = parent_revision_id

            conflict.status = "REPAIRED"
            conflict.repair_revision_id = repair_revision_id
            conflict.resolved_at = datetime.now(UTC)
            conflict.operator_authorization_reference = operator_authorization_reference
            conflict.resolution_reason = reason
            session.flush()
            return _conflict_from_record(conflict), revision
