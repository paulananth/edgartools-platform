"""Change-propagation Ticket 11: end-to-end acceptance evidence.

The ticket's own requirement: a versioned, secret-safe acceptance schema
that records selected/processed/skipped keys and costs so "success cannot
be inferred from row counts or clean logs alone." This module does not
re-implement any stage's own correctness logic -- Tickets 04-10/33/40/41/51
already proved every populable scenario with real evidence types
(``ContentImpact``, ``ExpectedProducerStatus``, ``ParityVerdict``,
``CauseAlignment``). The adapters below bind that existing evidence onto
one shared shape; ``unavailable()`` is the fail-closed slot for a scenario
this map has designed but not yet built a live evidence source for
(Tickets 49/50).

Secret-safe by construction: every field is a reference, hash, enum, count,
or duration -- never a payload, DSN, or presigned URL. See
``test_schema_fields_are_exactly_the_known_safe_set`` for the enforced
field-set lock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from edgar_warehouse.acquisition.capture_parity import ParityVerdict
from edgar_warehouse.acquisition.processing import ExpectedProducerOutcome, ExpectedProducerStatus
from edgar_warehouse.acquisition.revisions import ContentImpact
from edgar_warehouse.serving.watermark_aggregator import CauseAlignment

ACCEPTANCE_EVIDENCE_SCHEMA_VERSION = "1"


class AcceptanceScenario(StrEnum):
    """The 14 scenarios change-propagation Ticket 11 requires evidence for."""

    NOOP_REPLAY = "NOOP_REPLAY"
    MODIFIED_KEY_PROPAGATION = "MODIFIED_KEY_PROPAGATION"
    RETIRE = "RETIRE"
    SCOPE_COMPLETE = "SCOPE_COMPLETE"
    CONCURRENT_PRODUCERS = "CONCURRENT_PRODUCERS"
    PARTIAL_LOAD_RESUME = "PARTIAL_LOAD_RESUME"
    OUT_OF_ORDER_DELIVERY = "OUT_OF_ORDER_DELIVERY"
    REPAIR_ATTESTATION = "REPAIR_ATTESTATION"
    BOUNDED_MDM_CLOSURE = "BOUNDED_MDM_CLOSURE"
    GOLD_AFFECTED_DAG = "GOLD_AFFECTED_DAG"
    GRAPH_PARTITION_REUSE = "GRAPH_PARTITION_REUSE"
    GRAPH_VERIFICATION_ACTIVATION = "GRAPH_VERIFICATION_ACTIVATION"
    RECONCILIATION_BACKSTOP = "RECONCILIATION_BACKSTOP"
    DECISION_WATERMARK_ALIGNMENT = "DECISION_WATERMARK_ALIGNMENT"


@dataclass(frozen=True)
class AcceptanceEvidence:
    """One scenario's acceptance record for one Change Propagation Run.

    ``available=False`` means this scenario has no populable evidence
    source in the running system today (a designed-but-unbuilt stage) --
    distinct from ``available=True, passed=False``, which means real
    evidence was checked and failed.
    """

    schema_version: str
    scenario: AcceptanceScenario
    cause_reference: str
    selected_keys: tuple[str, ...]
    processed_keys: tuple[str, ...]
    skipped_keys: tuple[str, ...]
    cost_seconds: float | None
    cost_network_calls: int | None
    available: bool
    passed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario": str(self.scenario),
            "cause_reference": self.cause_reference,
            "selected_keys": list(self.selected_keys),
            "processed_keys": list(self.processed_keys),
            "skipped_keys": list(self.skipped_keys),
            "cost_seconds": self.cost_seconds,
            "cost_network_calls": self.cost_network_calls,
            "available": self.available,
            "passed": self.passed,
            "reasons": list(self.reasons),
        }


def build_acceptance_evidence(
    *,
    scenario: AcceptanceScenario,
    cause_reference: str,
    selected_keys: tuple[str, ...],
    processed_keys: tuple[str, ...],
    skipped_keys: tuple[str, ...],
    passed: bool,
    reasons: tuple[str, ...],
    cost_seconds: float | None = None,
    cost_network_calls: int | None = None,
) -> AcceptanceEvidence:
    """Fail-closed constructor -- the only way to build an ``available=True``
    record. A caller's ``passed=True`` claim is downgraded, never trusted
    outright, whenever the record's own shape can't support it:

    - any ``reasons`` present forces ``passed=False``;
    - touching zero keys (nothing selected, processed, or skipped) forces
      ``passed=False`` -- this is the ticket's own requirement that a
      clean-looking run with nothing to show for it can never read as
      success.
    """

    computed_reasons = list(reasons)
    if not selected_keys and not processed_keys and not skipped_keys:
        computed_reasons.append(
            "no keys were selected, processed, or skipped -- "
            "cannot infer success from an empty record"
        )
    resolved_passed = passed and not computed_reasons
    return AcceptanceEvidence(
        schema_version=ACCEPTANCE_EVIDENCE_SCHEMA_VERSION,
        scenario=scenario,
        cause_reference=cause_reference,
        selected_keys=tuple(selected_keys),
        processed_keys=tuple(processed_keys),
        skipped_keys=tuple(skipped_keys),
        cost_seconds=cost_seconds,
        cost_network_calls=cost_network_calls,
        available=True,
        passed=resolved_passed,
        reasons=tuple(computed_reasons),
    )


def unavailable(scenario: AcceptanceScenario, *, reason: str) -> AcceptanceEvidence:
    """Record a scenario this map has designed but has no live evidence
    source for yet (Tickets 49/50: 1-hop MDM candidate-neighbor expansion,
    the MDM Reconciliation Backstop). Fails closed like every other gap
    here -- never silently green.
    """

    return AcceptanceEvidence(
        schema_version=ACCEPTANCE_EVIDENCE_SCHEMA_VERSION,
        scenario=scenario,
        cause_reference="",
        selected_keys=(),
        processed_keys=(),
        skipped_keys=(),
        cost_seconds=None,
        cost_network_calls=None,
        available=False,
        passed=False,
        reasons=(reason,),
    )


# -- adapters: bind existing evidence types, never re-derive them -----------


def from_content_impact(
    impact: ContentImpact, *, cause_reference: str, logical_source_key: str
) -> AcceptanceEvidence:
    """Ticket 03/18's ``ContentImpact`` is already the no-op-replay /
    modified-key-propagation evidence -- ``NO_IMPACT`` is a genuine no-op
    (the key was checked and correctly skipped), ``CHANGED`` is real
    propagation.
    """

    if impact is ContentImpact.NO_IMPACT:
        return build_acceptance_evidence(
            scenario=AcceptanceScenario.NOOP_REPLAY,
            cause_reference=cause_reference,
            selected_keys=(logical_source_key,),
            processed_keys=(),
            skipped_keys=(logical_source_key,),
            passed=True,
            reasons=(),
        )
    return build_acceptance_evidence(
        scenario=AcceptanceScenario.MODIFIED_KEY_PROPAGATION,
        cause_reference=cause_reference,
        selected_keys=(logical_source_key,),
        processed_keys=(logical_source_key,),
        skipped_keys=(),
        passed=True,
        reasons=(),
    )


def from_expected_producer_status(
    status: ExpectedProducerStatus,
    *,
    cause_reference: str,
    scenario: AcceptanceScenario,
) -> AcceptanceEvidence:
    """Ticket 19's ``ExpectedProducerStatus`` already carries SCOPE_COMPLETE
    and partial-load/resume evidence: ``VERIFIED``/``NO_IMPACT`` converged,
    ``PENDING`` is a genuine partial in progress, ``FAILED`` carries its
    own ``failure_detail``.
    """

    key = status.scope_reference
    if status.outcome in (ExpectedProducerOutcome.VERIFIED, ExpectedProducerOutcome.NO_IMPACT):
        return build_acceptance_evidence(
            scenario=scenario,
            cause_reference=cause_reference,
            selected_keys=(key,),
            processed_keys=(key,),
            skipped_keys=(),
            passed=True,
            reasons=(),
        )
    if status.outcome is ExpectedProducerOutcome.PENDING:
        return build_acceptance_evidence(
            scenario=scenario,
            cause_reference=cause_reference,
            selected_keys=(key,),
            processed_keys=(),
            skipped_keys=(),
            passed=False,
            reasons=("producer outcome still PENDING",),
        )
    return build_acceptance_evidence(
        scenario=scenario,
        cause_reference=cause_reference,
        selected_keys=(key,),
        processed_keys=(),
        skipped_keys=(),
        passed=False,
        reasons=(status.failure_detail or "producer outcome FAILED",),
    )


def from_parity_verdict(
    verdict: ParityVerdict, *, cause_reference: str
) -> AcceptanceEvidence:
    """Ticket 51/53's ``ParityVerdict`` already proves modified-key
    propagation is complete (gated equal-or-superset of legacy) -- bound
    unmodified, not re-derived.

    ``only_gated`` keys are a real, expected case under "equal-or-superset"
    (the gated path is allowed to find more than legacy) -- counted as
    processed, not silently dropped from the record.
    """

    keys = verdict.logical_source_keys
    selected = keys.shared | keys.only_legacy | keys.only_gated
    processed = keys.shared | keys.only_gated
    return build_acceptance_evidence(
        scenario=AcceptanceScenario.MODIFIED_KEY_PROPAGATION,
        cause_reference=cause_reference,
        selected_keys=tuple(sorted(selected)),
        processed_keys=tuple(sorted(processed)),
        skipped_keys=(),
        passed=verdict.passed,
        reasons=verdict.reasons,
    )


def from_cause_alignment(row: CauseAlignment) -> AcceptanceEvidence:
    """Ticket 41's ``CauseAlignment`` is already the aligned-Decision-
    Watermark evidence for one ``cause_reference`` -- bound unmodified.
    """

    return build_acceptance_evidence(
        scenario=AcceptanceScenario.DECISION_WATERMARK_ALIGNMENT,
        cause_reference=row.cause_reference,
        selected_keys=(row.cause_reference,),
        processed_keys=(row.cause_reference,) if row.aligned else (),
        skipped_keys=(),
        passed=row.aligned,
        reasons=() if row.aligned else (f"stuck at stage: {row.stuck_stage}",),
    )
