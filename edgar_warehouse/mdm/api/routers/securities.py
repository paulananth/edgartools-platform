"""Security domain endpoints."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.api.deps import get_db
from edgar_warehouse.mdm.api.schemas.entities import SecurityOut

router = APIRouter(prefix="/securities", tags=["securities"])


@router.get("/{entity_id}", response_model=SecurityOut)
def get_security(entity_id: str, session: Session = Depends(get_db)) -> SecurityOut:
    s = session.get(db.MdmSecurity, entity_id)
    if s is None:
        raise HTTPException(404, "security not found")
    return SecurityOut.model_validate(s)


@router.get("/{entity_id}/holders")
def get_holders(
    entity_id: str,
    as_of: Optional[date] = Query(default=None),
    session: Session = Depends(get_db),
):
    rt = session.scalar(
        select(db.MdmRelationshipType).where(db.MdmRelationshipType.rel_type_name == "HOLDS")
    )
    if rt is None:
        return []
    edges_q = select(db.MdmRelationshipInstance).where(
        db.MdmRelationshipInstance.rel_type_id == rt.rel_type_id,
        db.MdmRelationshipInstance.target_entity_id == entity_id,
        db.MdmRelationshipInstance.is_active == True,
    )
    if as_of is not None:
        edges_q = edges_q.where(
            (db.MdmRelationshipInstance.effective_from.is_(None))
            | (db.MdmRelationshipInstance.effective_from <= as_of)
        ).where(
            (db.MdmRelationshipInstance.effective_to.is_(None))
            | (db.MdmRelationshipInstance.effective_to > as_of)
        )
    return [
        {
            "person_entity_id": e.source_entity_id,
            "properties": e.properties,
            "effective_from": e.effective_from,
            "effective_to": e.effective_to,
        }
        for e in session.scalars(edges_q).all()
    ]
