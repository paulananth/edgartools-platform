"""Carry a captured ``reference_catalog`` candidate through to Silver (Ticket 23).

Family-specific wiring for the generic mechanism in ``processing.py``,
mirroring ``company_facts_silver_acceptance.py``'s shape but per-source-name
rather than per-CIK: one producer (``sec_company_ticker``) per catalog
snapshot, scoped to that snapshot's own ``source_name``.

Retirement: reuses ``SilverDatabase.replace_company_tickers`` exactly as the
legacy ``_sync_reference_data`` path already does -- a per-``source_name``
delete-then-insert against the *local candidate* Silver database. This is
pre-existing legacy behavior on a method reused unmodified (same posture as
Ticket 22 reusing ``merge_financial_facts`` unmodified); this module does not
introduce a new deletion mechanism, it only gates the existing one behind
CAPTURED-and-complete (bullet 3: "partial, unavailable, or malformed catalogs
cannot ... retire prior authoritative members"). Nothing reaches Silver
unless the candidate is CAPTURED with a complete payload
(``ReferenceCatalogPolicy.is_complete``), and a snapshot whose
``ContentImpact`` is unchanged seals with empty expected producers, touching
nothing -- same pattern as Tickets 21/22's analogous bullet.

Known, pre-existing gap this module does NOT fix (confirmed live against
``silver_protection.py``'s own docstring, not assumed): ``merge_candidate_
into_canonical`` "never deletes a row that exists only in canonical (a
partial candidate is expected and must not regress coverage)". So while this
module's local candidate write correctly retires a ticker that has dropped
out of a fresh snapshot (the ``DELETE FROM sec_company_ticker WHERE
source_name = ?`` inside ``replace_company_tickers``), that retirement does
NOT propagate to canonical once the candidate is merged -- a stale ticker
mapping removed from the source can persist in canonical indefinitely. This
is the same, already-known gap Ticket 02's table-change-semantics inventory
already recorded ("Local replacement deletes for ticker catalogs ... are not
exported"), now confirmed to also apply at the DuckDB candidate-to-canonical
merge layer, not just the Snowflake-landing-export layer this ticket doesn't
touch. Fixing ``merge_candidate_into_canonical``'s conservative "never
shrinks a scope" policy is a real design change (it exists specifically to
protect a windowed CIK-slice candidate from looking like "the whole table
shrank") and is out of this ticket's scope -- flagged here, not silently
carried forward as an assumption.

``seed_company_sync_state_bulk`` (the legacy path's CIK-universe-seeding side
effect, `` _sync_reference_data``) is deliberately NOT reproduced here: it is
Ticket 20's Acquisition Universe seeding concern, not a Silver domain
producer this family's ``required_producers`` model can express (there is no
Silver domain table or read-back verification for it). Whoever cuts a
universe-seeding command over to this new family must decide independently
how/where that seeding happens.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from edgar_warehouse.acquisition.ledger import AcquisitionLedger, FetchWorkState
from edgar_warehouse.acquisition.processing import (
    ExpectedProducerOutcome,
    ExpectedProducerSpec,
    ProcessingDecision,
    ProcessingLedger,
    SilverFinalizer,
)
from edgar_warehouse.acquisition.reference_catalog_discovery import ReferenceCatalogDriveResult
from edgar_warehouse.acquisition.revisions import ContentImpact, SourceRevisionLedger
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_store import SilverDatabase

REFERENCE_CATALOG_PRODUCER_NAME = "sec_company_ticker"
REFERENCE_CATALOG_TARGET_TABLE = "sec_company_ticker"

# Same honest bounded-first-slice stance as submissions'/company_facts's own
# *_INTERPRETATION_VERSION: no real interpretation-vs-transport distinction
# exists yet for this family.
REFERENCE_CATALOG_INTERPRETATION_VERSION = "raw-passthrough-v1"


class CandidateNotCaptured(RuntimeError):
    """The referenced decision has not reached a CAPTURED Bronze evidence state."""


class UnsupportedRequiredProducers(RuntimeError):
    """A covered family declares a required_producers set this Strategy's
    write bodies cannot serve. Ticket 32 bullet 1's pattern, checked upfront
    from the start (Ticket 21's own Standards review caught this missing on
    its first pass) -- mirrors the sibling modules' ``UnsupportedRequiredProducers``
    exactly, for this family's own single-producer set.
    """


def bronze_reference_to_raw_evidence_hash(bronze_relative_path: str) -> str:
    """Mirrors ``silver_acceptance.bronze_reference_to_raw_evidence_hash``
    exactly -- same Bronze naming convention (``source_family/hash``).
    """

    return bronze_relative_path.rsplit("/", 1)[-1]


def _member_digest(keys: list[tuple]) -> str:
    """Order-independent, ordered-output digest over a set of business keys.

    Same shape as ``company_facts_silver_acceptance._member_digest`` (this is
    its second occurrence across the acquisition modules -- worth extracting
    to a shared helper once a third family repeats it, per this repo's own
    "two adapters is hypothetical, three is real" seam-extraction stance; not
    done here). Each key's leading element is an ordinal (see
    ``_finalize_reference_catalog_candidate`` below), so sorting by key
    reproduces the catalog's own file order -- the digest captures the
    catalog's exact member sequence, not just its unordered membership,
    satisfying bullet 2's "ordered member-key digest" wording.
    """

    canonical = "\n".join("|".join(str(part) for part in key) for key in sorted(keys))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReferenceCatalogOutcome:
    source_name: str
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
class ReferenceCatalogSilverAcceptanceResult:
    outcomes: tuple[ReferenceCatalogOutcome, ...]

    @property
    def interval_complete(self) -> bool:
        return all(o.settled for o in self.outcomes)


def _read_bronze_bytes(bronze_root: StorageLocation, relative_path: str) -> bytes:
    from edgar_warehouse.infrastructure.object_storage import read_bytes

    return read_bytes(bronze_root.join(relative_path))


def _finalize_reference_catalog_candidate(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    revisions: SourceRevisionLedger,
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    decision_id: str,
    *,
    source_name: str,
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
        contract_version=REFERENCE_CATALOG_INTERPRETATION_VERSION,
        parser_version=REFERENCE_CATALOG_INTERPRETATION_VERSION,
        schema_version=REFERENCE_CATALOG_INTERPRETATION_VERSION,
        configuration_version=REFERENCE_CATALOG_INTERPRETATION_VERSION,
        source_native_revision=f"reference-catalog/{source_name}",
    )

    if revision.content_impact is ContentImpact.NO_IMPACT:
        return processing.seal_expected_producers(revision.revision_id)

    catalog_bytes = _read_bronze_bytes(bronze_root, status.captured_artifact_reference)
    try:
        document = json.loads(catalog_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        # is_complete() already proved this is a well-formed SEC ticker
        # catalog shape at fetch time -- a reparse failure here would
        # indicate a Bronze read-back mismatch, not a genuinely malformed
        # snapshot. Seal FAILED rather than raising, matching Ticket 22's
        # equivalent payload-reparse-failure handling.
        decision = processing.seal_expected_producers(
            revision.revision_id,
            expected_producers=(
                ExpectedProducerSpec(
                    producer_name=REFERENCE_CATALOG_PRODUCER_NAME,
                    target_table=REFERENCE_CATALOG_TARGET_TABLE,
                    scope_reference=f"reference-catalog/{source_name}",
                ),
            ),
        )
        return finalizer.record_producer_outcome(
            decision.processing_decision_id,
            REFERENCE_CATALOG_PRODUCER_NAME,
            outcome=ExpectedProducerOutcome.FAILED,
            failure_detail=(
                f"reference catalog payload for source_name={source_name!r} is not "
                f"valid JSON: {error}"
            ),
        )

    from edgar_warehouse.silver_store import _parse_company_ticker_rows

    parsed_rows = _parse_company_ticker_rows(document)
    # replace_company_tickers itself skips any row with a missing cik or a
    # falsy ticker (silver_store.py's `if cik is None or not ticker: continue`)
    # -- filtered here too, upfront, so member_keys/scope_reference/the
    # written-set verification below all agree with what actually lands in
    # Silver. Standards review caught this: _parse_company_ticker_rows's
    # numbered-dict branch (company_tickers.json's shape) only guards a
    # missing cik, not an empty ticker string, so an unfiltered `rows` could
    # count a row the writer silently drops -- producing a false FAILED
    # verification for a real SEC catalog entry with a blank ticker.
    rows = [r for r in parsed_rows if r.get("cik") is not None and r.get("ticker")]
    member_keys = [
        (ordinal, row["cik"], row["ticker"], row.get("exchange"))
        for ordinal, row in enumerate(rows, start=1)
    ]

    decision = processing.seal_expected_producers(
        revision.revision_id,
        expected_producers=(
            ExpectedProducerSpec(
                producer_name=REFERENCE_CATALOG_PRODUCER_NAME,
                target_table=REFERENCE_CATALOG_TARGET_TABLE,
                scope_reference=(
                    f"reference-catalog/{source_name}/sec_company_ticker/"
                    f"count={len(member_keys)}/digest={_member_digest(member_keys)}"
                ),
            ),
        ),
    )
    pending_producer_names = {
        p.producer_name for p in decision.expected_producers if p.outcome is ExpectedProducerOutcome.PENDING
    }
    if REFERENCE_CATALOG_PRODUCER_NAME not in pending_producer_names:
        return decision

    silver.replace_company_tickers(rows, decision_id, source_name=source_name)
    written_pairs = {(row["cik"], row["ticker"]) for row in rows}
    if written_pairs:
        present = silver.fetch(
            "SELECT cik, ticker FROM sec_company_ticker WHERE source_name = ?",
            [source_name],
        )
        verified = {(r["cik"], r["ticker"]) for r in present} == written_pairs
    else:
        # Complete-empty scope: a valid catalog snapshot can legitimately
        # carry zero members (bullet 2). Zero written, zero expected, so this
        # settles VERIFIED trivially -- not a failure.
        present = silver.fetch(
            "SELECT cik, ticker FROM sec_company_ticker WHERE source_name = ?",
            [source_name],
        )
        verified = len(present) == 0

    return finalizer.record_producer_outcome(
        decision.processing_decision_id,
        REFERENCE_CATALOG_PRODUCER_NAME,
        outcome=ExpectedProducerOutcome.VERIFIED if verified else ExpectedProducerOutcome.FAILED,
        verified_reference=f"reference-catalog/{source_name}" if verified else None,
        failure_detail=(
            None
            if verified
            else (
                f"sec_company_ticker read-back for source_name={source_name!r} did not "
                "match the written member set"
            )
        ),
    )


def drive_reference_catalog_silver_acceptance(
    ledger: AcquisitionLedger,
    bronze_root: StorageLocation,
    revisions: SourceRevisionLedger,
    processing: ProcessingLedger,
    finalizer: SilverFinalizer,
    silver: SilverDatabase,
    result: ReferenceCatalogDriveResult,
    *,
    required_producers: tuple[str, ...] = (REFERENCE_CATALOG_PRODUCER_NAME,),
) -> ReferenceCatalogSilverAcceptanceResult:
    """Carry every CAPTURED candidate in a reference-catalog drive result to Silver.

    Mirrors ``company_facts_silver_acceptance.drive_company_facts_silver_acceptance``'s
    per-candidate fault isolation and upfront required_producers validation
    exactly (Ticket 32 bullet 1's pattern).
    """

    if set(required_producers) != {REFERENCE_CATALOG_PRODUCER_NAME}:
        raise UnsupportedRequiredProducers(
            f"required_producers={required_producers!r} for reference_catalog, but "
            f"this Strategy's Silver-write body only knows how to produce "
            f"{{{REFERENCE_CATALOG_PRODUCER_NAME!r}}}"
        )

    outcomes: list[ReferenceCatalogOutcome] = []
    for candidate_outcome in result.outcomes:
        source_name = candidate_outcome.candidate.source_name
        if (
            candidate_outcome.fetch_state is not FetchWorkState.CAPTURED
            or candidate_outcome.decision_id is None
        ):
            continue
        try:
            decision = _finalize_reference_catalog_candidate(
                ledger,
                bronze_root,
                revisions,
                processing,
                finalizer,
                silver,
                candidate_outcome.decision_id,
                source_name=source_name,
            )
            outcomes.append(
                ReferenceCatalogOutcome(
                    source_name=source_name,
                    decision_id=candidate_outcome.decision_id,
                    processing_decision=decision,
                    error=None,
                )
            )
        except Exception as error:  # noqa: BLE001 -- one candidate must not abort the interval
            outcomes.append(
                ReferenceCatalogOutcome(
                    source_name=source_name,
                    decision_id=candidate_outcome.decision_id,
                    processing_decision=None,
                    error=str(error),
                )
            )

    return ReferenceCatalogSilverAcceptanceResult(outcomes=tuple(outcomes))
