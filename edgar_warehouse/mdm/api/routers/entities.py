"""Entity-level endpoints (cross-domain registry)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.api.deps import get_db
from edgar_warehouse.mdm.api.schemas.entities import (
    EntitiesPage,
    EntityOut,
    PageMeta,
    ResolveRequest,
    ResolveResponse,
    SourceRefOut,
)

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("/{entity_id}", response_model=EntityOut)
def get_entity(entity_id: str, session: Session = Depends(get_db)) -> EntityOut:
    e = session.get(db.MdmEntity, entity_id)
    if e is None:
        raise HTTPException(404, "entity not found")
    return EntityOut.model_validate(e)


@router.get("/{entity_id}/sources", response_model=list[SourceRefOut])
def get_entity_sources(entity_id: str, session: Session = Depends(get_db)) -> list[SourceRefOut]:
    rows = session.scalars(
        select(db.MdmSourceRef).where(db.MdmSourceRef.entity_id == entity_id)
    ).all()
    return [SourceRefOut.model_validate(r) for r in rows]


@router.get("", response_model=EntitiesPage)
def list_entities(
    type: Optional[str] = Query(default=None, alias="type"),
    q: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    include_quarantined: bool = False,
    session: Session = Depends(get_db),
) -> EntitiesPage:
    base = select(db.MdmEntity)
    count_q = select(func.count(db.MdmEntity.entity_id))
    if type:
        base = base.where(db.MdmEntity.entity_type == type)
        count_q = count_q.where(db.MdmEntity.entity_type == type)
    if not include_quarantined:
        base = base.where(db.MdmEntity.is_quarantined.is_(False))
        count_q = count_q.where(db.MdmEntity.is_quarantined.is_(False))
    if q:
        # Search canonical_name on whichever domain table matches `type`. If
        # `type` is not given, only filter by source_id substring as a generic
        # fallback to keep this fast.
        domain_map = {
            "company": db.MdmCompany,
            "adviser": db.MdmAdviser,
            "person": db.MdmPerson,
            "security": db.MdmSecurity,
            "fund": db.MdmFund,
        }
        if type in domain_map:
            model = domain_map[type]
            field = model.canonical_title if type == "security" else model.canonical_name
            base = base.join(model, model.entity_id == db.MdmEntity.entity_id).where(
                field.ilike(f"%{q}%")
            )
            count_q = count_q.join(model, model.entity_id == db.MdmEntity.entity_id).where(
                field.ilike(f"%{q}%")
            )
        else:
            base = base.join(db.MdmSourceRef).where(db.MdmSourceRef.source_id.ilike(f"%{q}%"))
            count_q = count_q.join(db.MdmSourceRef).where(
                db.MdmSourceRef.source_id.ilike(f"%{q}%")
            )

    total = session.scalar(count_q) or 0
    items = session.scalars(base.offset((page - 1) * limit).limit(limit)).all()
    return EntitiesPage(
        items=[EntityOut.model_validate(i) for i in items],
        meta=PageMeta(page=page, limit=limit, total=total),
    )


@router.post("/resolve", response_model=ResolveResponse)
def resolve_entity(
    payload: ResolveRequest, session: Session = Depends(get_db)
) -> ResolveResponse:
    """Resolve a single source record. Looks up by source_system+source_id;
    returns the matched entity if any. Full resolution (creating + survivorship)
    is the pipeline's job — this endpoint is the read-side of the registry."""
    ref = session.scalar(
        select(db.MdmSourceRef).where(
            db.MdmSourceRef.source_system == payload.source_system,
            db.MdmSourceRef.source_id == payload.source_id,
        )
    )
    if ref is None:
        raise HTTPException(404, "source not yet resolved")
    e = session.get(db.MdmEntity, ref.entity_id)
    if e is None:
        raise HTTPException(404, "entity not found")
    return ResolveResponse(
        entity_id=e.entity_id,
        confidence=e.confidence,
        resolution_method=e.resolution_method,
        is_quarantined=e.is_quarantined,
    )
