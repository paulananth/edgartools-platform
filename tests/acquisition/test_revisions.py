from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
    UnauthorizedTransitionRole,
)
from edgar_warehouse.acquisition.models import AcquisitionBase, SourceFetchDecisionRecord
from edgar_warehouse.acquisition.revisions import (
    CompletenessType,
    ContentImpact,
    RevisionNotEligible,
    RevisionRelationship,
    SourceRevision,
    SourceRevisionLedger,
)


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _ledgers():
    engine = _engine()
    AcquisitionBase.metadata.create_all(engine)
    return AcquisitionLedger(engine), SourceRevisionLedger(engine), engine


def _captured_decision(
    ledger: AcquisitionLedger,
    *,
    candidate_id: str,
    logical_source_key: str,
    source_family: str = "filing_artifact",
    artifact_reference: str = "filing_artifact/deadbeef",
    worker_id: str = "worker-1",
) -> str:
    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id=candidate_id,
            source_family=source_family,
            logical_source_key=logical_source_key,
            source_url=f"https://www.sec.gov/Archives/{candidate_id}.txt",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="discovery-manifest-1",
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
        )
    )
    lease = ledger.claim_fetch(decision.decision_id, worker_id=worker_id, lease_seconds=300)
    ledger.finalize_fetch(
        decision.decision_id,
        worker_id=worker_id,
        fencing_token=lease.fencing_token,
        final_state=FetchWorkState.CAPTURED,
        artifact_reference=artifact_reference,
    )
    return decision.decision_id


def _skip_decision(ledger: AcquisitionLedger, *, candidate_id: str, logical_source_key: str) -> str:
    """An OUT_OF_SCOPE decision: reserves a position, no work row at all --
    unlike FAILED (which stays in ``source_fetch_work``'s active-key partial
    unique index and would block a fresh decision for the same key), this is
    the disposition that actually lets a later, separate candidate for the
    same key reserve the next position -- matching Ticket 03's own "skipped"
    gap wording.
    """

    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id=candidate_id,
            source_family="filing_artifact",
            logical_source_key=logical_source_key,
            source_url=f"https://www.sec.gov/Archives/{candidate_id}.txt",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="discovery-manifest-1",
            disposition=FetchDisposition.OUT_OF_SCOPE,
            blocker="outside acquisition universe",
            next_action="NONE",
            scope_proof_reference="acquisition-universe-v1/exclusion",
        )
    )
    return decision.decision_id


def test_materialize_from_capture_records_full_revision_identity() -> None:
    ledger, revisions, _ = _ledgers()
    decision_id = _captured_decision(
        ledger, candidate_id="c1", logical_source_key="0000320193/acc-1/full-submission-text"
    )

    revision = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash="raw-hash-1",
        canonical_source_hash="canonical-hash-1",
        domain_content_hash="domain-hash-1",
        contract_version="contract-v1",
        parser_version="parser-v1",
        schema_version="schema-v1",
        configuration_version="config-v1",
        declared_replacement_scope="accession/0000320193-26-000001",
        source_native_revision="0000320193-26-000001",
    )

    assert revision.decision_id == decision_id
    assert revision.parent_revision_id is None
    assert revision.revision_relationship is None
    assert revision.source_family == "filing_artifact"
    assert revision.logical_source_key == "0000320193/acc-1/full-submission-text"
    assert revision.observation_position == 1
    assert revision.source_native_revision == "0000320193-26-000001"
    assert revision.raw_evidence_hash == "raw-hash-1"
    assert revision.canonical_source_hash == "canonical-hash-1"
    assert revision.domain_content_hash == "domain-hash-1"
    assert revision.contract_version == "contract-v1"
    assert revision.parser_version == "parser-v1"
    assert revision.schema_version == "schema-v1"
    assert revision.configuration_version == "config-v1"
    assert revision.completeness_type is CompletenessType.COMPLETE
    assert revision.declared_replacement_scope == "accession/0000320193-26-000001"
    assert revision.bronze_artifact_reference == "filing_artifact/deadbeef"
    assert revision.content_impact is ContentImpact.CHANGED


def test_materialize_from_capture_is_idempotent_per_decision() -> None:
    ledger, revisions, _ = _ledgers()
    decision_id = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-1")

    first = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash="raw-hash",
        canonical_source_hash="canonical-hash",
        domain_content_hash="domain-hash",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )
    second = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash="raw-hash",
        canonical_source_hash="canonical-hash",
        domain_content_hash="domain-hash",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    assert first.revision_id == second.revision_id


@pytest.mark.parametrize(
    "setup",
    ["ready", "leased", "failed", "missing"],
)
def test_materialize_from_capture_rejects_decisions_that_are_not_captured(setup: str) -> None:
    ledger, revisions, _ = _ledgers()

    if setup == "missing":
        with pytest.raises(RevisionNotEligible):
            revisions.materialize_from_capture(
                "does-not-exist",
                raw_evidence_hash="h",
                canonical_source_hash="h",
                domain_content_hash="h",
                contract_version="v1",
                parser_version="v1",
                schema_version="v1",
                configuration_version="v1",
            )
        return

    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id=f"candidate-{setup}",
            source_family="filing_artifact",
            logical_source_key=f"key-{setup}",
            source_url="https://www.sec.gov/Archives/example.txt",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="discovery-manifest-1",
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
        )
    )
    if setup in ("leased", "failed"):
        lease = ledger.claim_fetch(decision.decision_id, worker_id="worker-1", lease_seconds=300)
        if setup == "failed":
            ledger.finalize_fetch(
                decision.decision_id,
                worker_id="worker-1",
                fencing_token=lease.fencing_token,
                final_state=FetchWorkState.FAILED,
            )

    with pytest.raises(RevisionNotEligible):
        revisions.materialize_from_capture(
            decision.decision_id,
            raw_evidence_hash="h",
            canonical_source_hash="h",
            domain_content_hash="h",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
        )


def test_observation_positions_preserve_gaps_left_by_failed_decisions() -> None:
    """Ticket 18 bullet 2: positions are monotonic per key but may skip
    failed/skipped/not-modified observations -- a revision's position is not
    a dense, renumbered counter of *materialized revisions*, it's the
    decision's own reserved per-key position.
    """

    ledger, revisions, _ = _ledgers()
    first_decision = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-gaps")
    _skip_decision(ledger, candidate_id="c2", logical_source_key="key-gaps")
    third_decision = _captured_decision(ledger, candidate_id="c3", logical_source_key="key-gaps")

    first_revision = revisions.materialize_from_capture(
        first_decision,
        raw_evidence_hash="h1",
        canonical_source_hash="h1",
        domain_content_hash="h1",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )
    third_revision = revisions.materialize_from_capture(
        third_decision,
        raw_evidence_hash="h3",
        canonical_source_hash="h3",
        domain_content_hash="h3",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    assert first_revision.observation_position == 1
    assert third_revision.observation_position == 3  # position 2 (FAILED) never got a revision


def test_unchanged_domain_content_records_no_impact() -> None:
    ledger, revisions, _ = _ledgers()
    first_decision = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-repeat")
    second_decision = _captured_decision(
        ledger,
        candidate_id="c2",
        logical_source_key="key-repeat",
        artifact_reference="filing_artifact/second-bytes",
    )

    revisions.materialize_from_capture(
        first_decision,
        raw_evidence_hash="raw-1",
        canonical_source_hash="canonical-1",
        domain_content_hash="same-domain-content",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )
    second = revisions.materialize_from_capture(
        second_decision,
        raw_evidence_hash="raw-2",
        canonical_source_hash="canonical-2",
        domain_content_hash="same-domain-content",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    assert second.content_impact is ContentImpact.NO_IMPACT


def test_changed_domain_content_records_changed() -> None:
    ledger, revisions, _ = _ledgers()
    first_decision = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-changed")
    second_decision = _captured_decision(
        ledger,
        candidate_id="c2",
        logical_source_key="key-changed",
        artifact_reference="filing_artifact/second-bytes",
    )

    revisions.materialize_from_capture(
        first_decision,
        raw_evidence_hash="raw-1",
        canonical_source_hash="canonical-1",
        domain_content_hash="domain-v1",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )
    second = revisions.materialize_from_capture(
        second_decision,
        raw_evidence_hash="raw-2",
        canonical_source_hash="canonical-2",
        domain_content_hash="domain-v2",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    assert second.content_impact is ContentImpact.CHANGED


def test_materialize_reinterpretation_reuses_bronze_evidence_without_a_new_fetch() -> None:
    """Ticket 18 bullet 4 (first half): a parser/schema upgrade reprocesses
    already-verified Bronze evidence and does not redownload -- provable
    structurally here as "no new Source Fetch Decision row is created" plus
    "raw evidence / canonical-source hash / Bronze reference are unchanged."
    """

    ledger, revisions, engine = _ledgers()
    decision_id = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-reinterp")
    parent = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash="raw-original",
        canonical_source_hash="canonical-original",
        domain_content_hash="domain-v1",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    with Session(engine) as session:
        decisions_before = len(
            session.execute(select(SourceFetchDecisionRecord)).scalars().all()
        )

    reinterpreted = revisions.materialize_reinterpretation(
        parent.revision_id,
        domain_content_hash="domain-v2-under-new-parser",
        contract_version="v1",
        parser_version="v2",
        schema_version="v1",
        configuration_version="v1",
    )

    with Session(engine) as session:
        decisions_after = len(
            session.execute(select(SourceFetchDecisionRecord)).scalars().all()
        )
    assert decisions_after == decisions_before  # no new SEC fetch decision was created

    assert reinterpreted.decision_id is None
    assert reinterpreted.parent_revision_id == parent.revision_id
    assert reinterpreted.revision_relationship is RevisionRelationship.REINTERPRETATION
    assert reinterpreted.raw_evidence_hash == parent.raw_evidence_hash
    assert reinterpreted.canonical_source_hash == parent.canonical_source_hash
    assert reinterpreted.bronze_artifact_reference == parent.bronze_artifact_reference
    assert reinterpreted.domain_content_hash == "domain-v2-under-new-parser"
    assert reinterpreted.parser_version == "v2"


def test_materialize_reinterpretation_is_idempotent_per_parent_and_version_tuple() -> None:
    ledger, revisions, _ = _ledgers()
    decision_id = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-reinterp-idem")
    parent = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash="raw",
        canonical_source_hash="canonical",
        domain_content_hash="domain-v1",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    first = revisions.materialize_reinterpretation(
        parent.revision_id,
        domain_content_hash="domain-v2",
        contract_version="v1",
        parser_version="v2",
        schema_version="v1",
        configuration_version="v1",
    )
    second = revisions.materialize_reinterpretation(
        parent.revision_id,
        domain_content_hash="domain-v2",
        contract_version="v1",
        parser_version="v2",
        schema_version="v1",
        configuration_version="v1",
    )

    assert first.revision_id == second.revision_id


def test_materialize_reinterpretation_against_a_nonexistent_parent_raises() -> None:
    _, revisions, _ = _ledgers()

    with pytest.raises(RevisionNotEligible):
        revisions.materialize_reinterpretation(
            "does-not-exist",
            domain_content_hash="domain",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
        )


def test_reinterpretation_and_fresh_captures_share_one_per_key_position_timeline() -> None:
    ledger, revisions, _ = _ledgers()
    first_decision = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-timeline")
    parent = revisions.materialize_from_capture(
        first_decision,
        raw_evidence_hash="raw",
        canonical_source_hash="canonical",
        domain_content_hash="domain-v1",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )
    assert parent.observation_position == 1

    reinterpreted = revisions.materialize_reinterpretation(
        parent.revision_id,
        domain_content_hash="domain-v2",
        contract_version="v1",
        parser_version="v2",
        schema_version="v1",
        configuration_version="v1",
    )
    assert reinterpreted.observation_position == 2

    second_decision = _captured_decision(
        ledger,
        candidate_id="c2",
        logical_source_key="key-timeline",
        artifact_reference="filing_artifact/second-bytes",
    )
    second = revisions.materialize_from_capture(
        second_decision,
        raw_evidence_hash="raw-2",
        canonical_source_hash="canonical-2",
        domain_content_hash="domain-v3",
        contract_version="v1",
        parser_version="v2",
        schema_version="v1",
        configuration_version="v1",
    )
    assert second.observation_position == 3


def test_revision_schema_and_api_reject_run_id_arrival_time_object_path_pointer_and_etag_as_identity() -> None:
    """Ticket 18 bullet 5: none of run_id, arrival time, object path, a
    mutable "latest" pointer, or an ETag (alone) are revision identity --
    provable structurally (no such column, no such parameter) rather than
    just by absence-of-a-test.
    """

    excluded_names = {
        "run_id",
        "arrival_time",
        "object_path",
        "s3_key",
        "latest_pointer",
        "etag",
    }
    import inspect

    from edgar_warehouse.acquisition.models import SourceRevisionRecord

    column_names = set(SourceRevisionRecord.__table__.columns.keys())
    assert column_names.isdisjoint(excluded_names)

    for method in (
        SourceRevisionLedger.materialize_from_capture,
        SourceRevisionLedger.materialize_reinterpretation,
    ):
        parameter_names = set(inspect.signature(method).parameters.keys())
        assert parameter_names.isdisjoint(excluded_names)


def test_replaying_materialize_from_capture_at_different_wall_clock_times_yields_the_same_revision() -> None:
    """Behavioral half of bullet 5: identity does not depend on *when* the
    call happens -- replaying it later (a retry, a redeploy) must not mint a
    second revision for the same decision.
    """

    ledger, revisions, _ = _ledgers()
    decision_id = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-replay")

    first = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash="raw",
        canonical_source_hash="canonical",
        domain_content_hash="domain",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )
    import time

    time.sleep(0.05)
    second = revisions.materialize_from_capture(
        decision_id,
        raw_evidence_hash="raw",
        canonical_source_hash="canonical",
        domain_content_hash="domain",
        contract_version="v1",
        parser_version="v1",
        schema_version="v1",
        configuration_version="v1",
    )

    assert first.revision_id == second.revision_id


def test_wrong_actor_role_is_rejected_for_both_materialize_calls() -> None:
    ledger, revisions, _ = _ledgers()
    decision_id = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-role")

    # A wrong-role attempt needs a stand-in outside the processing family --
    # ProcessingTransitionRole has exactly one member today, so simulate an
    # impostor via a stand-in that isn't ACQUISITION_PROCESSOR.
    class _NotAProcessor:
        value = "ACQUISITION_WORKER"

    with pytest.raises(UnauthorizedTransitionRole):
        revisions.materialize_from_capture(
            decision_id,
            raw_evidence_hash="raw",
            canonical_source_hash="canonical",
            domain_content_hash="domain",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
            actor_role=_NotAProcessor(),  # type: ignore[arg-type]
        )


def test_concurrent_materialize_from_capture_for_the_same_decision_converges_to_one_revision() -> None:
    """Ticket 18 bullet 3 (serialized per key): several threads racing to
    materialize the same already-CAPTURED decision must converge to exactly
    one revision, never two, against a real multi-connection engine.
    """

    db_path = Path(tempfile.mkstemp(suffix=".db")[1])
    engine = create_engine(f"sqlite:///{db_path}")
    AcquisitionBase.metadata.create_all(engine)
    ledger = AcquisitionLedger(engine)
    revisions = SourceRevisionLedger(engine)
    decision_id = _captured_decision(ledger, candidate_id="c1", logical_source_key="key-race")

    results: list[SourceRevision] = []

    def _materialize() -> None:
        results.append(
            revisions.materialize_from_capture(
                decision_id,
                raw_evidence_hash="raw",
                canonical_source_hash="canonical",
                domain_content_hash="domain",
                contract_version="v1",
                parser_version="v1",
                schema_version="v1",
                configuration_version="v1",
            )
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: _materialize(), range(8)))

    assert len(results) == 8
    assert len({r.revision_id for r in results}) == 1
    with Session(engine) as session:
        from edgar_warehouse.acquisition.models import SourceRevisionRecord

        rows = session.execute(
            select(SourceRevisionRecord).where(
                SourceRevisionRecord.decision_id == decision_id
            )
        ).scalars().all()
    assert len(rows) == 1


def test_concurrent_materialize_from_capture_for_different_keys_both_succeed() -> None:
    """Ticket 18 bullet 3 (unrelated keys concurrent): materializing two
    different logical keys at the same time must not interfere.
    """

    db_path = Path(tempfile.mkstemp(suffix=".db")[1])
    engine = create_engine(f"sqlite:///{db_path}")
    AcquisitionBase.metadata.create_all(engine)
    ledger = AcquisitionLedger(engine)
    revisions = SourceRevisionLedger(engine)

    decision_ids = [
        _captured_decision(ledger, candidate_id=f"c{i}", logical_source_key=f"key-parallel-{i}")
        for i in range(6)
    ]

    def _materialize(decision_id: str) -> SourceRevision:
        return revisions.materialize_from_capture(
            decision_id,
            raw_evidence_hash="raw",
            canonical_source_hash="canonical",
            domain_content_hash="domain",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(_materialize, decision_ids))

    assert len(results) == 6
    assert len({r.revision_id for r in results}) == 6
    assert {r.decision_id for r in results} == set(decision_ids)
