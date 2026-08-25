"""Carry a captured ``submissions`` candidate through to Silver (Ticket 21).

Family-specific wiring for the generic mechanism in ``processing.py``,
mirroring ``silver_acceptance.py``'s ``filing_artifact`` shape but with a
genuinely different completeness gate: a main snapshot's revision may only
be sealed with expected producers once every pagination file it declared has
independently reached a VERIFIED producer outcome (Ticket 21 bullet 2) --
``submissions_discovery.SubmissionsCandidateOutcome.settled`` already proves
this at the drive layer; this module trusts that proof rather than
re-deriving it, and simply declines to seal a main revision whose drive
outcome isn't ``pagination_complete``.

Two Silver scopes settle independently, matching ``submissions_discovery``'s
two logical-key kinds:

- Pagination revisions each seal one producer, ``sec_company_filing``
  (scoped to that one file's own accession rows) -- writes and read-back
  verifies its own filing rows only, via ``silver_store.merge_filings``.
- Main revisions seal two producers, ``sec_company`` (company/address/
  former-name/manifest, one combined write via ``silver_store.
  stage_submission`` with an empty ``pagination_payloads`` list -- confirmed
  via ``_stage_submission_locked`` that this still runs every main-derived
  loader and both scope-retire deletes) and ``sec_company_filing`` (this
  CIK's "recent" filing rows only -- the pagination rows are each already
  owned by their own pagination revision's producer, so main's own
  ``sec_company_filing`` producer is scoped to ``recent`` only, not the
  combined set, to avoid two different revisions both claiming to have
  produced the same table without a real ownership split).

Deliberately does not touch ``silver_store.py``'s existing loaders/merge
methods -- reuses them exactly as the legacy path does, since Ticket 21's
job is carrying already-correct Silver-write logic through the new
registered path, not reimplementing it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    FetchWorkState,
    SourceChangeStatus,
)
from edgar_warehouse.acquisition.processing import (
    ExpectedProducerOutcome,
    ExpectedProducerSpec,
    ProcessingDecision,
    ProcessingLedger,
    SilverFinalizer,
)
from edgar_warehouse.acquisition.revisions import (
    ContentImpact,
    SourceRevision,
    SourceRevisionLedger,
)
from edgar_warehouse.acquisition.submissions_discovery import SubmissionsDriveResult
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase

SUBMISSIONS_COMPANY_PRODUCER_NAME = "sec_company"
SUBMISSIONS_COMPANY_TARGET_TABLE = "sec_company"
SUBMISSIONS_FILING_PRODUCER_NAME = "sec_company_filing"
SUBMISSIONS_FILING_TARGET_TABLE = "sec_company_filing"

# Same honest bounded-first-slice stance as filing_artifact's
# FILING_ARTIFACT_INTERPRETATION_VERSION: no real interpretation-vs-transport
# distinction exists yet for this family, so all four hashes/identities
# collapse to the raw evidence hash. A later parsing-quality ticket must not
# inherit this as an assumption once real interpretation exists.
SUBMISSIONS_INTERPRETATION_VERSION = "raw-passthrough-v1"


class CandidateNotCaptured(RuntimeError):
    """The referenced decision has not reached a CAPTURED Bronze evidence state."""


class UnsupportedRequiredProducers(RuntimeError):
    """A covered family declares a required_producers set this Strategy's
    write bodies cannot serve.

    Ticket 32 bullet 1's pattern, ported from ``silver_acceptance.py``: the
    write bodies here (``_finalize_main_candidate``,
    ``_finalize_pagination_candidate``) are hardcoded to write exactly the
    producers named by ``SUBMISSIONS_COMPANY_PRODUCER_NAME``/
    ``SUBMISSIONS_FILING_PRODUCER_NAME`` -- no generic per-producer
    dispatch, since there is no second producer set to justify one
    (Speculative Generality). Validating the registry's declared set
    against that exact known pair, rather than iterating it generically,
    keeps that honest -- mirrors ``silver_acceptance.
    UnsupportedRequiredProducers`` exactly, just for this family's own
    two-producer set instead of filing_artifact's one.
    """


def bronze_reference_to_raw_evidence_hash(bronze_relative_path: str) -> str:
    """Mirrors ``silver_acceptance.bronze_reference_to_raw_evidence_hash``
    exactly -- same Bronze naming convention (``source_family/hash``).
    """

    return bronze_relative_path.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class SubmissionsMainOutcome:
    cik: int
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
class SubmissionsPaginationOutcome:
    cik: int
    file_name: str
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
class SubmissionsSilverAcceptanceResult:
    main_outcomes: tuple[SubmissionsMainOutcome, ...]
    pagination_outcomes: tuple[SubmissionsPaginationOutcome, ...]

    @property
    def interval_complete(self) -> bool:
        return all(o.settled for o in self.main_outcomes) and all(
            o.settled for o in self.pagination_outcomes
        )


@dataclass(frozen=True)
class _CapturedCandidate:
    """A CAPTURED decision's status plus its materialized revision -- the
    shared shape both ``_finalize_pagination_candidate`` and
    ``_finalize_main_candidate`` need before they diverge into their own
    producer sets and write bodies.
    """

    status: SourceChangeStatus
    revision: SourceRevision


def _materialize_captured_candidate(
    ledger: AcquisitionLedger,
    revisions: SourceRevisionLedger,
    decision_id: str,
    *,
    source_native_revision: str,
) -> _CapturedCandidate:
    """Read a CAPTURED decision's status and materialize its revision.

    Shared by both finalize functions below (Standards review, this
    ticket): the status-check -> raise-if-not-CAPTURED ->
    bronze_reference_to_raw_evidence_hash -> materialize_from_capture
    sequence was identical in both, differing only in
    ``source_native_revision``.
    """

    status = ledger.source_change_status(decision_id)
    if status.fetch_state is not FetchWorkState.CAPTURED:
        raise CandidateNotCaptured(
            f"decision_id={decision_id} is not CAPTURED (fetch_state={status.fetch_state})"
        )
    assert status.captured_artifact_reference is not None
    raw_evidence_hash = bronze_reference_to_raw_evidence_hash(
        status.captured_artifact_reference
    )
    revision = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash=raw_evidence_hash,
        canonical_source_hash=raw_evidence_hash,
        domain_content_hash=raw_evidence_hash,
        contract_version=SUBMISSIONS_INTERPRETATION_VERSION,
        parser_version=SUBMISSIONS_INTERPRETATION_VERSION,
        schema_version=SUBMISSIONS_INTERPRETATION_VERSION,
        configuration_version=SUBMISSIONS_INTERPRETATION_VERSION,
        source_native_revision=source_native_revision,
    )
    return _CapturedCandidate(status=status, revision=revision)


def _finalize_pagination_candidate(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    revisions: SourceRevisionLedger,
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    decision_id: str,
    *,
    cik: int,
    file_name: str,
) -> ProcessingDecision:
    captured = _materialize_captured_candidate(
        ledger, revisions, decision_id, source_native_revision=file_name
    )
    status, revision = captured.status, captured.revision

    if revision.content_impact is ContentImpact.NO_IMPACT:
        return processing.seal_expected_producers(revision.revision_id)

    decision = processing.seal_expected_producers(
        revision.revision_id,
        expected_producers=(
            ExpectedProducerSpec(
                producer_name=SUBMISSIONS_FILING_PRODUCER_NAME,
                target_table=SUBMISSIONS_FILING_TARGET_TABLE,
                scope_reference=f"{cik}/pagination/{file_name}",
            ),
        ),
    )
    already_settled = next(
        (
            p
            for p in decision.expected_producers
            if p.producer_name == SUBMISSIONS_FILING_PRODUCER_NAME
            and p.outcome is not ExpectedProducerOutcome.PENDING
        ),
        None,
    )
    if already_settled is not None:
        return decision

    from edgar_warehouse.loaders.bronze_submission_extractors import (
        stage_pagination_filing_loader,
    )

    assert status.captured_artifact_reference is not None
    pagination_bytes = _read_bronze_bytes(bronze_root, status.captured_artifact_reference)
    try:
        pagination_payload = json.loads(pagination_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return finalizer.record_producer_outcome(
            decision.processing_decision_id,
            SUBMISSIONS_FILING_PRODUCER_NAME,
            outcome=ExpectedProducerOutcome.FAILED,
            failure_detail=f"pagination payload for {file_name!r} is not valid JSON: {error}",
        )

    rows = stage_pagination_filing_loader(
        pagination_payload,
        cik,
        decision_id,
        revision.raw_evidence_hash,
        "drive-submissions-discovery",
    )
    silver.merge_filings(rows, decision_id)
    written_accessions = {row["accession_number"] for row in rows if row.get("accession_number")}
    verified = all(silver.get_filing(acc) is not None for acc in written_accessions)
    if verified:
        return finalizer.record_producer_outcome(
            decision.processing_decision_id,
            SUBMISSIONS_FILING_PRODUCER_NAME,
            outcome=ExpectedProducerOutcome.VERIFIED,
            verified_reference=f"{cik}/pagination/{file_name}",
        )
    return finalizer.record_producer_outcome(
        decision.processing_decision_id,
        SUBMISSIONS_FILING_PRODUCER_NAME,
        outcome=ExpectedProducerOutcome.FAILED,
        failure_detail=(
            f"sec_company_filing read-back for cik={cik} file_name={file_name!r} "
            "did not find all written accessions"
        ),
    )


def _finalize_main_candidate(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    revisions: SourceRevisionLedger,
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    decision_id: str,
    *,
    cik: int,
) -> ProcessingDecision:
    captured = _materialize_captured_candidate(
        ledger, revisions, decision_id, source_native_revision=f"{cik}/main"
    )
    status, revision = captured.status, captured.revision

    if revision.content_impact is ContentImpact.NO_IMPACT:
        return processing.seal_expected_producers(revision.revision_id)

    decision = processing.seal_expected_producers(
        revision.revision_id,
        expected_producers=(
            ExpectedProducerSpec(
                producer_name=SUBMISSIONS_COMPANY_PRODUCER_NAME,
                target_table=SUBMISSIONS_COMPANY_TARGET_TABLE,
                scope_reference=f"{cik}/main",
            ),
            ExpectedProducerSpec(
                producer_name=SUBMISSIONS_FILING_PRODUCER_NAME,
                target_table=SUBMISSIONS_FILING_TARGET_TABLE,
                scope_reference=f"{cik}/main/recent",
            ),
        ),
    )
    pending_producer_names = {
        p.producer_name
        for p in decision.expected_producers
        if p.outcome is ExpectedProducerOutcome.PENDING
    }
    if not pending_producer_names:
        return decision

    assert status.captured_artifact_reference is not None
    main_bytes = _read_bronze_bytes(bronze_root, status.captured_artifact_reference)
    try:
        main_payload = json.loads(main_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        for producer_name in pending_producer_names:
            decision = finalizer.record_producer_outcome(
                decision.processing_decision_id,
                producer_name,
                outcome=ExpectedProducerOutcome.FAILED,
                failure_detail=f"main payload for cik={cik} is not valid JSON: {error}",
            )
        return decision

    staged = silver.stage_submission(
        cik=cik,
        main_payload=main_payload,
        pagination_payloads=[],
        sync_run_id=decision_id,
        raw_object_id=revision.raw_evidence_hash,
        load_mode="drive-submissions-discovery",
    )

    if SUBMISSIONS_COMPANY_PRODUCER_NAME in pending_producer_names:
        company_row = silver.get_company(cik)
        outcome = (
            ExpectedProducerOutcome.VERIFIED
            if company_row is not None
            else ExpectedProducerOutcome.FAILED
        )
        decision = finalizer.record_producer_outcome(
            decision.processing_decision_id,
            SUBMISSIONS_COMPANY_PRODUCER_NAME,
            outcome=outcome,
            verified_reference=f"{cik}/main" if outcome is ExpectedProducerOutcome.VERIFIED else None,
            failure_detail=(
                None
                if outcome is ExpectedProducerOutcome.VERIFIED
                else f"sec_company read-back for cik={cik} found no row after stage_submission"
            ),
        )

    if SUBMISSIONS_FILING_PRODUCER_NAME in pending_producer_names:
        recent_accessions = set(staged["recent_accessions"])
        verified = all(silver.get_filing(acc) is not None for acc in recent_accessions)
        decision = finalizer.record_producer_outcome(
            decision.processing_decision_id,
            SUBMISSIONS_FILING_PRODUCER_NAME,
            outcome=(
                ExpectedProducerOutcome.VERIFIED
                if verified
                else ExpectedProducerOutcome.FAILED
            ),
            verified_reference=f"{cik}/main/recent" if verified else None,
            failure_detail=(
                None
                if verified
                else f"sec_company_filing read-back for cik={cik} recent rows did not find all written accessions"
            ),
        )

    return decision


def _read_bronze_bytes(bronze_root: StorageLocation, relative_path: str) -> bytes:
    from edgar_warehouse.infrastructure.object_storage import read_bytes

    return read_bytes(bronze_root.join(relative_path))


def drive_submissions_silver_acceptance(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    revisions: SourceRevisionLedger,
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    result: SubmissionsDriveResult,
    *,
    required_producers: tuple[str, ...] = (
        SUBMISSIONS_COMPANY_PRODUCER_NAME,
        SUBMISSIONS_FILING_PRODUCER_NAME,
    ),
) -> SubmissionsSilverAcceptanceResult:
    """Carry every CAPTURED candidate in a submissions drive result to Silver.

    Mirrors ``silver_acceptance.drive_filing_artifact_silver_acceptance``'s
    per-candidate fault isolation exactly, but only calls a main candidate's
    own finalize step once its drive outcome already proves
    ``pagination_complete`` -- an incomplete main candidate is skipped here
    entirely (not attempted-and-failed), leaving it unsettled for the next
    replay to retry, once its pagination files have actually settled.

    ``required_producers`` (Ticket 32 bullet 1, normally the active registry
    coverage's declared set for ``submissions``) is validated once, upfront,
    against the exact two producers this module's write bodies can serve --
    a misconfigured registry is the same error for every candidate in this
    interval, so failing fast here beats silently recording it N times as N
    identical per-candidate outcomes (mirrors ``silver_acceptance.
    drive_filing_artifact_silver_acceptance``'s own upfront check exactly).
    """

    if set(required_producers) != {
        SUBMISSIONS_COMPANY_PRODUCER_NAME,
        SUBMISSIONS_FILING_PRODUCER_NAME,
    }:
        raise UnsupportedRequiredProducers(
            f"required_producers={required_producers!r} for submissions, but "
            f"this Strategy's Silver-write bodies only know how to produce "
            f"{{{SUBMISSIONS_COMPANY_PRODUCER_NAME!r}, {SUBMISSIONS_FILING_PRODUCER_NAME!r}}}"
        )

    main_outcomes: list[SubmissionsMainOutcome] = []
    pagination_outcomes: list[SubmissionsPaginationOutcome] = []

    for candidate_outcome in result.outcomes:
        cik = candidate_outcome.candidate.cik

        for pagination_outcome in candidate_outcome.pagination_outcomes:
            if (
                pagination_outcome.fetch_state is not FetchWorkState.CAPTURED
                or pagination_outcome.decision_id is None
            ):
                continue
            try:
                decision = _finalize_pagination_candidate(
                    ledger,
                    bronze_root,
                    revisions,
                    processing,
                    finalizer,
                    silver,
                    pagination_outcome.decision_id,
                    cik=cik,
                    file_name=pagination_outcome.file_name,
                )
                pagination_outcomes.append(
                    SubmissionsPaginationOutcome(
                        cik=cik,
                        file_name=pagination_outcome.file_name,
                        decision_id=pagination_outcome.decision_id,
                        processing_decision=decision,
                        error=None,
                    )
                )
            except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
                pagination_outcomes.append(
                    SubmissionsPaginationOutcome(
                        cik=cik,
                        file_name=pagination_outcome.file_name,
                        decision_id=pagination_outcome.decision_id,
                        processing_decision=None,
                        error=str(error),
                    )
                )

        if (
            candidate_outcome.fetch_state is not FetchWorkState.CAPTURED
            or candidate_outcome.decision_id is None
        ):
            continue
        if not candidate_outcome.pagination_complete:
            # Ticket 21 bullet 2: cannot declare completeness (i.e. must not
            # even attempt to seal Silver producers) while a referenced
            # pagination file is unsettled -- leave this main candidate
            # entirely unattempted so the next replay retries once its
            # pagination files have settled, rather than sealing a
            # ProcessingDecision this run and being stuck with it.
            continue
        try:
            decision = _finalize_main_candidate(
                ledger,
                bronze_root,
                revisions,
                processing,
                finalizer,
                silver,
                candidate_outcome.decision_id,
                cik=cik,
            )
            main_outcomes.append(
                SubmissionsMainOutcome(
                    cik=cik,
                    decision_id=candidate_outcome.decision_id,
                    processing_decision=decision,
                    error=None,
                )
            )
        except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
            main_outcomes.append(
                SubmissionsMainOutcome(
                    cik=cik,
                    decision_id=candidate_outcome.decision_id,
                    processing_decision=None,
                    error=str(error),
                )
            )

    return SubmissionsSilverAcceptanceResult(
        main_outcomes=tuple(main_outcomes), pagination_outcomes=tuple(pagination_outcomes)
    )
