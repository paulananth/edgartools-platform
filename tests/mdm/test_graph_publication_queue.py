"""Tests for Phase 7 Plan 03: transactional MDM->graph publication queue
(RSYNC-01, RSYNC-03).

Uses a real SQLAlchemy session against in-memory SQLite (schema via
Base.metadata.create_all), matching the existing MDM test convention.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from edgar_warehouse.mdm.database import (
    Base,
    MdmEntity,
    MdmEntityTypeDefinition,
    MdmPublicationRequest,
    MdmRelationshipInstance,
    MdmRelationshipType,
)
from edgar_warehouse.mdm import publication


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine) -> Session:
    with Session(engine) as s:
        yield s


def _seed_minimal_relationship_type(session: Session) -> tuple[str, str, str]:
    session.add(MdmEntityTypeDefinition(
        entity_type="company", neo4j_label="Company", domain_table="mdm_company",
        api_path_prefix="/companies", primary_id_field="entity_id",
        display_name="Company", is_active=True,
    ))
    rt_id = str(uuid.uuid4())
    session.add(MdmRelationshipType(
        rel_type_id=rt_id, rel_type_name="HAS_PARENT_COMPANY",
        source_node_type="company", target_node_type="company",
        direction="outbound", is_temporal=True,
        merge_strategy="replace", is_active=True,
    ))
    a = str(uuid.uuid4())
    b = str(uuid.uuid4())
    session.add(MdmEntity(entity_id=a, entity_type="company"))
    session.add(MdmEntity(entity_id=b, entity_type="company"))
    session.commit()
    return rt_id, a, b


# ---------------------------------------------------------------------------
# Task 1: transactional atomicity, claim/lease, retry
# ---------------------------------------------------------------------------

class TestTransactionalAtomicity:
    def test_rollback_removes_both_relationship_change_and_publication_request(self, engine, session):
        rt_id, a, b = _seed_minimal_relationship_type(session)

        session.add(MdmRelationshipInstance(
            rel_type_id=rt_id, source_entity_id=a, target_entity_id=b,
        ))
        publication.request_publication(session)
        session.rollback()

        with Session(engine) as fresh:
            assert fresh.scalar(select(MdmRelationshipInstance)) is None
            assert fresh.scalar(select(MdmPublicationRequest)) is None

    def test_commit_persists_both_relationship_change_and_publication_request(self, engine, session):
        rt_id, a, b = _seed_minimal_relationship_type(session)

        session.add(MdmRelationshipInstance(
            rel_type_id=rt_id, source_entity_id=a, target_entity_id=b,
        ))
        request = publication.request_publication(session)
        session.commit()

        with Session(engine) as fresh:
            assert fresh.scalar(select(MdmRelationshipInstance)) is not None
            persisted = fresh.get(MdmPublicationRequest, request.request_id)
            assert persisted is not None
            assert persisted.lifecycle_state == "mdm_committed"

    def test_backfill_requires_deadline(self, session):
        with pytest.raises(ValueError):
            publication.request_publication(session, is_backfill=True)


class TestClaimAndLease:
    def test_claim_returns_none_when_queue_empty(self, session):
        assert publication.claim_next_publication_request(session, owner="worker-a") is None

    def test_single_claim_sets_owner_and_transitions_state(self, session):
        request = publication.request_publication(session)
        session.commit()

        claimed = publication.claim_next_publication_request(session, owner="worker-a")
        session.commit()

        assert claimed is not None
        assert claimed.request_id == request.request_id
        assert claimed.claimed_by == "worker-a"
        assert claimed.lifecycle_state == "graph_pending"
        assert claimed.lease_expires_at is not None

    def test_concurrent_claim_attempts_yield_one_owner(self, session):
        publication.request_publication(session)
        session.commit()

        first = publication.claim_next_publication_request(session, owner="worker-a")
        second = publication.claim_next_publication_request(session, owner="worker-b")

        assert first is not None
        assert second is None
        assert first.claimed_by == "worker-a"

    def test_claim_skips_already_leased_request_for_next_candidate(self, session):
        publication.request_publication(session)
        publication.request_publication(session)
        session.commit()

        first = publication.claim_next_publication_request(session, owner="worker-a")
        second = publication.claim_next_publication_request(session, owner="worker-b")

        assert first is not None
        assert second is not None
        assert first.request_id != second.request_id
        assert {first.claimed_by, second.claimed_by} == {"worker-a", "worker-b"}


class TestRetry:
    def test_expired_claim_is_retryable_without_duplicating_generation(self, session):
        publication.request_publication(session)
        session.commit()

        claimed = publication.claim_next_publication_request(session, owner="worker-a", lease_seconds=1)
        session.commit()
        request_id = claimed.request_id

        # Force the lease into the past (simulating an expired worker).
        claimed.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

        released = publication.release_expired_claims(session)
        session.commit()
        assert released == 1

        refreshed = session.get(MdmPublicationRequest, request_id)
        assert refreshed.lifecycle_state == "mdm_committed"
        assert refreshed.claimed_by is None
        assert refreshed.retry_count == 1

        # Total row count must stay 1 -- retry reuses the same request, never duplicates it.
        all_requests = list(session.scalars(select(MdmPublicationRequest)))
        assert len(all_requests) == 1

        # Retryable: a new claim attempt succeeds again on the same row.
        reclaimed = publication.claim_next_publication_request(session, owner="worker-b")
        assert reclaimed is not None
        assert reclaimed.request_id == request_id
        assert reclaimed.claimed_by == "worker-b"

    def test_release_expired_claims_ignores_unexpired_leases(self, session):
        publication.request_publication(session)
        session.commit()
        publication.claim_next_publication_request(session, owner="worker-a", lease_seconds=300)
        session.commit()

        released = publication.release_expired_claims(session)
        assert released == 0


class TestLifecycleAdvancement:
    def test_advance_to_graph_active_sets_activated_at(self, session):
        request = publication.request_publication(session)
        session.commit()

        publication.advance_publication_lifecycle(
            session, request.request_id, "graph_building"
        )
        advanced = publication.advance_publication_lifecycle(
            session, request.request_id, "graph_active", generation_id="gen-1"
        )
        assert advanced.lifecycle_state == "graph_active"
        assert advanced.generation_id == "gen-1"
        assert advanced.activated_at is not None

    def test_advance_rejects_unknown_state(self, session):
        request = publication.request_publication(session)
        session.commit()
        with pytest.raises(ValueError):
            publication.advance_publication_lifecycle(session, request.request_id, "not_a_real_state")

    def test_advance_unknown_request_id_raises(self, session):
        with pytest.raises(KeyError):
            publication.advance_publication_lifecycle(session, str(uuid.uuid4()), "failed")

    def test_advance_to_failed_records_error(self, session):
        request = publication.request_publication(session)
        session.commit()
        failed = publication.advance_publication_lifecycle(
            session, request.request_id, "failed", error="boom"
        )
        assert failed.lifecycle_state == "failed"
        assert failed.last_error == "boom"


# ---------------------------------------------------------------------------
# Task 2: freshness/health boundaries
# ---------------------------------------------------------------------------

class TestPublicationFreshness:
    def _make_request_with_age(self, session: Session, age_seconds: float, **kwargs) -> MdmPublicationRequest:
        request = publication.request_publication(session, **kwargs)
        request.committed_watermark = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        session.commit()
        return request

    def test_empty_queue_is_normal(self, session):
        status = publication.compute_publication_freshness(session)
        assert status.status == "normal"
        assert status.oldest_pending_age_seconds is None

    def test_4m59s_is_normal(self, session):
        self._make_request_with_age(session, 299)
        status = publication.compute_publication_freshness(session)
        assert status.status == "normal"

    def test_5m00s_is_warning(self, session):
        self._make_request_with_age(session, 300)
        status = publication.compute_publication_freshness(session)
        assert status.status == "warning"

    def test_15m00s_is_hard_alert(self, session):
        self._make_request_with_age(session, 900)
        status = publication.compute_publication_freshness(session)
        assert status.status == "hard_alert"

    def test_14m59s_is_still_warning_not_hard_alert(self, session):
        self._make_request_with_age(session, 899)
        status = publication.compute_publication_freshness(session)
        assert status.status == "warning"

    def test_graph_active_requests_do_not_count_as_pending(self, session):
        request = self._make_request_with_age(session, 10_000)
        publication.advance_publication_lifecycle(session, request.request_id, "graph_building")
        publication.advance_publication_lifecycle(session, request.request_id, "graph_active")
        status = publication.compute_publication_freshness(session)
        assert status.status == "normal"
        assert status.oldest_pending_age_seconds is None

    def test_backfill_window_exempt_before_deadline(self, session):
        deadline = datetime.now(timezone.utc) + timedelta(hours=1)
        self._make_request_with_age(
            session, 10_000, is_backfill=True, backfill_deadline=deadline
        )
        status = publication.compute_publication_freshness(session)
        assert status.status == "normal"
        assert status.is_backfill_exempt is True

    def test_backfill_window_hard_alert_after_deadline_passes(self, session):
        deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        self._make_request_with_age(
            session, 100, is_backfill=True, backfill_deadline=deadline
        )
        status = publication.compute_publication_freshness(session)
        assert status.status == "hard_alert"
        assert status.backfill_deadline_expired is True

    def test_lifecycle_counts_distinguish_states(self, session):
        r1 = publication.request_publication(session)
        session.commit()
        publication.advance_publication_lifecycle(session, r1.request_id, "graph_building")
        publication.advance_publication_lifecycle(session, r1.request_id, "graph_verified")
        publication.advance_publication_lifecycle(session, r1.request_id, "graph_active")

        r2 = publication.request_publication(session)
        session.commit()

        status = publication.compute_publication_freshness(session)
        assert status.lifecycle_counts["graph_active"] == 1
        assert status.lifecycle_counts["mdm_committed"] == 1
