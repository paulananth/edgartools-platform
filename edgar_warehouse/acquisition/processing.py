"""Seal expected Silver producers and record verified outcomes (Ticket 19).

Ticket 03's "Processing and Silver publication" section splits processing
into two owners: "processors claim work" (this module's ``ProcessingLedger``
-- seals what a revision requires, before any Silver write happens) and
"the Silver finalizer verifies and finalizes publications" (this module's
``SilverFinalizer`` -- the only role that may record a producer's verified
outcome, always backed by read-back verification against the authoritative
store, never a write call's success alone).

A revision's ``content_impact`` (Ticket 18) determines its Processing
Decision automatically: ``NO_IMPACT`` seals with zero expected producers and
is immediately ``silver_outcome='PUBLISHED'`` (bullet 1's "explicit no-impact
outcome" -- there is nothing to publish); ``CHANGED`` seals
``disposition='PROCESS_REQUIRED'`` with the caller-declared expected producer
set and starts ``silver_outcome='PENDING'`` until the Silver Finalizer
settles every producer.

Same-key ordering (bullet 4, "A Silver failure leaves prior Silver
authoritative and blocks only later revisions for the same logical key"):
sealing a revision requires the immediately preceding revision for the same
(source_family, logical_source_key) to have already reached
``silver_outcome='PUBLISHED'`` -- a revision that FAILED, or is still
PENDING, blocks every later revision for that key from sealing at all, while
unrelated keys are untouched. Enforced by a plain committed read of the
prior revision's Processing Decision row, not a row lock: ``silver_outcome``
only ever transitions *away* from ``PENDING`` once and never reverts (a
finalized ``PUBLISHED``/``FAILED`` outcome is permanent -- see
``SilverFinalizer.record_producer_outcome``), so a stale read can only ever
under-report readiness (block when the prior settled microseconds after the
read), never over-report it -- a transient, self-healing false block on
retry, not a correctness gap. (An earlier draft used ``SELECT ... FOR
UPDATE`` here; PostgreSQL requires UPDATE privilege for that, which the
processor role deliberately does not have on ``source_processing_decision``
-- confirmed live against real PostgreSQL, not just reasoned about.) The
real DB-enforced backstop against two concurrently PENDING processing
decisions for one key is ``uq_source_processing_decision_active_key``, a
partial unique index mirroring ``uq_source_fetch_work_active_key``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from edgar_warehouse.acquisition.ledger import (
    DecisionOwnerRole,
    ProcessingTransitionRole,
    require_processor_role,
    require_silver_finalizer_role,
    set_postgres_role,
)
from edgar_warehouse.acquisition.models import (
    SourceExpectedProducerRecord,
    SourceFetchDecisionRecord,
    SourceFetchWorkRecord,
    SourceProcessingDecisionRecord,
    SourceRevisionRecord,
)


class ProcessingDisposition(StrEnum):
    """Ticket 03's full Processing Decision disposition set.

    All seven values are real schema (the ``ck_source_processing_decision_
    disposition`` CHECK constraint accepts all of them) so a later ticket
    can seal one without a migration. ``ProcessingLedger.seal_expected_
    producers`` in *this* ticket only ever produces ``PROCESS_REQUIRED`` or
    ``NO_IMPACT`` -- derived automatically from a revision's own
    ``content_impact`` (Ticket 18). The other five are operator/repair-path
    dispositions (``OUT_OF_SCOPE``, ``OPERATOR_EXCLUDED``, ``SUPERSEDED``,
    ``QUARANTINED``, ``RETRYABLE_FAILURE``) that belong to Ticket 25's
    "conflict, repair, exclusion, and evidence-import workflows" and Ticket
    26's epoch rebuild -- deliberately out of this ticket's bounded
    first-slice scope, not an oversight.
    """

    PROCESS_REQUIRED = "PROCESS_REQUIRED"
    NO_IMPACT = "NO_IMPACT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    OPERATOR_EXCLUDED = "OPERATOR_EXCLUDED"
    SUPERSEDED = "SUPERSEDED"
    QUARANTINED = "QUARANTINED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"


class SilverOutcome(StrEnum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class ExpectedProducerOutcome(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    NO_IMPACT = "NO_IMPACT"
    FAILED = "FAILED"


_TERMINAL_PRODUCER_OUTCOMES = frozenset(
    {
        ExpectedProducerOutcome.VERIFIED,
        ExpectedProducerOutcome.NO_IMPACT,
        ExpectedProducerOutcome.FAILED,
    }
)


class RevisionNotFound(RuntimeError):
    """The referenced revision does not exist."""


class PriorRevisionNotSettled(RuntimeError):
    """An earlier revision for this same logical key has not been published.

    Ticket 19 bullet 4: a Silver failure (or an unsettled prior revision)
    blocks only later revisions for the *same* logical key -- unrelated keys
    are never affected.
    """


class ExpectedProducerNotFound(RuntimeError):
    """No sealed expected-producer row matches the requested name."""


class ExpectedProducerAlreadySettled(RuntimeError):
    """A producer outcome was already recorded with a conflicting result."""


SNOWFLAKE_LANDING_PRODUCER_KIND = "snowflake_landing"
DUCKDB_PRODUCER_KIND = "duckdb"


@dataclass(frozen=True)
class ExpectedProducerSpec:
    """One Silver producer/table/scope a processor declares at seal time."""

    producer_name: str
    target_table: str
    scope_reference: str
    producer_kind: str = DUCKDB_PRODUCER_KIND
    expected_row_count: int | None = None
    cause_reference: str | None = None


@dataclass(frozen=True)
class ExpectedProducerStatus:
    expected_producer_id: str
    producer_name: str
    target_table: str
    scope_reference: str
    outcome: ExpectedProducerOutcome
    verified_reference: str | None
    failure_detail: str | None


@dataclass(frozen=True)
class ProcessingDecision:
    processing_decision_id: str
    revision_id: str
    source_family: str
    logical_source_key: str
    observation_position: int
    disposition: ProcessingDisposition
    silver_outcome: SilverOutcome
    expected_producers: tuple[ExpectedProducerStatus, ...] = field(default_factory=tuple)


class ProcessingLedger:
    """Transaction boundary for sealing Processing Decisions (processor role)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def seal_expected_producers(
        self,
        revision_id: str,
        *,
        expected_producers: tuple[ExpectedProducerSpec, ...] = (),
        actor_role: ProcessingTransitionRole = (
            ProcessingTransitionRole.ACQUISITION_PROCESSOR
        ),
    ) -> ProcessingDecision:
        """Seal a revision's Processing Decision and expected producer set.

        Idempotent per ``revision_id``. A ``NO_IMPACT`` revision (per its
        already-materialized ``content_impact``) must be sealed with an empty
        ``expected_producers`` -- there is nothing to publish. A ``CHANGED``
        revision must be sealed with at least one; raises ``ValueError`` if
        neither invariant holds so a caller mistake surfaces immediately
        rather than silently sealing a decision nothing will ever settle.
        """

        require_processor_role(actor_role)
        existing = self.read_for_revision(revision_id, actor_role=actor_role)
        if existing is not None:
            return existing
        try:
            with Session(self._engine) as session, session.begin():
                set_postgres_role(session, actor_role.value)
                revision = session.get(SourceRevisionRecord, revision_id)
                if revision is None:
                    raise RevisionNotFound(f"revision_id={revision_id} does not exist")

                changed = revision.content_impact == "CHANGED"
                if changed and not expected_producers:
                    raise ValueError(
                        f"revision_id={revision_id} has content_impact=CHANGED "
                        "and requires at least one expected producer"
                    )
                if not changed and expected_producers:
                    raise ValueError(
                        f"revision_id={revision_id} has content_impact=NO_IMPACT "
                        "and must not declare expected producers"
                    )

                self._require_prior_revision_published(session, revision)

                now = datetime.now(UTC)
                disposition = (
                    ProcessingDisposition.PROCESS_REQUIRED
                    if changed
                    else ProcessingDisposition.NO_IMPACT
                )
                silver_outcome = (
                    SilverOutcome.PENDING if changed else SilverOutcome.PUBLISHED
                )
                record = SourceProcessingDecisionRecord(
                    revision_id=revision_id,
                    source_family=revision.source_family,
                    logical_source_key=revision.logical_source_key,
                    observation_position=revision.observation_position,
                    disposition=disposition.value,
                    silver_outcome=silver_outcome.value,
                    settled_at=None if changed else now,
                )
                session.add(record)
                session.flush()
                producer_records = [
                    SourceExpectedProducerRecord(
                        processing_decision_id=record.processing_decision_id,
                        producer_name=spec.producer_name,
                        target_table=spec.target_table,
                        scope_reference=spec.scope_reference,
                        outcome=ExpectedProducerOutcome.PENDING.value,
                    )
                    for spec in expected_producers
                ]
                for producer_record in producer_records:
                    session.add(producer_record)
                session.flush()
                return _decision_from_records(record, producer_records)
        except IntegrityError:
            winner = self.read_for_revision(revision_id, actor_role=actor_role)
            if winner is None:
                raise
            return winner

    def _require_prior_revision_published(
        self, session: Session, revision: SourceRevisionRecord
    ) -> None:
        previous = session.scalar(
            select(SourceRevisionRecord)
            .where(
                SourceRevisionRecord.source_family == revision.source_family,
                SourceRevisionRecord.logical_source_key == revision.logical_source_key,
                SourceRevisionRecord.observation_position
                < revision.observation_position,
            )
            .order_by(SourceRevisionRecord.observation_position.desc())
            .limit(1)
        )
        if previous is None:
            return
        previous_decision = session.scalar(
            select(SourceProcessingDecisionRecord).where(
                SourceProcessingDecisionRecord.revision_id == previous.revision_id
            )
        )
        if (
            previous_decision is None
            or previous_decision.silver_outcome != SilverOutcome.PUBLISHED.value
        ):
            raise PriorRevisionNotSettled(
                f"revision_id={previous.revision_id} (observation_position="
                f"{previous.observation_position}) for "
                f"{revision.source_family}/{revision.logical_source_key} has not "
                "reached silver_outcome=PUBLISHED; later revisions for this key "
                "cannot seal until it does"
            )

    def read_for_revision(
        self,
        revision_id: str,
        *,
        actor_role: ProcessingTransitionRole = (
            ProcessingTransitionRole.ACQUISITION_PROCESSOR
        ),
    ) -> ProcessingDecision | None:
        """Read the sealed Processing Decision for a revision, or ``None``
        if it has not been sealed yet. Public read accessor -- also the
        idempotency check ``seal_expected_producers`` reuses internally, so
        a caller inspecting state (an operator tool, a test) does not need
        to reach past this class's interface.
        """

        with Session(self._engine) as session:
            set_postgres_role(session, actor_role.value)
            record = session.scalar(
                select(SourceProcessingDecisionRecord).where(
                    SourceProcessingDecisionRecord.revision_id == revision_id
                )
            )
            if record is None:
                return None
            producer_records = list(
                session.scalars(
                    select(SourceExpectedProducerRecord).where(
                        SourceExpectedProducerRecord.processing_decision_id
                        == record.processing_decision_id
                    )
                )
            )
            return _decision_from_records(record, producer_records)


class SilverFinalizer:
    """Transaction boundary for recording verified producer outcomes (finalizer role)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record_producer_outcome(
        self,
        processing_decision_id: str,
        producer_name: str,
        *,
        outcome: ExpectedProducerOutcome,
        verified_reference: str | None = None,
        failure_detail: str | None = None,
        actor_role: ProcessingTransitionRole = (
            ProcessingTransitionRole.ACQUISITION_SILVER_FINALIZER
        ),
    ) -> ProcessingDecision:
        """Record one expected producer's settled outcome.

        Idempotent when replayed with the identical outcome/reference; raises
        ``ExpectedProducerAlreadySettled`` if a replay disagrees with the
        already-recorded terminal outcome (a real conflict, not a retry).
        """

        require_silver_finalizer_role(actor_role)
        if outcome not in _TERMINAL_PRODUCER_OUTCOMES:
            raise ValueError(f"outcome must be a terminal outcome, got {outcome}")
        if outcome is ExpectedProducerOutcome.VERIFIED and not (
            verified_reference or ""
        ).strip():
            raise ValueError("verified_reference is required when outcome is VERIFIED")
        if outcome is ExpectedProducerOutcome.FAILED and not (
            failure_detail or ""
        ).strip():
            raise ValueError("failure_detail is required when outcome is FAILED")

        with Session(self._engine) as session, session.begin():
            set_postgres_role(session, actor_role.value)
            producer = session.scalar(
                select(SourceExpectedProducerRecord).where(
                    SourceExpectedProducerRecord.processing_decision_id
                    == processing_decision_id,
                    SourceExpectedProducerRecord.producer_name == producer_name,
                )
            )
            if producer is None:
                raise ExpectedProducerNotFound(
                    f"no sealed expected producer {producer_name!r} for "
                    f"processing_decision_id={processing_decision_id}"
                )
            if producer.outcome != ExpectedProducerOutcome.PENDING.value:
                if (
                    producer.outcome == outcome.value
                    and producer.verified_reference == verified_reference
                    and producer.failure_detail == failure_detail
                ):
                    return self._read_decision(session, processing_decision_id)
                raise ExpectedProducerAlreadySettled(
                    f"expected producer {producer_name!r} for "
                    f"processing_decision_id={processing_decision_id} already "
                    f"settled as {producer.outcome!r}, cannot re-settle as "
                    f"{outcome.value!r}"
                )

            now = datetime.now(UTC)
            producer.outcome = outcome.value
            producer.verified_reference = verified_reference
            producer.failure_detail = failure_detail
            producer.updated_at = now
            session.flush()

            decision_query = select(SourceProcessingDecisionRecord).where(
                SourceProcessingDecisionRecord.processing_decision_id
                == processing_decision_id
            )
            if session.get_bind().dialect.name == "postgresql":
                decision_query = decision_query.with_for_update()
            decision = session.scalar(decision_query)
            if decision is None:
                raise ExpectedProducerNotFound(
                    f"no Processing Decision processing_decision_id="
                    f"{processing_decision_id}"
                )
            if decision.silver_outcome == SilverOutcome.PENDING.value:
                if outcome is ExpectedProducerOutcome.FAILED:
                    decision.silver_outcome = SilverOutcome.FAILED.value
                    decision.settled_at = now
                else:
                    remaining_pending = session.scalar(
                        select(func.count())
                        .select_from(SourceExpectedProducerRecord)
                        .where(
                            SourceExpectedProducerRecord.processing_decision_id
                            == processing_decision_id,
                            SourceExpectedProducerRecord.outcome
                            == ExpectedProducerOutcome.PENDING.value,
                        )
                    )
                    if remaining_pending == 0:
                        decision.silver_outcome = SilverOutcome.PUBLISHED.value
                        decision.settled_at = now
                session.flush()
            return self._read_decision(session, processing_decision_id)

    def _read_decision(
        self, session: Session, processing_decision_id: str
    ) -> ProcessingDecision:
        record = session.get(SourceProcessingDecisionRecord, processing_decision_id)
        assert record is not None  # caller already confirmed it exists
        producer_records = list(
            session.scalars(
                select(SourceExpectedProducerRecord).where(
                    SourceExpectedProducerRecord.processing_decision_id
                    == processing_decision_id
                )
            )
        )
        return _decision_from_records(record, producer_records)


def verify_snowflake_landing_producer(
    finalizer: SilverFinalizer,
    processing_decision_id: str,
    producer_name: str,
    *,
    target_table: str,
    cause_reference: str,
    expected_row_count: int,
    count_rows: Callable[[str, str], int],
) -> ProcessingDecision:
    """Ticket 35: settle a snowflake-landing producer from a real COUNT(*).

    ``count_rows(target_table, cause_reference)`` is the read-back against
    the authoritative landing table (or a test double of that table). This
    function does not open Snowflake itself -- callers inject the counter so
    production can COUNT EDGARTOOLS_SILVER_LANDING and tests can COUNT a
    local stand-in. Layered on top of dbt's ``target_lag = '6 hours'``:
    missing rows fail closed here regardless of the dynamic-table refresh
    clock.
    """

    actual = count_rows(target_table, cause_reference)
    if actual == expected_row_count:
        return finalizer.record_producer_outcome(
            processing_decision_id,
            producer_name,
            outcome=ExpectedProducerOutcome.VERIFIED,
            verified_reference=(
                f"snowflake_landing:{target_table}:{cause_reference}:count={actual}"
            ),
        )
    return finalizer.record_producer_outcome(
        processing_decision_id,
        producer_name,
        outcome=ExpectedProducerOutcome.FAILED,
        failure_detail=(
            f"expected {expected_row_count} landing rows in {target_table} "
            f"for cause_reference={cause_reference!r}; counted {actual}"
        ),
    )


@dataclass(frozen=True)
class SourceChangeStatusDetail:
    """Ticket 19 bullet 3: joins decision, capture, revision, processing,
    expected-producer progress, blocker, and next action for one candidate.

    Deliberately a separate read model from ``ledger.SourceChangeStatus`` --
    that dataclass's shape and every existing caller (discovery.py, the
    Facade, ``execute_source_request``) are untouched. This is the wider
    projection Ticket 03 describes for operator/status use, composed on
    demand rather than replacing the narrower one the fetch/capture path
    actually needs to operate.
    """

    decision_id: str
    source_family: str
    logical_source_key: str
    fetch_disposition: str
    fetch_state: str | None
    revision_id: str | None
    content_impact: str | None
    processing_disposition: str | None
    silver_outcome: str | None
    expected_producer_total: int
    expected_producer_settled: int
    blocker: str | None
    next_action: str

    @property
    def is_fully_published(self) -> bool:
        return self.silver_outcome == SilverOutcome.PUBLISHED.value


def read_source_change_status_detail(
    engine: Engine, decision_id: str
) -> SourceChangeStatusDetail:
    with Session(engine) as session:
        # Read-only, but Postgres role-gated tables still require SET LOCAL
        # ROLE under INHERIT FALSE -- mirrors ledger.py's own read-only
        # helpers (source_change_status, latest_transition_reason), which
        # both call this for the same reason. The coordinator role has
        # SELECT on every table this projection joins.
        set_postgres_role(session, DecisionOwnerRole.ACQUISITION_COORDINATOR.value)
        decision = session.get(SourceFetchDecisionRecord, decision_id)
        if decision is None:
            raise KeyError(f"No Source Fetch Decision with decision_id={decision_id}")
        work = session.get(SourceFetchWorkRecord, decision_id)
        revision = session.scalar(
            select(SourceRevisionRecord).where(
                SourceRevisionRecord.decision_id == decision_id
            )
        )
        processing: SourceProcessingDecisionRecord | None = None
        producer_total = 0
        producer_settled = 0
        # Mirrors source_change_status_detail's SQL view CASE exactly (same
        # fetch_state -> next_action mapping, same fallback to
        # decision.next_action) -- a prior version of this function only had
        # the CAPTURED branch, silently diverging from the view for
        # LEASED/FAILED (the same sibling-divergence shape this repo's
        # CLAUDE.md repeatedly flags); fixed and locked in by
        # test_source_change_status_detail_reflects_leased_and_failed_fetch_states.
        next_action = decision.next_action
        if work is not None:
            if work.fetch_state == "LEASED":
                next_action = "FETCH_SOURCE"
            elif work.fetch_state == "CAPTURED":
                next_action = "MATERIALIZE_SOURCE_REVISION"
            elif work.fetch_state == "FAILED":
                next_action = "RETRY_FETCH"
        if revision is not None:
            processing = session.scalar(
                select(SourceProcessingDecisionRecord).where(
                    SourceProcessingDecisionRecord.revision_id == revision.revision_id
                )
            )
            if processing is None:
                next_action = "SEAL_EXPECTED_PRODUCERS"
            elif processing.silver_outcome == SilverOutcome.PENDING.value:
                next_action = "FINALIZE_SILVER_PUBLICATION"
                producer_total = session.scalar(
                    select(func.count())
                    .select_from(SourceExpectedProducerRecord)
                    .where(
                        SourceExpectedProducerRecord.processing_decision_id
                        == processing.processing_decision_id
                    )
                )
                producer_settled = session.scalar(
                    select(func.count())
                    .select_from(SourceExpectedProducerRecord)
                    .where(
                        SourceExpectedProducerRecord.processing_decision_id
                        == processing.processing_decision_id,
                        SourceExpectedProducerRecord.outcome
                        != ExpectedProducerOutcome.PENDING.value,
                    )
                )
            elif processing.silver_outcome == SilverOutcome.PUBLISHED.value:
                next_action = "NONE"
            elif processing.silver_outcome == SilverOutcome.FAILED.value:
                next_action = "REPAIR_SILVER_FAILURE"
        return SourceChangeStatusDetail(
            decision_id=decision.decision_id,
            source_family=decision.source_family,
            logical_source_key=decision.logical_source_key,
            fetch_disposition=decision.fetch_disposition,
            fetch_state=work.fetch_state if work is not None else None,
            revision_id=revision.revision_id if revision is not None else None,
            content_impact=revision.content_impact if revision is not None else None,
            processing_disposition=(
                processing.disposition if processing is not None else None
            ),
            silver_outcome=(
                processing.silver_outcome if processing is not None else None
            ),
            expected_producer_total=int(producer_total or 0),
            expected_producer_settled=int(producer_settled or 0),
            blocker=decision.blocker,
            next_action=next_action,
        )


def _decision_from_records(
    record: SourceProcessingDecisionRecord,
    producer_records: list[SourceExpectedProducerRecord],
) -> ProcessingDecision:
    return ProcessingDecision(
        processing_decision_id=record.processing_decision_id,
        revision_id=record.revision_id,
        source_family=record.source_family,
        logical_source_key=record.logical_source_key,
        observation_position=record.observation_position,
        disposition=ProcessingDisposition(record.disposition),
        silver_outcome=SilverOutcome(record.silver_outcome),
        expected_producers=tuple(
            ExpectedProducerStatus(
                expected_producer_id=p.expected_producer_id,
                producer_name=p.producer_name,
                target_table=p.target_table,
                scope_reference=p.scope_reference,
                outcome=ExpectedProducerOutcome(p.outcome),
                verified_reference=p.verified_reference,
                failure_detail=p.failure_detail,
            )
            for p in producer_records
        ),
    )
