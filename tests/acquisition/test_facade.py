from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from edgar_warehouse.acquisition.facade import (
    CapturedArtifact,
    OrphanedBronzeCapture,
    SourceCaptureFailed,
    build_capture_facade,
)
from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    DecisionOwnerRole,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
    StaleFencingToken,
    execute_source_request,
)
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _ledger() -> AcquisitionLedger:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AcquisitionBase.metadata.create_all(engine)
    return AcquisitionLedger(engine)


class _FakePolicy:
    def __init__(self, payload: bytes, *, complete: bool = True) -> None:
        self.payload = payload
        self.complete = complete
        self.fetch_calls: list[str] = []

    def fetch(self, source_url: str) -> bytes:
        self.fetch_calls.append(source_url)
        return self.payload

    def is_complete(self, payload: bytes) -> bool:
        return self.complete


class _FailingPolicy:
    def fetch(self, source_url: str) -> bytes:
        raise RuntimeError("SEC request failed")

    def is_complete(self, payload: bytes) -> bool:
        return True


def _authorized_request(candidate_id: str, logical_source_key: str, source_url: str) -> FetchDecisionRequest:
    return FetchDecisionRequest(
        candidate_id=candidate_id,
        source_family="filing_artifact",
        logical_source_key=logical_source_key,
        source_url=source_url,
        cause=DecisionCause.OPERATOR_REQUEST,
        cause_reference="operator-backfill-1",
        disposition=FetchDisposition.FETCH_AUTHORIZED,
        blocker=None,
        next_action="FETCH_SOURCE",
        owner_role=DecisionOwnerRole.ACQUISITION_OPERATOR,
    )


def test_facade_captures_content_addressed_bronze_and_finalizes_ledger(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    payload = b"<XML>ownership document body</XML>"
    policy = _FakePolicy(payload)
    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-1"
    )

    result = execute_source_request(
        ledger,
        _authorized_request(
            "candidate-1",
            "0000320193/0000320193-26-000001/primary-document",
            "https://www.sec.gov/Archives/example.xml",
        ),
        facade,
        worker_id="worker-1",
    )

    assert isinstance(result.adapter_result, CapturedArtifact)
    artifact = result.adapter_result
    assert artifact.raw_evidence_hash == hashlib.sha256(payload).hexdigest()
    assert artifact.bronze_relative_path == f"filing_artifact/{artifact.raw_evidence_hash}"
    assert artifact.byte_size == len(payload)
    assert policy.fetch_calls == ["https://www.sec.gov/Archives/example.xml"]

    stored = (tmp_path / "bronze" / "filing_artifact" / artifact.raw_evidence_hash).read_bytes()
    assert stored == payload

    status = ledger.source_change_status(result.status.decision_id)
    assert status.fetch_state is FetchWorkState.CAPTURED


def test_facade_uses_only_the_fenced_decisions_own_source_url(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    policy = _FakePolicy(b"payload")
    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-1"
    )

    result = execute_source_request(
        ledger,
        _authorized_request(
            "candidate-url-check",
            "0000320193/accession/doc",
            "https://www.sec.gov/Archives/only-this-url.xml",
        ),
        facade,
        worker_id="worker-1",
    )

    assert result.status.source_url == "https://www.sec.gov/Archives/only-this-url.xml"
    assert policy.fetch_calls == ["https://www.sec.gov/Archives/only-this-url.xml"]


def test_identical_bytes_reuse_one_bronze_object_with_distinct_ledger_lineage(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    payload = b"identical bytes across two observations"
    policy = _FakePolicy(payload)
    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-1"
    )

    first = execute_source_request(
        ledger,
        _authorized_request(
            "candidate-a", "0000320193/accession-a/doc", "https://www.sec.gov/Archives/a.xml"
        ),
        facade,
        worker_id="worker-1",
    )
    second = execute_source_request(
        ledger,
        _authorized_request(
            "candidate-b", "0000320193/accession-b/doc", "https://www.sec.gov/Archives/b.xml"
        ),
        facade,
        worker_id="worker-1",
    )

    assert first.adapter_result.raw_evidence_hash == second.adapter_result.raw_evidence_hash
    assert first.adapter_result.bronze_relative_path == second.adapter_result.bronze_relative_path
    assert first.status.decision_id != second.status.decision_id

    bronze_dir = tmp_path / "bronze" / "filing_artifact"
    assert len(list(bronze_dir.iterdir())) == 1

    first_status = ledger.source_change_status(first.status.decision_id)
    second_status = ledger.source_change_status(second.status.decision_id)
    assert first_status.fetch_state is FetchWorkState.CAPTURED
    assert second_status.fetch_state is FetchWorkState.CAPTURED


class _FlakyOnCaptureLedger:
    """Wraps a real AcquisitionLedger; the first N CAPTURED finalize calls
    raise a transient-looking error before delegating to the real ledger.
    Every other method (including FAILED finalize calls) passes straight
    through -- this is what stands in for "the DB connection blipped right
    after the Bronze write succeeded" in the orphan-quarantine tests.
    """

    def __init__(self, real_ledger: AcquisitionLedger, fail_times: int) -> None:
        self._real = real_ledger
        self._fail_times = fail_times
        self.capture_finalize_attempts = 0

    def __getattr__(self, name):
        return getattr(self._real, name)

    def finalize_fetch(self, *args, **kwargs):
        if kwargs.get("final_state") is FetchWorkState.CAPTURED:
            self.capture_finalize_attempts += 1
            if self.capture_finalize_attempts <= self._fail_times:
                raise RuntimeError(
                    f"transient ledger error on attempt {self.capture_finalize_attempts}"
                )
        return self._real.finalize_fetch(*args, **kwargs)


def test_capture_finalize_survives_a_transient_ledger_failure_and_retries_to_captured(
    tmp_path,
) -> None:
    real_ledger = _ledger()
    flaky_ledger = _FlakyOnCaptureLedger(real_ledger, fail_times=1)
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    payload = b"payload that survives a flaky finalize"
    policy = _FakePolicy(payload)
    facade = build_capture_facade(
        flaky_ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-1"
    )

    result = execute_source_request(
        real_ledger,
        _authorized_request(
            "candidate-flaky-finalize",
            "0000320193/accession-flaky/doc",
            "https://www.sec.gov/Archives/flaky.xml",
        ),
        facade,
        worker_id="worker-1",
    )

    assert flaky_ledger.capture_finalize_attempts == 2
    assert isinstance(result.adapter_result, CapturedArtifact)
    status = real_ledger.source_change_status(result.status.decision_id)
    assert status.fetch_state is FetchWorkState.CAPTURED
    assert status.captured_artifact_reference == result.adapter_result.bronze_relative_path


def test_capture_finalize_exhausting_all_retries_raises_orphaned_bronze_capture(
    tmp_path,
) -> None:
    real_ledger = _ledger()
    flaky_ledger = _FlakyOnCaptureLedger(real_ledger, fail_times=99)
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    payload = b"payload that never finalizes"
    policy = _FakePolicy(payload)
    facade = build_capture_facade(
        flaky_ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-1"
    )

    with pytest.raises(OrphanedBronzeCapture) as excinfo:
        execute_source_request(
            real_ledger,
            _authorized_request(
                "candidate-orphaned",
                "0000320193/accession-orphaned/doc",
                "https://www.sec.gov/Archives/orphaned.xml",
            ),
            facade,
            worker_id="worker-1",
        )

    raised = excinfo.value
    expected_hash = hashlib.sha256(payload).hexdigest()
    assert raised.raw_evidence_hash == expected_hash
    assert raised.bronze_relative_path == f"filing_artifact/{expected_hash}"

    # The Bronze write genuinely happened and is verified on disk -- the
    # artifact is real, just unowned by any finalized decision.
    stored = (tmp_path / "bronze" / "filing_artifact" / expected_hash).read_bytes()
    assert stored == payload

    # Quarantined: the ledger was never told this succeeded (still LEASED,
    # not downgraded to FAILED -- that would be a lie about what happened),
    # so it stays open/unsettled rather than silently discarding real
    # evidence or masking it behind a false failure.
    status = real_ledger.source_change_status(raised.decision_id)
    assert status.fetch_state is FetchWorkState.LEASED
    assert status.captured_artifact_reference is None


def test_capture_finalize_does_not_retry_a_stale_fencing_token(tmp_path) -> None:
    """A stale fencing token means a NEWER attempt already owns this decision
    -- retrying a doomed finalize would just waste time and could mask the
    real (newer) outcome behind a misleading OrphanedBronzeCapture. It must
    fail fast, in one attempt, with the ledger's own StaleFencingToken.
    """
    real_ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    payload = b"payload racing a newer fenced attempt"
    policy = _FakePolicy(payload)
    facade = build_capture_facade(
        real_ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-stale"
    )

    request = _authorized_request(
        "candidate-stale-fence",
        "0000320193/accession-stale-fence/doc",
        "https://www.sec.gov/Archives/stale-fence.xml",
    )
    decision = real_ledger.create_fetch_decision(request)
    stale_lease = real_ledger.claim_fetch(
        decision.decision_id, worker_id="worker-stale", lease_seconds=1
    )
    # Snapshot the status while it's genuinely LEASED under this worker's
    # token -- this is what a real stale worker would be holding in memory
    # right before a newer attempt races ahead of it, not a status re-read
    # after the fact (which would already show CAPTURED and get rejected by
    # capture()'s own may_fetch guard for an unrelated reason).
    stale_status = real_ledger.source_change_status(decision.decision_id)

    # A newer worker reclaims (expires+reclaims the same lease slot) and
    # finalizes first, advancing the fencing token past the one the stale
    # worker above is still holding.
    fresh_lease = real_ledger.claim_fetch(
        decision.decision_id,
        worker_id="worker-fresh",
        lease_seconds=60,
        now=datetime.now(UTC) + timedelta(seconds=2),
    )
    real_ledger.finalize_fetch(
        decision.decision_id,
        worker_id="worker-fresh",
        fencing_token=fresh_lease.fencing_token,
        final_state=FetchWorkState.CAPTURED,
        artifact_reference="filing_artifact/already-owned-by-someone-else",
    )

    with pytest.raises(StaleFencingToken):
        facade(stale_status, stale_lease)

    # Not retried: the flaky-ledger-style attempt counter doesn't exist here
    # because this is the REAL ledger, so instead we assert the CAPTURED
    # state that "won" is still exactly the fresh worker's, untouched.
    final_status = real_ledger.source_change_status(decision.decision_id)
    assert final_status.captured_artifact_reference == "filing_artifact/already-owned-by-someone-else"


def test_fetch_failure_records_failure_detail_as_durable_fetch_attempt_evidence(
    tmp_path,
) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": _FailingPolicy()}, worker_id="worker-1"
    )
    request = _authorized_request(
        "candidate-failure-evidence",
        "0000320193/accession-failure/doc",
        "https://www.sec.gov/Archives/failure.xml",
    )
    decision_id = ledger.create_fetch_decision(request).decision_id

    with pytest.raises(RuntimeError):
        execute_source_request(ledger, request, facade, worker_id="worker-1")

    assert "SEC request failed" in (ledger.latest_transition_reason(decision_id) or "")


def test_incomplete_payload_finalizes_ledger_as_failed_and_raises(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    policy = _FakePolicy(b"", complete=False)
    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-1"
    )

    with pytest.raises(SourceCaptureFailed, match="incomplete source payload"):
        execute_source_request(
            ledger,
            _authorized_request(
                "candidate-incomplete",
                "0000320193/accession-c/doc",
                "https://www.sec.gov/Archives/c.xml",
            ),
            facade,
            worker_id="worker-1",
        )

    decision = ledger.create_fetch_decision(
        _authorized_request(
            "candidate-incomplete",
            "0000320193/accession-c/doc",
            "https://www.sec.gov/Archives/c.xml",
        )
    )
    assert decision.fetch_state is FetchWorkState.FAILED


def test_fetch_exception_finalizes_ledger_as_failed_and_propagates(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": _FailingPolicy()}, worker_id="worker-1"
    )

    with pytest.raises(RuntimeError, match="SEC request failed"):
        execute_source_request(
            ledger,
            _authorized_request(
                "candidate-failing",
                "0000320193/accession-d/doc",
                "https://www.sec.gov/Archives/d.xml",
            ),
            facade,
            worker_id="worker-1",
        )

    decision = ledger.create_fetch_decision(
        _authorized_request(
            "candidate-failing",
            "0000320193/accession-d/doc",
            "https://www.sec.gov/Archives/d.xml",
        )
    )
    assert decision.fetch_state is FetchWorkState.FAILED


def test_unknown_source_family_finalizes_ledger_as_failed_and_raises(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    facade = build_capture_facade(ledger, bronze_root, {}, worker_id="worker-1")

    with pytest.raises(SourceCaptureFailed, match="no Source Family Registry entry"):
        execute_source_request(
            ledger,
            _authorized_request(
                "candidate-unregistered",
                "0000320193/accession-e/doc",
                "https://www.sec.gov/Archives/e.xml",
            ),
            facade,
            worker_id="worker-1",
        )

    decision = ledger.create_fetch_decision(
        _authorized_request(
            "candidate-unregistered",
            "0000320193/accession-e/doc",
            "https://www.sec.gov/Archives/e.xml",
        )
    )
    assert decision.fetch_state is FetchWorkState.FAILED


def test_facade_rejects_lease_that_does_not_match_the_fenced_decision(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    policy = _FakePolicy(b"payload")
    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-1"
    )

    status = ledger.create_fetch_decision(
        _authorized_request(
            "candidate-mismatch",
            "0000320193/accession-f/doc",
            "https://www.sec.gov/Archives/f.xml",
        )
    )
    lease = ledger.claim_fetch(status.decision_id, worker_id="a-different-worker", lease_seconds=60)
    leased_status = ledger.source_change_status(status.decision_id)

    with pytest.raises(SourceCaptureFailed, match="does not match"):
        facade(leased_status, lease)
    assert policy.fetch_calls == []


def test_facade_rejects_a_status_that_is_not_in_a_fetchable_state(tmp_path) -> None:
    """Direct-call boundary check: a caller other than execute_source_request (e.g.
    a future retry path) could hand the Facade a matching lease against a status
    that is no longer LEASED -- the Facade must still refuse, not just rely on
    execute_source_request's own upstream guard."""
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    policy = _FakePolicy(b"payload")
    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-1"
    )

    status = ledger.create_fetch_decision(
        _authorized_request(
            "candidate-not-leased",
            "0000320193/accession-g/doc",
            "https://www.sec.gov/Archives/g.xml",
        )
    )
    lease = ledger.claim_fetch(status.decision_id, worker_id="worker-1", lease_seconds=60)
    ledger.finalize_fetch(
        status.decision_id,
        worker_id="worker-1",
        fencing_token=lease.fencing_token,
        final_state=FetchWorkState.FAILED,
    )
    stale_status = ledger.source_change_status(status.decision_id)

    with pytest.raises(SourceCaptureFailed, match="not in a fetchable state"):
        facade(stale_status, lease)
    assert policy.fetch_calls == []


def test_bronze_read_back_mismatch_finalizes_ledger_as_failed_and_raises(tmp_path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    policy = _FakePolicy(b"the real payload")
    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-1"
    )

    with patch(
        "edgar_warehouse.acquisition.facade.read_bytes", return_value=b"corrupted bytes"
    ):
        with pytest.raises(SourceCaptureFailed, match="read-back mismatch"):
            execute_source_request(
                ledger,
                _authorized_request(
                    "candidate-readback",
                    "0000320193/accession-h/doc",
                    "https://www.sec.gov/Archives/h.xml",
                ),
                facade,
                worker_id="worker-1",
            )

    decision = ledger.create_fetch_decision(
        _authorized_request(
            "candidate-readback",
            "0000320193/accession-h/doc",
            "https://www.sec.gov/Archives/h.xml",
        )
    )
    assert decision.fetch_state is FetchWorkState.FAILED
