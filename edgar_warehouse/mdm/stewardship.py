"""Stewardship workflow: curation queue, quarantine, manual merge."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import (
    MdmChangeLog,
    MdmEntity,
    MdmMatchReview,
    MdmSourceRef,
)


@dataclass
class ReviewListItem:
    review_id: str
    entity_id_a: str
    entity_id_b: str
    match_score: float
    status: str
    created_at: datetime


def list_pending_reviews(
    session: Session, entity_type: Optional[str] = None, limit: int = 100
) -> list[ReviewListItem]:
    stmt = (
        select(MdmMatchReview, MdmEntity.entity_type)
        .join(MdmEntity, MdmEntity.entity_id == MdmMatchReview.entity_id_a)
        .where(MdmMatchReview.status == "pending")
    )
    if entity_type:
        stmt = stmt.where(MdmEntity.entity_type == entity_type)
    stmt = stmt.limit(limit)

    out: list[ReviewListItem] = []
    for row, _et in session.execute(stmt).all():
        out.append(ReviewListItem(
            review_id=row.review_id,
            entity_id_a=row.entity_id_a,
            entity_id_b=row.entity_id_b,
            match_score=row.match_score,
            status=row.status,
            created_at=row.created_at,
        ))
    return out


def accept_review(
    session: Session,
    review_id: str,
    reviewer: str,
    run_id: str | None = None,
) -> tuple[str, str]:
    """Accept a review and return the kept entity plus its mutation identity."""
    from edgar_warehouse.mdm.run_identity import bind_mdm_run_identity

    bound_run_id = bind_mdm_run_identity(run_id)
    review = session.get(MdmMatchReview, review_id)
    if review is None:
        raise KeyError(f"Review {review_id} not found")
    if review.status != "pending":
        raise ValueError(f"Review {review_id} already {review.status}")

    kept = review.entity_id_a
    merged = review.entity_id_b
    _merge_entities(
        session,
        keep=kept,
        discard=merged,
        reason=f"review={review_id}",
        run_id=bound_run_id,
    )
    review.status = "accepted"
    review.reviewed_by = reviewer
    review.reviewed_at = datetime.now(timezone.utc)
    session.commit()
    return kept, bound_run_id


def reject_review(session: Session, review_id: str, reviewer: str) -> None:
    review = session.get(MdmMatchReview, review_id)
    if review is None:
        raise KeyError(f"Review {review_id} not found")
    review.status = "rejected"
    review.reviewed_by = reviewer
    review.reviewed_at = datetime.now(timezone.utc)
    session.commit()


def quarantine(session: Session, entity_id: str, run_id: str | None = None) -> str:
    from edgar_warehouse.mdm.run_identity import bind_mdm_run_identity

    bound_run_id = bind_mdm_run_identity(run_id)
    session.execute(
        update(MdmEntity).where(MdmEntity.entity_id == entity_id).values(is_quarantined=True)
    )
    session.add(MdmChangeLog(
        entity_id=entity_id,
        entity_type=_lookup_entity_type(session, entity_id),
        changed_fields={"is_quarantined": True},
        run_id=bound_run_id,
    ))
    session.commit()
    return bound_run_id


def unquarantine(session: Session, entity_id: str, run_id: str | None = None) -> str:
    from edgar_warehouse.mdm.run_identity import bind_mdm_run_identity

    bound_run_id = bind_mdm_run_identity(run_id)
    session.execute(
        update(MdmEntity).where(MdmEntity.entity_id == entity_id).values(is_quarantined=False)
    )
    session.add(MdmChangeLog(
        entity_id=entity_id,
        entity_type=_lookup_entity_type(session, entity_id),
        changed_fields={"is_quarantined": False},
        run_id=bound_run_id,
    ))
    session.commit()
    return bound_run_id


def merge_entities(
    session: Session,
    keep: str,
    discard: str,
    reason: str = "",
    run_id: str | None = None,
) -> str:
    """Re-point every source_ref from discard -> keep, tombstone discard."""
    from edgar_warehouse.mdm.run_identity import bind_mdm_run_identity

    bound_run_id = bind_mdm_run_identity(run_id)
    _merge_entities(
        session,
        keep=keep,
        discard=discard,
        reason=reason,
        run_id=bound_run_id,
    )
    session.commit()
    return bound_run_id


def _merge_entities(
    session: Session,
    *,
    keep: str,
    discard: str,
    reason: str,
    run_id: str,
) -> None:
    session.execute(
        update(MdmSourceRef).where(MdmSourceRef.entity_id == discard).values(entity_id=keep)
    )
    # Tombstone the discarded entity via valid_to
    session.execute(
        update(MdmEntity)
        .where(MdmEntity.entity_id == discard)
        .values(valid_to=datetime.now(timezone.utc))
    )
    session.add(MdmChangeLog(
        entity_id=keep,
        entity_type=_lookup_entity_type(session, keep),
        changed_fields={"merged_from": discard, "reason": reason},
        run_id=run_id,
    ))


def _lookup_entity_type(session: Session, entity_id: str) -> str:
    e = session.get(MdmEntity, entity_id)
    return e.entity_type if e else "unknown"
