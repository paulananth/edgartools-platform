"""Carry a captured ``filing_artifact`` candidate through to Silver (Ticket 19).

This is the family-specific wiring for the generic mechanism in
``processing.py``: materialize the Logical Source Revision for an already
CAPTURED Source Fetch Decision, seal its expected Silver producer set, and --
for a revision whose content actually changed -- write and read back
``sec_raw_object`` (``edgar_warehouse.silver_store.SilverDatabase``) as this
family's one Silver producer.

Deliberately does not touch ``discovery.py``: that module's own docstring
says it "stays independent of the ~292KB legacy orchestrator," and pulling a
``SilverDatabase`` (DuckDB) dependency into it would re-acquire exactly the
coupling it was built to avoid. This module instead consumes an already
CAPTURED ``decision_id`` (e.g. from a ``DiscoveryDriveResult`` outcome) and
owns nothing upstream of capture.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchWorkState
from edgar_warehouse.acquisition.processing import (
    ExpectedProducerOutcome,
    ExpectedProducerSpec,
    ProcessingDecision,
    ProcessingLedger,
    SilverFinalizer,
)
from edgar_warehouse.acquisition.revisions import ContentImpact, SourceRevisionLedger
from edgar_warehouse.silver_store import SilverDatabase

FILING_ARTIFACT_PRODUCER_NAME = "sec_raw_object"
FILING_ARTIFACT_TARGET_TABLE = "sec_raw_object"

# Ticket 19's bounded first slice treats full-submission-text as an
# uninterpreted pass-through -- there is no real parsing yet (that is later,
# per-family migration work; see discovery.py's own docstring on
# spec.md's vertical-slice sequencing). All four interpretation identities
# share one version string, and canonical_source_hash/domain_content_hash
# both equal raw_evidence_hash: no transport normalization or interpretation
# happens to the bytes today. This is a deliberate, honest consequence, not
# an oversight -- it means content_impact can never distinguish "new
# transport bytes, same domain content" (Ticket 03's NO_IMPACT case) for
# this family until real interpretation lands; a byte-for-byte-identical
# resubmission is the only case this slice can currently detect as
# NO_IMPACT. A later family migration must not inherit this as an
# assumption once real parsing exists.
FILING_ARTIFACT_INTERPRETATION_VERSION = "raw-passthrough-v1"


class CandidateNotCaptured(RuntimeError):
    """The referenced decision has not reached a CAPTURED Bronze evidence state."""


def bronze_reference_to_raw_evidence_hash(bronze_relative_path: str) -> str:
    """Recover a Bronze object's raw evidence hash from its storage path.

    Bronze objects are keyed by exact raw-byte hash (Ticket 03), and
    ``facade._capture_bronze_evidence`` names every object
    ``f"{source_family}/{raw_evidence_hash}"`` -- the hash is always the
    final path segment. Recovering it this way avoids re-reading and
    re-hashing a potentially large Bronze object purely to relearn a value
    the capture path already computed and returned as
    ``CapturedArtifact.raw_evidence_hash``; see
    ``test_bronze_reference_to_raw_evidence_hash_matches_real_facade_output``
    for a regression test tying this parsing to the Facade's real output.
    """

    return bronze_relative_path.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class FilingArtifactCandidateMeta:
    """Denormalized candidate metadata needed to write ``sec_raw_object``."""

    cik: int
    accession_number: str
    form: str
    source_url: str


def finalize_filing_artifact_candidate(
    ledger: AcquisitionLedger,
    revisions: SourceRevisionLedger,
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    decision_id: str,
    candidate: FilingArtifactCandidateMeta,
) -> ProcessingDecision:
    """Carry one CAPTURED ``filing_artifact`` decision to a verified Silver
    publication or an explicit ``NO_IMPACT`` outcome.

    Requires ``decision_id`` to already be a CAPTURED Source Fetch Decision
    (e.g. an outcome from ``discovery.drive_discovery_manifest``) -- this
    function owns nothing upstream of capture, only carries an
    already-captured candidate the rest of the way. Idempotent: replaying
    with the same ``decision_id`` reuses the already-materialized revision,
    the already-sealed Processing Decision, and (via the Silver Finalizer's
    own idempotency) the already-recorded producer outcome rather than
    re-writing or re-verifying Silver state that already settled.
    """

    status = ledger.source_change_status(decision_id)
    if status.fetch_state is not FetchWorkState.CAPTURED:
        raise CandidateNotCaptured(
            f"decision_id={decision_id} is not CAPTURED "
            f"(fetch_state={status.fetch_state})"
        )
    assert status.captured_artifact_reference is not None  # CAPTURED requires it
    raw_evidence_hash = bronze_reference_to_raw_evidence_hash(
        status.captured_artifact_reference
    )

    revision = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash=raw_evidence_hash,
        canonical_source_hash=raw_evidence_hash,
        domain_content_hash=raw_evidence_hash,
        contract_version=FILING_ARTIFACT_INTERPRETATION_VERSION,
        parser_version=FILING_ARTIFACT_INTERPRETATION_VERSION,
        schema_version=FILING_ARTIFACT_INTERPRETATION_VERSION,
        configuration_version=FILING_ARTIFACT_INTERPRETATION_VERSION,
        source_native_revision=candidate.accession_number,
    )

    if revision.content_impact is ContentImpact.NO_IMPACT:
        return processing.seal_expected_producers(revision.revision_id)

    decision = processing.seal_expected_producers(
        revision.revision_id,
        expected_producers=(
            ExpectedProducerSpec(
                producer_name=FILING_ARTIFACT_PRODUCER_NAME,
                target_table=FILING_ARTIFACT_TARGET_TABLE,
                scope_reference=candidate.accession_number,
            ),
        ),
    )
    already_settled = next(
        (
            p
            for p in decision.expected_producers
            if p.producer_name == FILING_ARTIFACT_PRODUCER_NAME
            and p.outcome is not ExpectedProducerOutcome.PENDING
        ),
        None,
    )
    if already_settled is not None:
        return decision

    # sec_raw_object's business key IS the sha256 of the fetched bytes
    # (silver_protection.py's ProtectedTablePolicy for this table, and
    # every real writer in bronze_filing_artifacts.py, key it this way) --
    # not an arbitrary identifier. Using anything else (e.g. revision_id)
    # would defeat this table's whole content-dedup design: identical byte
    # content legitimately recurs across different filings (shared
    # boilerplate/exhibit templates), and downstream code keys off this
    # exact convention.
    raw_object_id = revision.raw_evidence_hash
    silver.upsert_raw_object(
        {
            "raw_object_id": raw_object_id,
            "source_type": "filing_artifact",
            "cik": candidate.cik,
            "accession_number": candidate.accession_number,
            "form": candidate.form,
            "source_url": candidate.source_url,
            "storage_path": status.captured_artifact_reference,
            "sha256": revision.raw_evidence_hash,
            "fetched_at": datetime.now(UTC),
            "http_status": 200,
        }
    )
    read_back = silver.get_raw_object(raw_object_id)
    if read_back is not None and read_back.get("sha256") == revision.raw_evidence_hash:
        return finalizer.record_producer_outcome(
            decision.processing_decision_id,
            FILING_ARTIFACT_PRODUCER_NAME,
            outcome=ExpectedProducerOutcome.VERIFIED,
            verified_reference=raw_object_id,
        )
    return finalizer.record_producer_outcome(
        decision.processing_decision_id,
        FILING_ARTIFACT_PRODUCER_NAME,
        outcome=ExpectedProducerOutcome.FAILED,
        failure_detail=(
            f"sec_raw_object read-back for raw_object_id={raw_object_id} did not "
            f"match expected sha256={revision.raw_evidence_hash!r} (got {read_back!r})"
        ),
    )
