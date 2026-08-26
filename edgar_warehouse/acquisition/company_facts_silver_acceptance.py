"""Carry a captured ``company_facts`` candidate through to Silver (Ticket 22).

Family-specific wiring for the generic mechanism in ``processing.py``,
mirroring ``submissions_silver_acceptance.py``'s shape but single-phase (one
producer pair per CIK, not two Silver scopes split across main/pagination
candidates).

Retirement (Ticket 33, change-propagation map): ``sec_financial_fact`` and
``sec_accounting_flag`` both gained ``valid_from``/``valid_to``/
``is_current`` columns (``silver_store.py``'s schema migration
``010_company_facts_retirement_columns``). A business key present in a
prior complete snapshot but absent from a fresh, verified-written one is
retired by closing its validity interval (``is_current=FALSE``,
``valid_to=<retirement time>``) via ``SilverDatabase.
retire_financial_facts_not_in_snapshot``/``retire_accounting_flags_not_in_snapshot``
-- never a physical DELETE, per the change-propagation spec's "RETIRE ...
never physically deletes history" rule. The comparison basis is each
table's own ``is_current=TRUE`` rows for the CIK (always exactly the prior
complete snapshot's membership set, since nothing else mutates
``is_current``), a per-CIK full-scope comparison, run only after this
snapshot's own write is confirmed VERIFIED. A retired key that reappears in
a later snapshot is reinstated by the merge methods' own ``ON CONFLICT``
branch, not by the retire call. Bullet 3 ("missing, partial, or failed
snapshots cannot retire prior facts or become the current Silver
authority") is satisfied the same way Ticket 21 satisfies its analogous
bullet plus this retirement gate: nothing reaches Silver unless the
candidate is CAPTURED with a complete payload
(``CompanyFactsPolicy.is_complete``), a snapshot whose ``ContentImpact`` is
unchanged seals with empty expected producers touching nothing, and a
FAILED write (read-back mismatch) skips retirement entirely rather than
retiring against an unconfirmed fact_keys set.

Bullet 2 ("Scope Completion includes the authoritative member count and
ordered digest") is a *recording* requirement, not a deletion one: each
producer's ``ExpectedProducerSpec.scope_reference`` carries its own
snapshot's member count and an ordered digest of its business-key set,
computed per-CIK and released immediately (never accumulated across a
batch -- see CLAUDE.md's gold-build-memory-OOM entry for why that matters
at scale).

``sec_financial_derived`` is deliberately NOT a required producer here: the
change-propagation spec classifies it as a "derived projection" that "consumes
committed base-silver publications ... never uncommitted landing output" --
computing it inside this same acceptance step (as the legacy
``run_bootstrap_entity_facts`` does) would violate that. It is left for a
separate downstream step, out of this ticket's scope. ``backfill_accounting_
flags`` (cross-period forensic scoring, reads back a CIK's whole stored
history) is likewise out of scope -- structurally the same shape as the
``backfill-mdm-entity-ids`` sweep, not a producer of this snapshot's scope.

Deliberately does not touch ``silver_store.py``'s existing merge methods --
reuses ``merge_financial_facts``/``merge_accounting_flags`` exactly as the
legacy path does.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from edgar_warehouse.acquisition.company_facts_discovery import CompanyFactsDriveResult
from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchWorkState
from edgar_warehouse.acquisition.processing import (
    ExpectedProducerOutcome,
    ExpectedProducerSpec,
    ProcessingDecision,
    ProcessingLedger,
    SilverFinalizer,
)
from edgar_warehouse.acquisition.revisions import ContentImpact, SourceRevisionLedger
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase

COMPANY_FACTS_FACT_PRODUCER_NAME = "sec_financial_fact"
COMPANY_FACTS_FACT_TARGET_TABLE = "sec_financial_fact"
COMPANY_FACTS_FLAG_PRODUCER_NAME = "sec_accounting_flag"
COMPANY_FACTS_FLAG_TARGET_TABLE = "sec_accounting_flag"

# Same honest bounded-first-slice stance as submissions'
# SUBMISSIONS_INTERPRETATION_VERSION: no real interpretation-vs-transport
# distinction exists yet for this family.
COMPANY_FACTS_INTERPRETATION_VERSION = "raw-passthrough-v1"


class CandidateNotCaptured(RuntimeError):
    """The referenced decision has not reached a CAPTURED Bronze evidence state."""


class UnsupportedRequiredProducers(RuntimeError):
    """A covered family declares a required_producers set this Strategy's
    write bodies cannot serve. Ticket 32 bullet 1's pattern, checked upfront
    this time (Standards review caught this missing on Ticket 21's first
    pass) -- mirrors ``submissions_silver_acceptance.UnsupportedRequiredProducers``
    exactly, for this family's own two-producer set.
    """


def bronze_reference_to_raw_evidence_hash(bronze_relative_path: str) -> str:
    """Mirrors ``silver_acceptance.bronze_reference_to_raw_evidence_hash``
    exactly -- same Bronze naming convention (``source_family/hash``).
    """

    return bronze_relative_path.rsplit("/", 1)[-1]


def _member_digest(keys: list[tuple]) -> str:
    """Order-independent, ordered-output digest over a set of business keys.

    Computed per-CIK, per-producer, and released immediately by the caller --
    never accumulated across a batch of CIKs.
    """

    canonical = "\n".join("|".join(str(part) for part in key) for key in sorted(keys))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CompanyFactsOutcome:
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
class CompanyFactsSilverAcceptanceResult:
    outcomes: tuple[CompanyFactsOutcome, ...]

    @property
    def interval_complete(self) -> bool:
        return all(o.settled for o in self.outcomes)


def _read_bronze_bytes(bronze_root: StorageLocation, relative_path: str) -> bytes:
    from edgar_warehouse.infrastructure.object_storage import read_bytes

    return read_bytes(bronze_root.join(relative_path))


def _finalize_company_facts_candidate(
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
        contract_version=COMPANY_FACTS_INTERPRETATION_VERSION,
        parser_version=COMPANY_FACTS_INTERPRETATION_VERSION,
        schema_version=COMPANY_FACTS_INTERPRETATION_VERSION,
        configuration_version=COMPANY_FACTS_INTERPRETATION_VERSION,
        source_native_revision=f"{cik}/company-facts",
    )

    if revision.content_impact is ContentImpact.NO_IMPACT:
        return processing.seal_expected_producers(revision.revision_id)

    facts_bytes = _read_bronze_bytes(bronze_root, status.captured_artifact_reference)
    try:
        facts_json = json.loads(facts_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        # is_complete() already proved this is a valid JSON object at fetch
        # time -- a reparse failure here would indicate a Bronze read-back
        # mismatch, not a genuinely malformed snapshot. Seal both producers
        # FAILED rather than raising, so this settles as a per-candidate
        # error the caller can isolate, matching submissions' equivalent
        # payload-reparse-failure handling.
        decision = processing.seal_expected_producers(
            revision.revision_id,
            expected_producers=(
                ExpectedProducerSpec(
                    producer_name=COMPANY_FACTS_FACT_PRODUCER_NAME,
                    target_table=COMPANY_FACTS_FACT_TARGET_TABLE,
                    scope_reference=f"{cik}/company-facts",
                ),
                ExpectedProducerSpec(
                    producer_name=COMPANY_FACTS_FLAG_PRODUCER_NAME,
                    target_table=COMPANY_FACTS_FLAG_TARGET_TABLE,
                    scope_reference=f"{cik}/company-facts",
                ),
            ),
        )
        for producer_name in (COMPANY_FACTS_FACT_PRODUCER_NAME, COMPANY_FACTS_FLAG_PRODUCER_NAME):
            decision = finalizer.record_producer_outcome(
                decision.processing_decision_id,
                producer_name,
                outcome=ExpectedProducerOutcome.FAILED,
                failure_detail=f"company-facts payload for cik={cik} is not valid JSON: {error}",
            )
        return decision

    from edgar_warehouse.parsers.financials import parse_entity_facts

    parsed = parse_entity_facts(cik=cik, facts_json=facts_json)
    fact_rows = parsed.get("sec_financial_fact", [])
    flag_rows = parsed.get("sec_accounting_flag", [])

    fact_keys = [
        (
            r["accession_number"], r["concept"], r["fiscal_period"],
            r.get("segment", "consolidated"), r.get("period_end"), r.get("period_start"),
        )
        for r in fact_rows
    ]
    flag_keys = [(r["accession_number"],) for r in flag_rows]

    decision = processing.seal_expected_producers(
        revision.revision_id,
        expected_producers=(
            ExpectedProducerSpec(
                producer_name=COMPANY_FACTS_FACT_PRODUCER_NAME,
                target_table=COMPANY_FACTS_FACT_TARGET_TABLE,
                scope_reference=(
                    f"{cik}/company-facts/sec_financial_fact/"
                    f"count={len(fact_keys)}/digest={_member_digest(fact_keys)}"
                ),
            ),
            ExpectedProducerSpec(
                producer_name=COMPANY_FACTS_FLAG_PRODUCER_NAME,
                target_table=COMPANY_FACTS_FLAG_TARGET_TABLE,
                scope_reference=(
                    f"{cik}/company-facts/sec_accounting_flag/"
                    f"count={len(flag_keys)}/digest={_member_digest(flag_keys)}"
                ),
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

    if COMPANY_FACTS_FACT_PRODUCER_NAME in pending_producer_names:
        silver.merge_financial_facts(fact_rows, decision_id)
        written_accessions = sorted({r["accession_number"] for r in fact_rows})
        if written_accessions:
            placeholders = ", ".join("?" * len(written_accessions))
            present = silver.fetch(
                f"SELECT DISTINCT accession_number FROM sec_financial_fact "
                f"WHERE cik = ? AND accession_number IN ({placeholders})",
                [cik, *written_accessions],
            )
            verified = {r["accession_number"] for r in present} == set(written_accessions)
        else:
            # Complete-empty scope: a real CIK can have zero XBRL facts
            # (e.g. a newly registered company). Zero written, zero
            # expected, so this settles VERIFIED trivially -- not a failure.
            verified = True
        if verified:
            # Ticket 33: only retire once this snapshot's own facts are
            # confirmed durably written -- a FAILED write must not retire
            # anything, since we can't yet trust fact_keys reflects what's
            # actually in Silver.
            silver.retire_financial_facts_not_in_snapshot(cik, fact_keys, decision_id)
        decision = finalizer.record_producer_outcome(
            decision.processing_decision_id,
            COMPANY_FACTS_FACT_PRODUCER_NAME,
            outcome=ExpectedProducerOutcome.VERIFIED if verified else ExpectedProducerOutcome.FAILED,
            verified_reference=f"{cik}/company-facts" if verified else None,
            failure_detail=(
                None
                if verified
                else f"sec_financial_fact read-back for cik={cik} did not find all written accessions"
            ),
        )

    if COMPANY_FACTS_FLAG_PRODUCER_NAME in pending_producer_names:
        silver.merge_accounting_flags(flag_rows, decision_id)
        written_flag_accessions = sorted({r["accession_number"] for r in flag_rows})
        if written_flag_accessions:
            placeholders = ", ".join("?" * len(written_flag_accessions))
            present = silver.fetch(
                f"SELECT accession_number FROM sec_accounting_flag "
                f"WHERE cik = ? AND accession_number IN ({placeholders})",
                [cik, *written_flag_accessions],
            )
            verified = {r["accession_number"] for r in present} == set(written_flag_accessions)
        else:
            verified = True
        if verified:
            silver.retire_accounting_flags_not_in_snapshot(cik, written_flag_accessions, decision_id)
        decision = finalizer.record_producer_outcome(
            decision.processing_decision_id,
            COMPANY_FACTS_FLAG_PRODUCER_NAME,
            outcome=ExpectedProducerOutcome.VERIFIED if verified else ExpectedProducerOutcome.FAILED,
            verified_reference=f"{cik}/company-facts" if verified else None,
            failure_detail=(
                None
                if verified
                else f"sec_accounting_flag read-back for cik={cik} did not find all written accessions"
            ),
        )

    return decision


def drive_company_facts_silver_acceptance(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    revisions: SourceRevisionLedger,
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    result: CompanyFactsDriveResult,
    *,
    required_producers: tuple[str, ...] = (
        COMPANY_FACTS_FACT_PRODUCER_NAME,
        COMPANY_FACTS_FLAG_PRODUCER_NAME,
    ),
) -> CompanyFactsSilverAcceptanceResult:
    """Carry every CAPTURED candidate in a company-facts drive result to Silver.

    Mirrors ``submissions_silver_acceptance.drive_submissions_silver_acceptance``'s
    per-candidate fault isolation and upfront required_producers validation
    exactly (Ticket 32 bullet 1's pattern, ported at the start this time).
    """

    if set(required_producers) != {
        COMPANY_FACTS_FACT_PRODUCER_NAME,
        COMPANY_FACTS_FLAG_PRODUCER_NAME,
    }:
        raise UnsupportedRequiredProducers(
            f"required_producers={required_producers!r} for company_facts, but "
            f"this Strategy's Silver-write bodies only know how to produce "
            f"{{{COMPANY_FACTS_FACT_PRODUCER_NAME!r}, {COMPANY_FACTS_FLAG_PRODUCER_NAME!r}}}"
        )

    outcomes: list[CompanyFactsOutcome] = []
    for candidate_outcome in result.outcomes:
        cik = candidate_outcome.candidate.cik
        if (
            candidate_outcome.fetch_state is not FetchWorkState.CAPTURED
            or candidate_outcome.decision_id is None
        ):
            continue
        try:
            decision = _finalize_company_facts_candidate(
                ledger,
                bronze_root,
                revisions,
                processing,
                finalizer,
                silver,
                candidate_outcome.decision_id,
                cik=cik,
            )
            outcomes.append(
                CompanyFactsOutcome(
                    cik=cik,
                    decision_id=candidate_outcome.decision_id,
                    processing_decision=decision,
                    error=None,
                )
            )
        except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
            outcomes.append(
                CompanyFactsOutcome(
                    cik=cik,
                    decision_id=candidate_outcome.decision_id,
                    processing_decision=None,
                    error=str(error),
                )
            )

    return CompanyFactsSilverAcceptanceResult(outcomes=tuple(outcomes))
