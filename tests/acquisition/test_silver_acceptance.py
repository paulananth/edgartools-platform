"""Ticket 19 bullet 5: assert durable external evidence, not concrete classes.

Every test in this file exercises ``finalize_filing_artifact_candidate``
against a real ``SilverDatabase`` (DuckDB) and reads the resulting
``sec_raw_object`` row back independently -- the assertions are on what
landed in that durable store, never on which internal Facade/Strategy/
handler object was invoked.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
)
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.acquisition.processing import (
    ExpectedProducerOutcome,
    ProcessingDisposition,
    ProcessingLedger,
    SilverFinalizer,
    SilverOutcome,
)
from edgar_warehouse.acquisition.revisions import SourceRevisionLedger
from edgar_warehouse.acquisition.silver_acceptance import (
    CandidateNotCaptured,
    FilingArtifactCandidateMeta,
    bronze_reference_to_raw_evidence_hash,
    finalize_filing_artifact_candidate,
)
from edgar_warehouse.silver_store import SilverDatabase


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _harness(tmp_path: Path):
    engine = _engine()
    AcquisitionBase.metadata.create_all(engine)
    silver = SilverDatabase(str(tmp_path / "silver.duckdb"))
    return (
        AcquisitionLedger(engine),
        SourceRevisionLedger(engine),
        ProcessingLedger(engine),
        SilverFinalizer(engine),
        silver,
    )


def _captured_decision(
    ledger: AcquisitionLedger,
    *,
    candidate_id: str,
    logical_source_key: str,
    artifact_reference: str,
    worker_id: str = "worker-1",
) -> str:
    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id=candidate_id,
            source_family="filing_artifact",
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


_META = FilingArtifactCandidateMeta(
    cik=320193,
    accession_number="0000320193-26-000001",
    form="4",
    source_url="https://www.sec.gov/Archives/edgar/data/320193/0000320193-26-000001.txt",
)


def test_finalize_writes_and_verifies_sec_raw_object(tmp_path: Path) -> None:
    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision_id = _captured_decision(
        ledger,
        candidate_id="c1",
        logical_source_key="320193/0000320193-26-000001/full-submission-text",
        artifact_reference="filing_artifact/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )

    decision = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, decision_id, _META
    )

    assert decision.disposition is ProcessingDisposition.PROCESS_REQUIRED
    assert decision.silver_outcome is SilverOutcome.PUBLISHED
    producer = decision.expected_producers[0]
    assert producer.outcome is ExpectedProducerOutcome.VERIFIED

    # raw_object_id is the content hash itself (sec_raw_object's
    # codebase-wide business key, per silver_protection.py's
    # ProtectedTablePolicy for this table), not an arbitrary identifier.
    assert producer.verified_reference == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    # Durable external evidence: read sec_raw_object back independently,
    # not via anything this call returned.
    raw_object = silver.get_raw_object(producer.verified_reference)
    assert raw_object is not None
    assert raw_object["sha256"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert raw_object["accession_number"] == "0000320193-26-000001"
    assert raw_object["cik"] == 320193
    assert raw_object["form"] == "4"
    assert raw_object["source_type"] == "filing_artifact"
    assert raw_object["storage_path"] == "filing_artifact/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_finalize_reuses_one_sec_raw_object_row_for_identical_content_across_accessions(
    tmp_path: Path,
) -> None:
    """sec_raw_object's whole design point (silver_protection.py's policy
    comment): identical byte content legitimately recurs across different
    filings (shared boilerplate/exhibit templates), fetched under different
    accessions -- content-addressing must actually dedupe this, not create
    one row per revision.
    """

    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    shared_hash_reference = "filing_artifact/99999999999999999999999999999999"
    first_meta = FilingArtifactCandidateMeta(
        cik=320193,
        accession_number="0000320193-26-000001",
        form="4",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/0000320193-26-000001.txt",
    )
    second_meta = FilingArtifactCandidateMeta(
        cik=789019,
        accession_number="0000789019-26-000042",
        form="4",
        source_url="https://www.sec.gov/Archives/edgar/data/789019/0000789019-26-000042.txt",
    )
    first_decision_id = _captured_decision(
        ledger,
        candidate_id="c1",
        logical_source_key="320193/0000320193-26-000001/full-submission-text",
        artifact_reference=shared_hash_reference,
    )
    second_decision_id = _captured_decision(
        ledger,
        candidate_id="c2",
        logical_source_key="789019/0000789019-26-000042/full-submission-text",
        artifact_reference=shared_hash_reference,
    )

    first = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, first_decision_id, first_meta
    )
    second = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, second_decision_id, second_meta
    )

    assert first.revision_id != second.revision_id
    first_ref = first.expected_producers[0].verified_reference
    second_ref = second.expected_producers[0].verified_reference
    assert first_ref == second_ref == "99999999999999999999999999999999"

    raw_object = silver.get_raw_object(first_ref)
    assert raw_object is not None
    # One physical row -- the second finalize's upsert landed on the same
    # content-addressed key, matching every other real writer of this table.
    row_count = silver._conn.execute(
        "SELECT COUNT(*) FROM sec_raw_object WHERE raw_object_id = ?", [first_ref]
    ).fetchone()[0]
    assert row_count == 1


def test_finalize_marks_failed_on_read_back_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A write that lands but reads back wrong content must be recorded
    FAILED, not VERIFIED -- read-back verification, not write success alone
    (Ticket 19 bullet 2).
    """

    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision_id = _captured_decision(
        ledger,
        candidate_id="c1",
        logical_source_key="320193/0000320193-26-000001/full-submission-text",
        artifact_reference="filing_artifact/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )

    real_upsert = silver.upsert_raw_object

    def _corrupting_upsert(row: dict) -> None:
        row = dict(row)
        row["sha256"] = "corrupted-on-write"
        real_upsert(row)

    monkeypatch.setattr(silver, "upsert_raw_object", _corrupting_upsert)

    decision = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, decision_id, _META
    )

    assert decision.silver_outcome is SilverOutcome.FAILED
    producer = decision.expected_producers[0]
    assert producer.outcome is ExpectedProducerOutcome.FAILED
    assert "did not match" in producer.failure_detail


def test_finalize_blocks_later_revision_for_same_key_after_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    logical_key = "320193/0000320193-26-000001/full-submission-text"
    first_decision_id = _captured_decision(
        ledger,
        candidate_id="c1",
        logical_source_key=logical_key,
        artifact_reference="filing_artifact/cccccccccccccccccccccccccccccccc",
    )

    real_upsert = silver.upsert_raw_object

    def _corrupting_upsert(row: dict) -> None:
        row = dict(row)
        row["sha256"] = "corrupted-on-write"
        real_upsert(row)

    monkeypatch.setattr(silver, "upsert_raw_object", _corrupting_upsert)
    first_result = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, first_decision_id, _META
    )
    assert first_result.silver_outcome is SilverOutcome.FAILED

    monkeypatch.setattr(silver, "upsert_raw_object", real_upsert)
    second_decision_id = _captured_decision(
        ledger,
        candidate_id="c2",
        logical_source_key=logical_key,
        artifact_reference="filing_artifact/dddddddddddddddddddddddddddddddd",
    )

    with pytest.raises(Exception) as excinfo:
        finalize_filing_artifact_candidate(
            ledger, revisions, processing, finalizer, silver, second_decision_id, _META
        )
    assert "PriorRevisionNotSettled" in type(excinfo.value).__name__

    # Prior Silver state remains exactly as it was -- the blocked later
    # attempt never wrote or touched sec_raw_object at all. The first
    # (failed) attempt's row is still there, still carrying the mismatched
    # content it failed on -- nothing repaired or overwrote it. raw_object_id
    # is the content hash (cccc...), not the revision_id.
    first_row = silver.get_raw_object("cccccccccccccccccccccccccccccccc")
    assert first_row is not None
    assert first_row["sha256"] == "corrupted-on-write"


def test_finalize_is_idempotent_on_replay(tmp_path: Path) -> None:
    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision_id = _captured_decision(
        ledger,
        candidate_id="c1",
        logical_source_key="320193/0000320193-26-000001/full-submission-text",
        artifact_reference="filing_artifact/eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    )

    first = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, decision_id, _META
    )
    second = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, decision_id, _META
    )

    assert first == second


def test_finalize_second_identical_capture_is_no_impact_and_publishes_with_no_producers(
    tmp_path: Path,
) -> None:
    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    logical_key = "320193/0000320193-26-000001/full-submission-text"
    same_bytes_reference = "filing_artifact/ffffffffffffffffffffffffffffffff"
    first_decision_id = _captured_decision(
        ledger, candidate_id="c1", logical_source_key=logical_key, artifact_reference=same_bytes_reference
    )
    finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, first_decision_id, _META
    )

    second_decision_id = _captured_decision(
        ledger, candidate_id="c2", logical_source_key=logical_key, artifact_reference=same_bytes_reference
    )
    second = finalize_filing_artifact_candidate(
        ledger, revisions, processing, finalizer, silver, second_decision_id, _META
    )

    assert second.disposition is ProcessingDisposition.NO_IMPACT
    assert second.silver_outcome is SilverOutcome.PUBLISHED
    assert second.expected_producers == ()


def test_finalize_requires_captured_decision(tmp_path: Path) -> None:
    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    decision = ledger.create_fetch_decision(
        FetchDecisionRequest(
            candidate_id="c1",
            source_family="filing_artifact",
            logical_source_key="320193/0000320193-26-000001/full-submission-text",
            source_url="https://www.sec.gov/Archives/c1.txt",
            cause=DecisionCause.CAPTURED_DISCOVERY,
            cause_reference="discovery-manifest-1",
            disposition=FetchDisposition.FETCH_AUTHORIZED,
            blocker=None,
            next_action="FETCH_SOURCE",
        )
    )

    with pytest.raises(CandidateNotCaptured):
        finalize_filing_artifact_candidate(
            ledger, revisions, processing, finalizer, silver, decision.decision_id, _META
        )


def test_bronze_reference_to_raw_evidence_hash_matches_real_facade_output(tmp_path: Path) -> None:
    """Ties this module's path-parsing to the Facade's actual naming
    convention with a real capture, not just a hand-written example.
    """

    from edgar_warehouse.acquisition.facade import build_capture_facade
    from edgar_warehouse.acquisition.ledger import execute_source_request
    from edgar_warehouse.infrastructure.object_storage import StorageLocation

    engine = _engine()
    AcquisitionBase.metadata.create_all(engine)
    ledger = AcquisitionLedger(engine)
    bronze_root = StorageLocation(str(tmp_path / "bronze"))

    class _Policy:
        def fetch(self, source_url: str) -> bytes:
            return b"real filing bytes for hash parsing test"

        def is_complete(self, payload: bytes) -> bool:
            return True

    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": _Policy()}, worker_id="worker-1"
    )
    request = FetchDecisionRequest(
        candidate_id="c1",
        source_family="filing_artifact",
        logical_source_key="320193/0000320193-26-000001/full-submission-text",
        source_url="https://www.sec.gov/Archives/c1.txt",
        cause=DecisionCause.CAPTURED_DISCOVERY,
        cause_reference="discovery-manifest-1",
        disposition=FetchDisposition.FETCH_AUTHORIZED,
        blocker=None,
        next_action="FETCH_SOURCE",
    )
    result = execute_source_request(ledger, request, facade, worker_id="worker-1")

    parsed = bronze_reference_to_raw_evidence_hash(result.adapter_result.bronze_relative_path)
    assert parsed == result.adapter_result.raw_evidence_hash


# ---------------------------------------------------------------------------
# drive_filing_artifact_silver_acceptance: carries a real DiscoveryDriveResult
# to Silver, mirroring discovery.drive_discovery_manifest's own per-candidate
# fault isolation (Ticket 29's real prod entry point wiring).
# ---------------------------------------------------------------------------


class _RowPolicy:
    """A SourceFamilyPolicy whose fetched bytes vary per source_url, so
    each candidate produces a distinct raw_evidence_hash/revision -- unlike
    the fixed-payload _Policy above, used where distinct content matters.
    """

    def fetch(self, source_url: str) -> bytes:
        return f"filing bytes for {source_url}".encode()

    def is_complete(self, payload: bytes) -> bool:
        return True


def _drive_real_discovery(
    ledger: AcquisitionLedger, tmp_path: Path, rows: list[dict]
):
    from edgar_warehouse.acquisition.discovery import build_discovery_manifest, drive_discovery_manifest
    from edgar_warehouse.infrastructure.object_storage import StorageLocation

    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    manifest = build_discovery_manifest(rows, business_date="2026-08-24")
    registry = {"filing_artifact": _RowPolicy()}
    return drive_discovery_manifest(
        ledger, bronze_root, registry, manifest, worker_id="worker-1", registry_version="v1"
    )


def _row(*, accession: str, cik: int, form: str) -> dict:
    return {
        "accession_number": accession,
        "cik": cik,
        "form": form,
        "filing_txt_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt",
    }


def test_drive_filing_artifact_silver_acceptance_carries_captured_candidates_to_silver(
    tmp_path: Path,
) -> None:
    from edgar_warehouse.acquisition.silver_acceptance import drive_filing_artifact_silver_acceptance

    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    rows = [
        _row(accession="0000320193-26-000001", cik=320193, form="4"),
        _row(accession="0000789019-26-000042", cik=789019, form="3"),
    ]
    result = _drive_real_discovery(ledger, tmp_path, rows)
    assert result.interval_complete

    silver_result = drive_filing_artifact_silver_acceptance(
        ledger, revisions, processing, finalizer, silver, result
    )

    assert silver_result.interval_complete
    assert len(silver_result.outcomes) == 2
    for outcome in silver_result.outcomes:
        assert outcome.error is None
        assert outcome.processing_decision is not None
        assert outcome.processing_decision.silver_outcome is SilverOutcome.PUBLISHED
        producer = outcome.processing_decision.expected_producers[0]
        raw_object = silver.get_raw_object(producer.verified_reference)
        assert raw_object is not None
        assert raw_object["accession_number"] == outcome.candidate.accession_number


def test_drive_filing_artifact_silver_acceptance_skips_out_of_scope_candidates(
    tmp_path: Path,
) -> None:
    from edgar_warehouse.acquisition.silver_acceptance import drive_filing_artifact_silver_acceptance

    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    rows = [
        _row(accession="0000320193-26-000001", cik=320193, form="4"),
        _row(accession="0000789019-26-000099", cik=789019, form="8-K"),  # out of scope
    ]
    result = _drive_real_discovery(ledger, tmp_path, rows)

    silver_result = drive_filing_artifact_silver_acceptance(
        ledger, revisions, processing, finalizer, silver, result
    )

    # Only the in-scope, CAPTURED candidate is carried forward.
    assert len(silver_result.outcomes) == 1
    assert silver_result.outcomes[0].candidate.accession_number == "0000320193-26-000001"


def test_drive_filing_artifact_silver_acceptance_records_per_candidate_error_without_aborting(
    tmp_path: Path,
) -> None:
    """PriorRevisionNotSettled from one blocked candidate must not prevent
    others from settling -- mirrors drive_discovery_manifest's own
    per-candidate fault isolation.
    """

    from edgar_warehouse.acquisition.processing import ExpectedProducerOutcome as _EPO
    from edgar_warehouse.acquisition.processing import ExpectedProducerSpec as _EPS
    from edgar_warehouse.acquisition.silver_acceptance import (
        FILING_ARTIFACT_PRODUCER_NAME,
        FILING_ARTIFACT_TARGET_TABLE,
        drive_filing_artifact_silver_acceptance,
    )

    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    logical_key = "320193/0000320193-26-000001/full-submission-text"

    # Seed a FAILED-and-blocking prior revision for this exact key, out of
    # band, before the real discovery drive ever sees a decision for it --
    # sealed and failed directly (not via finalize_filing_artifact_candidate,
    # whose real SilverDatabase write would legitimately succeed here and
    # settle VERIFIED, not the FAILED state this test needs to seed).
    seed_decision_id = _captured_decision(
        ledger, candidate_id="seed", logical_source_key=logical_key,
        artifact_reference="filing_artifact/seedhashseedhashseedhashseedhash",
    )
    seed_revision = revisions.materialize_from_capture(
        seed_decision_id,
        raw_evidence_hash="seedhashseedhashseedhashseedhash",
        canonical_source_hash="seedhashseedhashseedhashseedhash",
        domain_content_hash="seedhashseedhashseedhashseedhash",
        contract_version="v1", parser_version="v1", schema_version="v1", configuration_version="v1",
    )
    seeded = processing.seal_expected_producers(
        seed_revision.revision_id,
        expected_producers=(
            _EPS(FILING_ARTIFACT_PRODUCER_NAME, FILING_ARTIFACT_TARGET_TABLE, "seed-accession"),
        ),
    )
    finalizer.record_producer_outcome(
        seeded.processing_decision_id, FILING_ARTIFACT_PRODUCER_NAME,
        outcome=_EPO.FAILED, failure_detail="seeded failure",
    )

    rows = [
        _row(accession="0000320193-26-000001", cik=320193, form="4"),  # blocked key
        _row(accession="0000789019-26-000042", cik=789019, form="3"),  # unrelated key
    ]
    result = _drive_real_discovery(ledger, tmp_path, rows)
    assert result.interval_complete  # fetch/capture itself succeeds for both

    silver_result = drive_filing_artifact_silver_acceptance(
        ledger, revisions, processing, finalizer, silver, result
    )

    assert not silver_result.interval_complete
    by_accession = {o.candidate.accession_number: o for o in silver_result.outcomes}
    blocked = by_accession["0000320193-26-000001"]
    assert blocked.error is not None
    assert "cannot seal until it does" in blocked.error
    unrelated = by_accession["0000789019-26-000042"]
    assert unrelated.error is None
    assert unrelated.processing_decision.silver_outcome is SilverOutcome.PUBLISHED


def test_drive_filing_artifact_silver_acceptance_replay_is_idempotent_no_op(
    tmp_path: Path,
) -> None:
    """Ticket 29's own acceptance criterion, proven at unit-test level
    before it's proven live in prod: a no-op replay of the same interval
    changes nothing new.
    """

    from edgar_warehouse.acquisition.silver_acceptance import drive_filing_artifact_silver_acceptance

    ledger, revisions, processing, finalizer, silver = _harness(tmp_path)
    rows = [_row(accession="0000320193-26-000001", cik=320193, form="4")]

    first_drive = _drive_real_discovery(ledger, tmp_path, rows)
    first_silver = drive_filing_artifact_silver_acceptance(
        ledger, revisions, processing, finalizer, silver, first_drive
    )
    assert first_silver.interval_complete

    second_drive = _drive_real_discovery(ledger, tmp_path, rows)
    second_silver = drive_filing_artifact_silver_acceptance(
        ledger, revisions, processing, finalizer, silver, second_drive
    )

    assert second_silver.interval_complete
    assert (
        first_silver.outcomes[0].processing_decision.processing_decision_id
        == second_silver.outcomes[0].processing_decision.processing_decision_id
    )
    assert not second_drive.outcomes[0].network_fetched  # replay hit the cache, no re-fetch
