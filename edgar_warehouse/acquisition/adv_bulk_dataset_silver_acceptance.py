"""Carry a captured ``adv_bulk_dataset`` candidate through to Silver (Ticket 24).

Reuses ``adv_bulk_ingest.parse_adv_bulk_archive``/``ingest_adv_bulk_archive``
and ``adv_firm_roster_ingest.parse_firm_roster_archive``/
``ingest_firm_roster_archive`` unmodified -- same posture as Ticket 23
reusing ``replace_company_tickers`` unmodified. In particular this does NOT
reimplement ``ingest_adv_bulk_archive``'s per-accession ``fund_index``
scoping: that function already carries the fix for a real production
incident (a global counter overflowed ``sec_adv_private_fund.fund_index``
SMALLINT on a >32767-fund month), and calling it unchanged is what preserves
that fix here.

Verification is parse-count-vs-write-count reconciliation, not a full
member-key read-back: ``ingest_adv_bulk_archive``/``ingest_firm_roster_archive``
report only counts, not the written key set, and re-deriving business keys
independently here would risk drifting from what the ingest functions
actually write (the same class of bug Ticket 23's Standards review caught
for the blank-ticker case, avoided here by not duplicating the parse-to-key
mapping at all). A parsed-count that doesn't match the merged-count is
exactly the failure mode this exists to catch (a merge silently dropping
rows) -- an exact key-set mismatch would also change the count, so this
still fails closed on the case that matters.
"""

from __future__ import annotations

from dataclasses import dataclass

from edgar_warehouse.acquisition.adv_bulk_dataset_discovery import AdvBulkDatasetDriveResult
from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchWorkState
from edgar_warehouse.acquisition.processing import (
    ExpectedProducerOutcome,
    ExpectedProducerSpec,
    ProcessingDecision,
    ProcessingLedger,
    SilverFinalizer,
)
from edgar_warehouse.acquisition.revisions import ContentImpact, SourceRevisionLedger
from edgar_warehouse.application.adv_bulk_ingest import ingest_adv_bulk_archive, parse_adv_bulk_archive
from edgar_warehouse.application.adv_firm_roster_ingest import (
    ingest_firm_roster_archive,
    parse_firm_roster_archive,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase

ADV_BULK_PRODUCER_NAMES = ("sec_adv_filing", "sec_adv_private_fund")
FIRM_ROSTER_PRODUCER_NAME = "sec_adv_firm_roster"

# Same honest bounded-first-slice stance as the sibling families' own
# *_INTERPRETATION_VERSION constants.
ADV_BULK_DATASET_INTERPRETATION_VERSION = "raw-passthrough-v1"


class CandidateNotCaptured(RuntimeError):
    """The referenced decision has not reached a CAPTURED Bronze evidence state."""


class UnsupportedRequiredProducers(RuntimeError):
    """A covered family declares a required_producers set this Strategy's
    write bodies cannot serve. Ticket 32 bullet 1's pattern -- this family's
    required set spans both source kinds' producers.
    """


def bronze_reference_to_raw_evidence_hash(bronze_relative_path: str) -> str:
    return bronze_relative_path.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class AdvBulkDatasetOutcome:
    source_kind: str
    dataset_period: str
    variant: str | None
    decision_id: str | None
    processing_decision: ProcessingDecision | None
    error: str | None

    @property
    def settled(self) -> bool:
        return (
            self.error is None
            and self.processing_decision is not None
            and self.processing_decision.silver_outcome.value != "PENDING"
        )


@dataclass(frozen=True)
class AdvBulkDatasetSilverAcceptanceResult:
    outcomes: tuple[AdvBulkDatasetOutcome, ...]

    @property
    def interval_complete(self) -> bool:
        return all(o.settled for o in self.outcomes)


def _read_bronze_bytes(bronze_root: StorageLocation, relative_path: str) -> bytes:
    from edgar_warehouse.infrastructure.object_storage import read_bytes

    return read_bytes(bronze_root.join(relative_path))


def _finalize_adv_bulk_archive(
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    revision,
    decision_id: str,
    content: bytes,
    *,
    dataset_period: str,
    source_sha256: str,
) -> ProcessingDecision:
    parsed = parse_adv_bulk_archive(content, dataset_period=dataset_period, source_sha256=source_sha256)
    scope_reference = (
        f"adv-bulk-archive/{dataset_period}/filings={len(parsed.filings)}/funds={len(parsed.funds)}"
    )
    decision = processing.seal_expected_producers(
        revision.revision_id,
        expected_producers=tuple(
            ExpectedProducerSpec(
                producer_name=name,
                target_table=name,
                scope_reference=scope_reference,
            )
            for name in ADV_BULK_PRODUCER_NAMES
        ),
    )
    pending = {
        p.producer_name for p in decision.expected_producers if p.outcome is ExpectedProducerOutcome.PENDING
    }
    if not pending:
        return decision

    counts = ingest_adv_bulk_archive(
        silver, content, dataset_period=dataset_period, source_sha256=source_sha256, sync_run_id=decision_id
    )
    checks = {"sec_adv_filing": ("filings", len(parsed.filings)), "sec_adv_private_fund": ("funds", len(parsed.funds))}
    for producer_name in ADV_BULK_PRODUCER_NAMES:
        if producer_name not in pending:
            continue
        count_key, expected_count = checks[producer_name]
        actual_count = counts[count_key]
        verified = actual_count == expected_count
        decision = finalizer.record_producer_outcome(
            decision.processing_decision_id,
            producer_name,
            outcome=ExpectedProducerOutcome.VERIFIED if verified else ExpectedProducerOutcome.FAILED,
            verified_reference=scope_reference if verified else None,
            failure_detail=(
                None
                if verified
                else (
                    f"{producer_name} merge count={actual_count} did not match parsed "
                    f"count={expected_count} for dataset_period={dataset_period!r}"
                )
            ),
        )
    return decision


def _finalize_firm_roster_archive(
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    revision,
    decision_id: str,
    content: bytes,
    *,
    dataset_period: str,
    source_sha256: str,
) -> ProcessingDecision:
    parsed = parse_firm_roster_archive(content, dataset_period=dataset_period, source_sha256=source_sha256)
    scope_reference = f"adv-firm-roster/{dataset_period}/rows={len(parsed.rows)}"
    decision = processing.seal_expected_producers(
        revision.revision_id,
        expected_producers=(
            ExpectedProducerSpec(
                producer_name=FIRM_ROSTER_PRODUCER_NAME,
                target_table=FIRM_ROSTER_PRODUCER_NAME,
                scope_reference=scope_reference,
            ),
        ),
    )
    pending = {
        p.producer_name for p in decision.expected_producers if p.outcome is ExpectedProducerOutcome.PENDING
    }
    if FIRM_ROSTER_PRODUCER_NAME not in pending:
        return decision

    counts = ingest_firm_roster_archive(
        silver, content, dataset_period=dataset_period, source_sha256=source_sha256, sync_run_id=decision_id
    )
    verified = counts["firm_roster"] == len(parsed.rows)
    return finalizer.record_producer_outcome(
        decision.processing_decision_id,
        FIRM_ROSTER_PRODUCER_NAME,
        outcome=ExpectedProducerOutcome.VERIFIED if verified else ExpectedProducerOutcome.FAILED,
        verified_reference=scope_reference if verified else None,
        failure_detail=(
            None
            if verified
            else (
                f"sec_adv_firm_roster merge count={counts['firm_roster']} did not match "
                f"parsed count={len(parsed.rows)} for dataset_period={dataset_period!r}"
            )
        ),
    )


def _finalize_adv_bulk_dataset_candidate(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    revisions: SourceRevisionLedger,
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    decision_id: str,
    *,
    source_kind: str,
    dataset_period: str,
) -> ProcessingDecision:
    status = ledger.source_change_status(decision_id)
    if status.fetch_state is not FetchWorkState.CAPTURED:
        raise CandidateNotCaptured(
            f"decision_id={decision_id} is not CAPTURED (fetch_state={status.fetch_state})"
        )
    assert status.captured_artifact_reference is not None
    raw_evidence_hash = bronze_reference_to_raw_evidence_hash(status.captured_artifact_reference)
    revision = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash=raw_evidence_hash,
        canonical_source_hash=raw_evidence_hash,
        domain_content_hash=raw_evidence_hash,
        contract_version=ADV_BULK_DATASET_INTERPRETATION_VERSION,
        parser_version=ADV_BULK_DATASET_INTERPRETATION_VERSION,
        schema_version=ADV_BULK_DATASET_INTERPRETATION_VERSION,
        configuration_version=ADV_BULK_DATASET_INTERPRETATION_VERSION,
        source_native_revision=f"adv-bulk-dataset/{source_kind}/{dataset_period}",
    )

    if revision.content_impact is ContentImpact.NO_IMPACT:
        return processing.seal_expected_producers(revision.revision_id)

    content = _read_bronze_bytes(bronze_root, status.captured_artifact_reference)
    if source_kind == "firm_roster":
        return _finalize_firm_roster_archive(
            processing, finalizer, silver, revision, decision_id, content,
            dataset_period=dataset_period, source_sha256=raw_evidence_hash,
        )
    return _finalize_adv_bulk_archive(
        processing, finalizer, silver, revision, decision_id, content,
        dataset_period=dataset_period, source_sha256=raw_evidence_hash,
    )


def drive_adv_bulk_dataset_silver_acceptance(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    revisions: SourceRevisionLedger,
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    result: AdvBulkDatasetDriveResult,
    *,
    required_producers: tuple[str, ...] = ADV_BULK_PRODUCER_NAMES + (FIRM_ROSTER_PRODUCER_NAME,),
) -> AdvBulkDatasetSilverAcceptanceResult:
    """Carry every CAPTURED candidate in an adv-bulk-dataset drive result to Silver."""

    if set(required_producers) != set(ADV_BULK_PRODUCER_NAMES) | {FIRM_ROSTER_PRODUCER_NAME}:
        raise UnsupportedRequiredProducers(
            f"required_producers={required_producers!r} for adv_bulk_dataset, but this "
            f"Strategy's Silver-write bodies only know how to produce "
            f"{set(ADV_BULK_PRODUCER_NAMES) | {FIRM_ROSTER_PRODUCER_NAME}!r}"
        )

    outcomes: list[AdvBulkDatasetOutcome] = []
    for candidate_outcome in result.outcomes:
        candidate = candidate_outcome.candidate
        if (
            candidate_outcome.fetch_state is not FetchWorkState.CAPTURED
            or candidate_outcome.decision_id is None
        ):
            continue
        try:
            decision = _finalize_adv_bulk_dataset_candidate(
                ledger, bronze_root, revisions, processing, finalizer, silver,
                candidate_outcome.decision_id,
                source_kind=candidate.source_kind,
                dataset_period=candidate.dataset_period,
            )
            outcomes.append(
                AdvBulkDatasetOutcome(
                    source_kind=candidate.source_kind,
                    dataset_period=candidate.dataset_period,
                    variant=candidate.variant,
                    decision_id=candidate_outcome.decision_id,
                    processing_decision=decision,
                    error=None,
                )
            )
        except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
            outcomes.append(
                AdvBulkDatasetOutcome(
                    source_kind=candidate.source_kind,
                    dataset_period=candidate.dataset_period,
                    variant=candidate.variant,
                    decision_id=candidate_outcome.decision_id,
                    processing_decision=None,
                    error=str(error),
                )
            )

    return AdvBulkDatasetSilverAcceptanceResult(outcomes=tuple(outcomes))
