"""Transactional MDM -> graph publication queue (07-03, RSYNC-01/03).

PostgreSQL MDM is the derivation/staging authority; graph publication is a
separate lifecycle. Relationship-changing workflows call
``request_publication`` inside their own session/transaction so an MDM
commit and its publication request are atomic (a rollback removes both). A
separate coordinator (CLI or scheduled job) claims eligible requests via
``claim_next_publication_request``, advances them through
``advance_publication_lifecycle``, and ``release_expired_claims`` recovers
requests whose lease expired without creating a duplicate/competing
generation attempt. ``compute_publication_freshness`` reports the
five-minute-warning/fifteen-minute-hard-alert SLO used by the dashboard.

No Snowflake/Neo4j orchestration logic lives here or is required of
writers -- this module is pure MDM/Postgres queue mechanics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmPublicationRequest

LIFECYCLE_STATES = (
    "mdm_committed",
    "graph_pending",
    "graph_building",
    "graph_verified",
    "graph_active",
    "failed",
)
CLAIMABLE_STATES = ("mdm_committed", "graph_pending", "graph_building")
PENDING_STATES = ("mdm_committed", "graph_pending", "graph_building", "graph_verified")

DEFAULT_LEASE_SECONDS = 300
WARNING_AGE_SECONDS = 300
HARD_ALERT_AGE_SECONDS = 900


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: Any) -> datetime:
    """SQLite (tests) returns naive datetimes for TIMESTAMP columns; Postgres
    returns tz-aware. Treat naive values as UTC so age math is correct on both."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def request_publication(
    session: Session,
    *,
    is_backfill: bool = False,
    backfill_deadline: Optional[datetime] = None,
    source_summary: Optional[dict[str, Any]] = None,
) -> MdmPublicationRequest:
    """Create a publication request in the CALLER's existing session/transaction.

    Must be invoked inside the same session as the relationship-changing
    write it accompanies. This function does not commit -- session.add()
    here participates in the caller's uncommitted transaction, so
    session.rollback() removes both the MDM changes and this request.
    """
    if is_backfill and backfill_deadline is None:
        raise ValueError("backfill_deadline is required when is_backfill=True")
    request = MdmPublicationRequest(
        lifecycle_state="mdm_committed",
        committed_watermark=_utcnow(),
        is_backfill=is_backfill,
        backfill_deadline=backfill_deadline,
        source_summary=source_summary,
    )
    session.add(request)
    session.flush()
    return request


def claim_next_publication_request(
    session: Session,
    *,
    owner: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> Optional[MdmPublicationRequest]:
    """Atomically claim one eligible request (unclaimed or with an expired lease).

    Concurrency safety: the UPDATE...WHERE below only succeeds (rowcount==1)
    if the row is still unclaimed/expired at the moment of the UPDATE. Two
    concurrent claimants racing for the same row see exactly one successful
    UPDATE -- correctness relies on the database's row-level locking during
    UPDATE (standard optimistic-claim pattern), not on ORM-level coordination.
    """
    now = _utcnow()
    candidate_ids = session.scalars(
        select(MdmPublicationRequest.request_id)
        .where(MdmPublicationRequest.lifecycle_state.in_(CLAIMABLE_STATES))
        .order_by(MdmPublicationRequest.committed_watermark)
    ).all()
    for request_id in candidate_ids:
        lease_expiry = now + timedelta(seconds=lease_seconds)
        # synchronize_session=False: this is a single-row conditional claim: the
        # DB evaluates the WHERE at the SQL level and rowcount tells us whether we
        # won the race. The default ORM "evaluate" sync strategy re-checks the
        # WHERE clause in Python against already-loaded attribute values, which
        # breaks on naive-vs-aware datetime comparisons (SQLite round-trips
        # naive datetimes); we don't need it since we reload via session.get()
        # (after expire_all()) instead of relying on in-memory sync.
        result = session.execute(
            update(MdmPublicationRequest)
            .where(
                MdmPublicationRequest.request_id == request_id,
                MdmPublicationRequest.lifecycle_state.in_(CLAIMABLE_STATES),
                (MdmPublicationRequest.claimed_by.is_(None))
                | (MdmPublicationRequest.lease_expires_at < now),
            )
            .values(
                claimed_by=owner,
                claimed_at=now,
                lease_expires_at=lease_expiry,
                lifecycle_state="graph_pending",
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 1:
            session.flush()
            session.expire_all()
            return session.get(MdmPublicationRequest, request_id)
    return None


def release_expired_claims(session: Session) -> int:
    """Reset expired leases back to mdm_committed (retryable), bump retry_count.

    Never creates a new request row -- the same request is retried in
    place, so no duplicate/competing generation activation is possible.
    """
    now = _utcnow()
    expired = list(
        session.scalars(
            select(MdmPublicationRequest).where(
                MdmPublicationRequest.lifecycle_state.in_(("graph_pending", "graph_building")),
                MdmPublicationRequest.lease_expires_at.is_not(None),
                MdmPublicationRequest.lease_expires_at < now,
            )
        )
    )
    for request in expired:
        request.lifecycle_state = "mdm_committed"
        request.claimed_by = None
        request.claimed_at = None
        request.lease_expires_at = None
        request.retry_count += 1
        request.updated_at = now
    session.flush()
    return len(expired)


def advance_publication_lifecycle(
    session: Session,
    request_id: str,
    new_state: str,
    *,
    error: Optional[str] = None,
    generation_id: Optional[str] = None,
) -> MdmPublicationRequest:
    if new_state not in LIFECYCLE_STATES:
        raise ValueError(f"Unknown lifecycle_state {new_state!r}; must be one of {LIFECYCLE_STATES}")
    request = session.get(MdmPublicationRequest, request_id)
    if request is None:
        raise KeyError(f"No mdm_publication_request with request_id={request_id}")
    request.lifecycle_state = new_state
    request.updated_at = _utcnow()
    if error is not None:
        request.last_error = error
    if generation_id is not None:
        request.generation_id = generation_id
    if new_state == "graph_active":
        request.activated_at = _utcnow()
    session.flush()
    return request


@dataclass(frozen=True)
class PublicationFreshnessStatus:
    """RSYNC-01/03 freshness/health contract.

    ``status``: "normal" (<5min), "warning" (>=5min), "hard_alert" (>=15min
    OR a declared backfill window's deadline has passed). A declared bounded
    backfill window (``is_backfill``) is exempt from the ordinary age
    thresholds while its deadline hasn't passed.
    """

    status: str
    oldest_pending_age_seconds: Optional[float]
    oldest_pending_request_id: Optional[str]
    is_backfill_exempt: bool
    backfill_deadline_expired: bool
    lifecycle_counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "oldest_pending_age_seconds": self.oldest_pending_age_seconds,
            "oldest_pending_request_id": self.oldest_pending_request_id,
            "is_backfill_exempt": self.is_backfill_exempt,
            "backfill_deadline_expired": self.backfill_deadline_expired,
            "lifecycle_counts": dict(self.lifecycle_counts),
        }


def compute_publication_freshness(
    session: Session, *, now: Optional[datetime] = None
) -> PublicationFreshnessStatus:
    now = now or _utcnow()
    lifecycle_counts: dict[str, int] = {state: 0 for state in LIFECYCLE_STATES}
    for state, count in session.execute(
        select(MdmPublicationRequest.lifecycle_state, func.count())
        .group_by(MdmPublicationRequest.lifecycle_state)
    ):
        lifecycle_counts[state] = int(count)

    pending = list(
        session.scalars(
            select(MdmPublicationRequest)
            .where(MdmPublicationRequest.lifecycle_state.in_(PENDING_STATES))
            .order_by(MdmPublicationRequest.committed_watermark)
        )
    )
    if not pending:
        return PublicationFreshnessStatus(
            status="normal",
            oldest_pending_age_seconds=None,
            oldest_pending_request_id=None,
            is_backfill_exempt=False,
            backfill_deadline_expired=False,
            lifecycle_counts=lifecycle_counts,
        )

    oldest = pending[0]
    age_seconds = (now - _as_aware(oldest.committed_watermark)).total_seconds()

    if oldest.is_backfill:
        deadline = _as_aware(oldest.backfill_deadline) if oldest.backfill_deadline else None
        if deadline is not None and now > deadline:
            return PublicationFreshnessStatus(
                status="hard_alert",
                oldest_pending_age_seconds=age_seconds,
                oldest_pending_request_id=oldest.request_id,
                is_backfill_exempt=False,
                backfill_deadline_expired=True,
                lifecycle_counts=lifecycle_counts,
            )
        return PublicationFreshnessStatus(
            status="normal",
            oldest_pending_age_seconds=age_seconds,
            oldest_pending_request_id=oldest.request_id,
            is_backfill_exempt=True,
            backfill_deadline_expired=False,
            lifecycle_counts=lifecycle_counts,
        )

    if age_seconds >= HARD_ALERT_AGE_SECONDS:
        status = "hard_alert"
    elif age_seconds >= WARNING_AGE_SECONDS:
        status = "warning"
    else:
        status = "normal"
    return PublicationFreshnessStatus(
        status=status,
        oldest_pending_age_seconds=age_seconds,
        oldest_pending_request_id=oldest.request_id,
        is_backfill_exempt=False,
        backfill_deadline_expired=False,
        lifecycle_counts=lifecycle_counts,
    )
