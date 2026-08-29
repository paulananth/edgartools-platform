"""Ticket 28: due re-poll with If-None-Match / 304 linking."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from edgar_warehouse.acquisition.facade import build_capture_facade, execute_due_repoll
from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    DecisionOwnerRole,
    FetchDecisionRequest,
    FetchDisposition,
    execute_source_request,
)
from edgar_warehouse.acquisition.models import AcquisitionBase
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.infrastructure.sec_client import ConditionalSecResponse
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


def _ledger() -> AcquisitionLedger:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AcquisitionBase.metadata.create_all(engine)
    return AcquisitionLedger(engine)


class _FakePolicy:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.fetch_calls = 0

    def fetch(self, source_url: str) -> bytes:
        self.fetch_calls += 1
        return self.payload

    def is_complete(self, payload: bytes) -> bool:
        return bool(payload)


def _first_capture(ledger: AcquisitionLedger, bronze_root: StorageLocation, payload: bytes):
    policy = _FakePolicy(payload)
    facade = build_capture_facade(
        ledger, bronze_root, {"filing_artifact": policy}, worker_id="worker-1"
    )
    request = FetchDecisionRequest(
        candidate_id="candidate-original",
        source_family="filing_artifact",
        logical_source_key="logical/key-1",
        source_url="https://www.sec.gov/Archives/example.txt",
        cause=DecisionCause.OPERATOR_REQUEST,
        cause_reference="operator-1",
        disposition=FetchDisposition.FETCH_AUTHORIZED,
        blocker=None,
        next_action="FETCH_SOURCE",
        owner_role=DecisionOwnerRole.ACQUISITION_OPERATOR,
    )
    result = execute_source_request(
        ledger, request, facade, worker_id="worker-1"
    )
    return result.adapter_result, policy


def _bronze_objects(tmp_path: Path) -> set[str]:
    bronze = tmp_path / "bronze"
    if not bronze.exists():
        return set()
    return {str(path.relative_to(bronze)) for path in bronze.rglob("*") if path.is_file()}


def test_304_repoll_links_prior_artifact_and_writes_no_bronze(tmp_path: Path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    first_artifact, policy = _first_capture(ledger, bronze_root, b"payload-v1")

    # SourceFamilyPolicy.fetch() returns bytes only, so the original capture
    # has no ETag. One unconditional 200 due-repoll stores validators; the
    # 304 below then sends them. Ticket 28 does not widen the policy protocol.

    def _first_poll(*args, **kwargs):
        return ConditionalSecResponse(
            not_modified=False,
            content=b"payload-v1",
            etag="etag-v1",
            last_modified="Wed, 21 Oct 2015 07:28:00 GMT",
        )

    with patch(
        "edgar_warehouse.acquisition.facade.download_sec_conditionally",
        side_effect=_first_poll,
    ):
        execute_due_repoll(
            ledger,
            bronze_root,
            {"filing_artifact": policy},
            source_family="filing_artifact",
            logical_source_key="logical/key-1",
            source_url="https://www.sec.gov/Archives/example.txt",
            identity="edgartools-platform test@example.com",
            worker_id="worker-1",
        )
    objects_after_seed = _bronze_objects(tmp_path)
    seen_kwargs: dict[str, object] = {}

    def _not_modified(*args, **kwargs):
        seen_kwargs.update(kwargs)
        return ConditionalSecResponse(
            not_modified=True,
            content=b"",
            etag="etag-v1",
            last_modified="Wed, 21 Oct 2015 07:28:00 GMT",
        )

    with patch(
        "edgar_warehouse.acquisition.facade.download_sec_conditionally",
        side_effect=_not_modified,
    ):
        status = execute_due_repoll(
            ledger,
            bronze_root,
            {"filing_artifact": policy},
            source_family="filing_artifact",
            logical_source_key="logical/key-1",
            source_url="https://www.sec.gov/Archives/example.txt",
            identity="edgartools-platform test@example.com",
            worker_id="worker-1",
        )

    assert seen_kwargs.get("etag") == "etag-v1"
    assert status.cause is DecisionCause.DUE_POLICY
    assert status.fetch_state.value == "CAPTURED"
    assert status.captured_artifact_reference == first_artifact.bronze_relative_path
    assert status.decision_id != first_artifact.decision_id
    assert _bronze_objects(tmp_path) == objects_after_seed
    assert policy.fetch_calls == 1


def test_200_repoll_writes_a_new_bronze_artifact(tmp_path: Path) -> None:
    ledger = _ledger()
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    first_artifact, policy = _first_capture(ledger, bronze_root, b"payload-v1")

    def _conditional(*args, **kwargs):
        return ConditionalSecResponse(
            not_modified=False,
            content=b"payload-v2",
            etag="etag-v2",
            last_modified="Thu, 22 Oct 2015 07:28:00 GMT",
        )

    with patch(
        "edgar_warehouse.acquisition.facade.download_sec_conditionally",
        side_effect=_conditional,
    ):
        status = execute_due_repoll(
            ledger,
            bronze_root,
            {"filing_artifact": policy},
            source_family="filing_artifact",
            logical_source_key="logical/key-1",
            source_url="https://www.sec.gov/Archives/example.txt",
            identity="edgartools-platform test@example.com",
            worker_id="worker-1",
        )

    assert status.fetch_state.value == "CAPTURED"
    assert status.captured_artifact_reference != first_artifact.bronze_relative_path
    assert first_artifact.bronze_relative_path.split("/")[-1] in {
        path.split("/")[-1] for path in _bronze_objects(tmp_path)
    }
    latest = ledger.latest_verified_capture("filing_artifact", "logical/key-1")
    assert latest is not None
    assert latest.etag == "etag-v2"
    assert latest.captured_artifact_reference == status.captured_artifact_reference
