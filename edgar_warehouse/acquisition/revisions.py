"""Materialize ordered, immutable Logical Source Revisions (Ticket 18).

Converts a verified Bronze capture (a CAPTURED Source Fetch Decision, Ticket
14/15) into a Logical Source Revision -- the durable, ordered record of what
actually changed, independent of transport identity or operational
timestamps. Per Ticket 03's "Source revision identity and ordering" section,
a revision binds source family/key, its reserved per-key Source Observation
Position, the exact raw-byte hash, a versioned canonical-source hash (after
transport-only normalization), a versioned domain-content hash (after
interpretation), contract/parser/schema/configuration identities, a
completeness declaration, and verified Bronze evidence lineage. ``run_id``,
S3 key, arrival time, ETag alone, and mutable "latest" pointers are
deliberately absent from both the schema and this module's public functions
-- they are not source identity.

Processing is its own ledger lifecycle, separate from fetching (Ticket 03),
so this module -- not ``AcquisitionLedger`` -- owns revision materialization,
under its own database role (``ProcessingTransitionRole.ACQUISITION_PROCESSOR``).

Two ways a revision comes to exist:

- ``materialize_from_capture``: a fresh capture. Idempotent per
  ``decision_id`` -- replaying a drive call that already produced a revision
  returns the existing one rather than creating a duplicate.
- ``materialize_reinterpretation``: a parser/schema/contract/configuration
  upgrade reprocessing an already-verified Bronze artifact *without* a new
  SEC fetch (Ticket 18 bullet 4's first half). Reuses the parent revision's
  raw evidence hash, canonical-source hash, and Bronze artifact reference
  unchanged -- only the domain-content hash and interpretation identities are
  supplied fresh, since interpretation is the only thing that changed.
  Idempotent per (parent_revision_id, contract/parser/schema/configuration
  version tuple).

Both determine ``content_impact`` (``CHANGED`` vs. an explicit,
publication-backed ``NO_IMPACT``, Ticket 18 bullet 4's second half) by
comparing the new domain-content hash against the immediately preceding
revision for the same logical key -- the first revision for a key is always
``CHANGED``, since there is no prior state to compare against.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from edgar_warehouse.acquisition.ledger import (
    FetchWorkState,
    ProcessingTransitionRole,
    require_processor_role,
    reserve_observation_position,
    set_postgres_role,
)
from edgar_warehouse.acquisition.models import (
    SourceFetchDecisionRecord,
    SourceFetchWorkRecord,
    SourceRevisionRecord,
)


class ContentImpact(StrEnum):
    CHANGED = "CHANGED"
    NO_IMPACT = "NO_IMPACT"


class CompletenessType(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


class RevisionRelationship(StrEnum):
    REPAIR = "REPAIR"
    SUPERSESSION = "SUPERSESSION"
    COALESCING = "COALESCING"
    REINTERPRETATION = "REINTERPRETATION"


class RevisionNotEligible(RuntimeError):
    """The referenced decision or parent revision cannot produce a revision."""


@dataclass(frozen=True)
class SourceRevision:
    revision_id: str
    decision_id: str | None
    parent_revision_id: str | None
    revision_relationship: RevisionRelationship | None
    source_family: str
    logical_source_key: str
    observation_position: int
    source_native_revision: str | None
    raw_evidence_hash: str
    canonical_source_hash: str
    domain_content_hash: str
    contract_version: str
    parser_version: str
    schema_version: str
    configuration_version: str
    completeness_type: CompletenessType
    declared_replacement_scope: str | None
    bronze_artifact_reference: str
    content_impact: ContentImpact


class SourceRevisionLedger:
    """Transaction boundary for materializing Logical Source Revisions."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def materialize_from_capture(
        self,
        decision_id: str,
        *,
        raw_evidence_hash: str,
        canonical_source_hash: str,
        domain_content_hash: str,
        contract_version: str,
        parser_version: str,
        schema_version: str,
        configuration_version: str,
        completeness_type: CompletenessType = CompletenessType.COMPLETE,
        declared_replacement_scope: str | None = None,
        source_native_revision: str | None = None,
        actor_role: ProcessingTransitionRole = (
            ProcessingTransitionRole.ACQUISITION_PROCESSOR
        ),
    ) -> SourceRevision:
        """Materialize the revision for a CAPTURED Source Fetch Decision.

        Idempotent by ``decision_id`` -- a replayed call (e.g. a discovery
        drive rerun) returns the already-materialized revision rather than
        creating a duplicate or raising. Raises ``RevisionNotEligible`` if
        the decision does not exist or has not reached ``CAPTURED``.
        """

        require_processor_role(actor_role)
        existing = self._existing_from_capture(decision_id, actor_role=actor_role)
        if existing is not None:
            return existing
        try:
            with Session(self._engine) as session, session.begin():
                set_postgres_role(session, actor_role.value)
                decision = session.get(SourceFetchDecisionRecord, decision_id)
                work = session.get(SourceFetchWorkRecord, decision_id)
                if (
                    decision is None
                    or work is None
                    or FetchWorkState(work.fetch_state) is not FetchWorkState.CAPTURED
                ):
                    raise RevisionNotEligible(
                        f"decision_id={decision_id} is not a CAPTURED Source Fetch Decision"
                    )

                previous = _latest_revision_before(
                    session,
                    decision.source_family,
                    decision.logical_source_key,
                    decision.observation_position,
                )
                content_impact = _content_impact(previous, domain_content_hash)

                record = SourceRevisionRecord(
                    decision_id=decision_id,
                    parent_revision_id=None,
                    revision_relationship=None,
                    source_family=decision.source_family,
                    logical_source_key=decision.logical_source_key,
                    observation_position=decision.observation_position,
                    source_native_revision=source_native_revision,
                    raw_evidence_hash=raw_evidence_hash,
                    canonical_source_hash=canonical_source_hash,
                    domain_content_hash=domain_content_hash,
                    contract_version=contract_version,
                    parser_version=parser_version,
                    schema_version=schema_version,
                    configuration_version=configuration_version,
                    completeness_type=completeness_type.value,
                    declared_replacement_scope=declared_replacement_scope,
                    bronze_artifact_reference=work.captured_artifact_reference,
                    content_impact=content_impact.value,
                )
                session.add(record)
                session.flush()
                return _revision_from_record(record)
        except IntegrityError:
            # Lost a race against a concurrent materialization for this same
            # decision_id -- the unique constraint on decision_id is what
            # actually serializes this, not application logic. The failed
            # `with` block above already rolled itself back on the way out;
            # read the winner on a fresh session rather than reusing it.
            winner = self._existing_from_capture(decision_id, actor_role=actor_role)
            if winner is None:
                raise
            return winner

    def _existing_from_capture(
        self,
        decision_id: str,
        *,
        actor_role: ProcessingTransitionRole = (
            ProcessingTransitionRole.ACQUISITION_PROCESSOR
        ),
    ) -> SourceRevision | None:
        with Session(self._engine) as session:
            set_postgres_role(session, actor_role.value)
            existing = session.scalar(
                select(SourceRevisionRecord).where(
                    SourceRevisionRecord.decision_id == decision_id
                )
            )
            return _revision_from_record(existing) if existing is not None else None

    def materialize_reinterpretation(
        self,
        parent_revision_id: str,
        *,
        domain_content_hash: str,
        contract_version: str,
        parser_version: str,
        schema_version: str,
        configuration_version: str,
        actor_role: ProcessingTransitionRole = (
            ProcessingTransitionRole.ACQUISITION_PROCESSOR
        ),
    ) -> SourceRevision:
        """Reprocess a parent revision's verified Bronze evidence under a new
        interpretation, without a new SEC fetch (Ticket 18 bullet 4).

        Raw evidence hash, canonical-source hash, Bronze artifact reference,
        source-native revision, completeness type, and declared replacement
        scope are all inherited unchanged from the parent -- only
        interpretation changed, so only the domain-content hash and
        interpretation identities are supplied fresh. Idempotent per
        ``(parent_revision_id, contract_version, parser_version,
        schema_version, configuration_version)``.
        """

        require_processor_role(actor_role)
        existing = self._existing_reinterpretation(
            parent_revision_id,
            contract_version=contract_version,
            parser_version=parser_version,
            schema_version=schema_version,
            configuration_version=configuration_version,
            actor_role=actor_role,
        )
        if existing is not None:
            return existing
        try:
            with Session(self._engine) as session, session.begin():
                set_postgres_role(session, actor_role.value)
                parent = session.get(SourceRevisionRecord, parent_revision_id)
                if parent is None:
                    raise RevisionNotEligible(
                        f"parent_revision_id={parent_revision_id} does not exist"
                    )

                position = reserve_observation_position(
                    session, parent.source_family, parent.logical_source_key
                )
                previous = _latest_revision_before(
                    session, parent.source_family, parent.logical_source_key, position
                )
                content_impact = _content_impact(previous, domain_content_hash)

                record = SourceRevisionRecord(
                    decision_id=None,
                    parent_revision_id=parent_revision_id,
                    revision_relationship=RevisionRelationship.REINTERPRETATION.value,
                    source_family=parent.source_family,
                    logical_source_key=parent.logical_source_key,
                    observation_position=position,
                    source_native_revision=parent.source_native_revision,
                    raw_evidence_hash=parent.raw_evidence_hash,
                    canonical_source_hash=parent.canonical_source_hash,
                    domain_content_hash=domain_content_hash,
                    contract_version=contract_version,
                    parser_version=parser_version,
                    schema_version=schema_version,
                    configuration_version=configuration_version,
                    completeness_type=parent.completeness_type,
                    declared_replacement_scope=parent.declared_replacement_scope,
                    bronze_artifact_reference=parent.bronze_artifact_reference,
                    content_impact=content_impact.value,
                )
                session.add(record)
                session.flush()
                return _revision_from_record(record)
        except IntegrityError:
            winner = self._existing_reinterpretation(
                parent_revision_id,
                contract_version=contract_version,
                parser_version=parser_version,
                schema_version=schema_version,
                configuration_version=configuration_version,
                actor_role=actor_role,
            )
            if winner is None:
                raise
            return winner

    def _existing_reinterpretation(
        self,
        parent_revision_id: str,
        *,
        contract_version: str,
        parser_version: str,
        schema_version: str,
        configuration_version: str,
        actor_role: ProcessingTransitionRole = (
            ProcessingTransitionRole.ACQUISITION_PROCESSOR
        ),
    ) -> SourceRevision | None:
        with Session(self._engine) as session:
            set_postgres_role(session, actor_role.value)
            existing = session.scalar(
                select(SourceRevisionRecord).where(
                    SourceRevisionRecord.parent_revision_id == parent_revision_id,
                    SourceRevisionRecord.contract_version == contract_version,
                    SourceRevisionRecord.parser_version == parser_version,
                    SourceRevisionRecord.schema_version == schema_version,
                    SourceRevisionRecord.configuration_version == configuration_version,
                )
            )
            return _revision_from_record(existing) if existing is not None else None


def _content_impact(
    previous: SourceRevisionRecord | None, domain_content_hash: str
) -> ContentImpact:
    if previous is not None and previous.domain_content_hash == domain_content_hash:
        return ContentImpact.NO_IMPACT
    return ContentImpact.CHANGED


def _latest_revision_before(
    session: Session,
    source_family: str,
    logical_source_key: str,
    observation_position: int,
) -> SourceRevisionRecord | None:
    return session.scalar(
        select(SourceRevisionRecord)
        .where(
            SourceRevisionRecord.source_family == source_family,
            SourceRevisionRecord.logical_source_key == logical_source_key,
            SourceRevisionRecord.observation_position < observation_position,
        )
        .order_by(SourceRevisionRecord.observation_position.desc())
        .limit(1)
    )


def _revision_from_record(record: SourceRevisionRecord) -> SourceRevision:
    return SourceRevision(
        revision_id=record.revision_id,
        decision_id=record.decision_id,
        parent_revision_id=record.parent_revision_id,
        revision_relationship=(
            RevisionRelationship(record.revision_relationship)
            if record.revision_relationship is not None
            else None
        ),
        source_family=record.source_family,
        logical_source_key=record.logical_source_key,
        observation_position=record.observation_position,
        source_native_revision=record.source_native_revision,
        raw_evidence_hash=record.raw_evidence_hash,
        canonical_source_hash=record.canonical_source_hash,
        domain_content_hash=record.domain_content_hash,
        contract_version=record.contract_version,
        parser_version=record.parser_version,
        schema_version=record.schema_version,
        configuration_version=record.configuration_version,
        completeness_type=CompletenessType(record.completeness_type),
        declared_replacement_scope=record.declared_replacement_scope,
        bronze_artifact_reference=record.bronze_artifact_reference,
        content_impact=ContentImpact(record.content_impact),
    )
