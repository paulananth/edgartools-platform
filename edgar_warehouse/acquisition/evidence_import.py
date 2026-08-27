"""Checksum-verified Bronze evidence imported from another environment or
account, with preserved source lineage (Ticket 34).

Per the change-propagation spec (bullet 92, "immutable S3 objects and
cross-environment reference rejection"): nothing else in this codebase
reads Bronze evidence across environments -- each environment/account has
its own physically separate Bronze bucket, and no cross-account IAM role or
cross-bucket read path exists anywhere. This module is the *only* deliberate
way to bring foreign evidence in, and it does so explicitly, checksum-
verified, and audited -- never a raw cross-environment copy.

``import_evidence`` writes the verified bytes into *this* environment's
Bronze store using the same content-hash-keyed relative path scheme the
Ticket 14/15 capture Facade uses (``{source_family}/{raw_evidence_hash}``,
see ``facade._capture_bronze_evidence``), so imported evidence is
indistinguishable from a normally-captured object once it lands -- any
downstream code expecting that key shape finds it there. "Becomes
processable" (the ticket's own bullet) means exactly this: the returned
``local_bronze_reference`` is a legitimate local Bronze artifact reference,
usable as ``FetchDecisionRequest.verified_evidence_reference`` for a normal
``AcquisitionLedger.create_fetch_decision(disposition=ALREADY_CAPTURED_VERIFIED,
...)`` call -- no new disposition value or Facade path is needed, since
consuming an already-verified local reference is already fully supported.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from edgar_warehouse.acquisition.ledger import DecisionOwnerRole, require_operator_role, set_postgres_role
from edgar_warehouse.acquisition.models import SourceEvidenceImportRecord
from edgar_warehouse.infrastructure.object_storage import (
    StorageLocation,
    read_bytes,
    sanitize_relative_path,
)


class ChecksumVerificationFailed(ValueError):
    """The supplied payload's actual hash does not match the claimed source checksum."""


class InvalidImportEvidence(ValueError):
    """An import is missing its required operator authorization or reason."""


@dataclass(frozen=True)
class ImportedEvidence:
    import_id: str
    source_family: str
    logical_source_key: str
    source_environment: str
    source_bronze_reference: str
    raw_evidence_hash: str
    local_bronze_reference: str
    operator_authorization_reference: str
    reason: str


def _imported_evidence_from_record(record: SourceEvidenceImportRecord) -> ImportedEvidence:
    return ImportedEvidence(
        import_id=record.import_id,
        source_family=record.source_family,
        logical_source_key=record.logical_source_key,
        source_environment=record.source_environment,
        source_bronze_reference=record.source_bronze_reference,
        raw_evidence_hash=record.raw_evidence_hash,
        local_bronze_reference=record.local_bronze_reference,
        operator_authorization_reference=record.operator_authorization_reference,
        reason=record.reason,
    )


class EvidenceImportLedger:
    """Transaction boundary for importing cross-environment Bronze evidence."""

    def __init__(self, engine: Engine, bronze_root: StorageLocation) -> None:
        self._engine = engine
        self._bronze_root = bronze_root

    def import_evidence(
        self,
        *,
        source_family: str,
        logical_source_key: str,
        source_environment: str,
        source_bronze_reference: str,
        payload: bytes,
        expected_checksum: str,
        operator_authorization_reference: str,
        reason: str,
        actor_role: DecisionOwnerRole = DecisionOwnerRole.ACQUISITION_OPERATOR,
    ) -> ImportedEvidence:
        """Verify, write locally, and durably record one cross-environment import.

        Idempotent per ``(source_environment, source_bronze_reference)``: a
        replayed import of the exact same foreign evidence returns the
        existing row rather than re-verifying, re-writing, or duplicating
        the audit trail -- mirrors ``ConflictLedger.record_evidence_conflict``'s
        own idempotent-per-natural-key shape.

        Checksum verification happens *before* any Bronze write, so a
        mismatched payload never becomes processable even transiently
        (fails closed, not "written then flagged").
        """

        require_operator_role(actor_role)
        if not operator_authorization_reference.strip():
            raise InvalidImportEvidence(
                "import_evidence requires a non-empty operator_authorization_reference"
            )
        if not reason.strip():
            raise InvalidImportEvidence("import_evidence requires a non-empty reason")

        with Session(self._engine) as session:
            set_postgres_role(session, actor_role.value)
            existing = session.scalar(
                select(SourceEvidenceImportRecord).where(
                    SourceEvidenceImportRecord.source_environment == source_environment,
                    SourceEvidenceImportRecord.source_bronze_reference
                    == source_bronze_reference,
                )
            )
            if existing is not None:
                return _imported_evidence_from_record(existing)

        actual_hash = hashlib.sha256(payload).hexdigest()
        if actual_hash.lower() != expected_checksum.strip().lower():
            raise ChecksumVerificationFailed(
                f"expected_checksum={expected_checksum!r} does not match the "
                f"payload's actual checksum={actual_hash!r} for "
                f"source_bronze_reference={source_bronze_reference!r}"
            )

        relative_path = sanitize_relative_path(f"{source_family}/{actual_hash}")
        destination = self._bronze_root.write_immutable_bytes(relative_path, payload)
        verified_payload = read_bytes(destination)
        if verified_payload != payload:
            raise ChecksumVerificationFailed(
                f"Bronze read-back mismatch for {relative_path!r} imported from "
                f"source_environment={source_environment!r}"
            )

        with Session(self._engine) as session, session.begin():
            set_postgres_role(session, actor_role.value)
            existing = session.scalar(
                select(SourceEvidenceImportRecord).where(
                    SourceEvidenceImportRecord.source_environment == source_environment,
                    SourceEvidenceImportRecord.source_bronze_reference
                    == source_bronze_reference,
                )
            )
            if existing is not None:
                return _imported_evidence_from_record(existing)
            record = SourceEvidenceImportRecord(
                source_family=source_family,
                logical_source_key=logical_source_key,
                source_environment=source_environment,
                source_bronze_reference=source_bronze_reference,
                expected_checksum=expected_checksum,
                raw_evidence_hash=actual_hash,
                local_bronze_reference=relative_path,
                operator_authorization_reference=operator_authorization_reference,
                reason=reason,
            )
            session.add(record)
            session.flush()
            return _imported_evidence_from_record(record)
