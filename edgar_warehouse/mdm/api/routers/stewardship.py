"""Stewardship endpoints: curation queue + manual overrides + merges."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db, stewardship as sw
from edgar_warehouse.mdm.api.deps import get_db
from edgar_warehouse.mdm.api.schemas.stewardship import (
    AttributeStageRow,
    FieldOverrideRequest,
    MergeRequest,
    ReviewOut,
)

router = APIRouter(prefix="/stewardship", tags=["stewardship"])


@router.get("/reviews", response_model=list[ReviewOut])
def list_reviews(
    status: str = "pending",
    entity_type: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db),
) -> list[ReviewOut]:
    q = select(db.MdmMatchReview).where(db.MdmMatchReview.status == status)
    if entity_type:
        q = q.join(db.MdmEntity, db.MdmEntity.entity_id == db.MdmMatchReview.entity_id_a).where(
            db.MdmEntity.entity_type == entity_type
        )
    rows = session.scalars(q.limit(limit)).all()
    return [ReviewOut.model_validate(r) for r in rows]


@router.post("/reviews/{review_id}/accept")
def accept_review(
    review_id: str, reviewer: str = "api", session: Session = Depends(get_db)
):
    kept = sw.accept_review(session, review_id, reviewer)
    return {"kept_entity_id": kept}


@router.post("/reviews/{review_id}/reject")
def reject_review(
    review_id: str, reviewer: str = "api", session: Session = Depends(get_db)
):
    sw.reject_review(session, review_id, reviewer)
    return {"status": "rejected"}


@router.post("/entities/{entity_id}/quarantine")
def quarantine_entity(entity_id: str, session: Session = Depends(get_db)):
    sw.quarantine(session, entity_id)
    return {"status": "quarantined"}


@router.post("/entities/{entity_id}/unquarantine")
def unquarantine_entity(entity_id: str, session: Session = Depends(get_db)):
    sw.unquarantine(session, entity_id)
    return {"status": "active"}


@router.post("/entities/merge")
def merge_entities(payload: MergeRequest, session: Session = Depends(get_db)):
    sw.merge_entities(
        session,
        keep=payload.entity_id_keep,
        discard=payload.entity_id_discard,
        reason=payload.reason,
    )
    return {"status": "merged", "kept": payload.entity_id_keep}


@router.patch("/entities/{entity_id}")
def patch_entity(
    entity_id: str, payload: FieldOverrideRequest, session: Session = Depends(get_db)
):
    """Manual field override on a domain golden record. Looks up the domain
    table from the entity's type, sets the field, and writes a change log row."""
    e = session.get(db.MdmEntity, entity_id)
    if e is None:
        raise HTTPException(404, "entity not found")
    domain_map = {
        "company": db.MdmCompany,
        "adviser": db.MdmAdviser,
        "person": db.MdmPerson,
        "security": db.MdmSecurity,
        "fund": db.MdmFund,
    }
    model = domain_map.get(e.entity_type)
    if model is None:
        raise HTTPException(400, f"unsupported entity_type {e.entity_type}")
    row = session.get(model, entity_id)
    if row is None:
        raise HTTPException(404, "domain row not found")
    if not hasattr(row, payload.field):
        raise HTTPException(400, f"unknown field {payload.field}")
    setattr(row, payload.field, payload.value)
    session.add(
        db.MdmChangeLog(
            entity_id=entity_id,
            entity_type=e.entity_type,
            changed_fields={payload.field: payload.value, "reason": payload.reason},
        )
    )
    session.commit()
    return {"status": "patched"}


@router.get(
    "/entities/{entity_id}/attribute-stage",
    response_model=list[AttributeStageRow],
)
def attribute_stage(
    entity_id: str,
    field_name: Optional[str] = None,
    session: Session = Depends(get_db),
) -> list[AttributeStageRow]:
    q = select(db.MdmEntityAttributeStage).where(
        db.MdmEntityAttributeStage.entity_id == entity_id
    )
    if field_name:
        q = q.where(db.MdmEntityAttributeStage.field_name == field_name)
    rows = session.scalars(q).all()
    return [AttributeStageRow.model_validate(r) for r in rows]
