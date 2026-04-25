"""Person domain endpoints."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.api.deps import get_db
from edgar_warehouse.mdm.api.schemas.entities import PersonOut

router = APIRouter(prefix="/persons", tags=["persons"])


def _person(session: Session, entity_id: str) -> db.MdmPerson:
    p = session.get(db.MdmPerson, entity_id)
    if p is None:
        raise HTTPException(404, "person not found")
    return p


@router.get("/search", response_model=list[PersonOut])
def search_persons(
    name: str,
    company_cik: Optional[int] = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> list[PersonOut]:
    q = select(db.MdmPerson).where(db.MdmPerson.canonical_name.ilike(f"%{name}%"))
    if company_cik is not None:
        # Filter by IS_INSIDER edge into the company with this CIK
        rt = session.scalar(
            select(db.MdmRelationshipType).where(
                db.MdmRelationshipType.rel_type_name == "IS_INSIDER"
            )
        )
        company = session.scalar(select(db.MdmCompany).where(db.MdmCompany.cik == company_cik))
        if rt is None or company is None:
            return []
        person_ids = session.scalars(
            select(db.MdmRelationshipInstance.source_entity_id).where(
                db.MdmRelationshipInstance.rel_type_id == rt.rel_type_id,
                db.MdmRelationshipInstance.target_entity_id == company.entity_id,
            )
        ).all()
        q = q.where(db.MdmPerson.entity_id.in_(person_ids))
    rows = session.scalars(q.limit(limit)).all()
    return [PersonOut.model_validate(r) for r in rows]


@router.get("/{entity_id}", response_model=PersonOut)
def get_person(entity_id: str, session: Session = Depends(get_db)) -> PersonOut:
    return PersonOut.model_validate(_person(session, entity_id))


@router.get("/{entity_id}/affiliations")
def get_affiliations(
    entity_id: str,
    as_of: Optional[date] = Query(default=None),
    session: Session = Depends(get_db),
):
    _person(session, entity_id)
    rt = session.scalar(
        select(db.MdmRelationshipType).where(db.MdmRelationshipType.rel_type_name == "IS_INSIDER")
    )
    if rt is None:
        return []
    edges_q = select(db.MdmRelationshipInstance).where(
        db.MdmRelationshipInstance.rel_type_id == rt.rel_type_id,
        db.MdmRelationshipInstance.source_entity_id == entity_id,
        db.MdmRelationshipInstance.is_active.is_(True),
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
            "company_entity_id": e.target_entity_id,
            "properties": e.properties,
            "effective_from": e.effective_from,
            "effective_to": e.effective_to,
        }
        for e in session.scalars(edges_q).all()
    ]


@router.get("/{entity_id}/holdings")
def get_holdings(
    entity_id: str,
    as_of: Optional[date] = Query(default=None),
    session: Session = Depends(get_db),
):
    _person(session, entity_id)
    rt = session.scalar(
        select(db.MdmRelationshipType).where(db.MdmRelationshipType.rel_type_name == "HOLDS")
    )
    if rt is None:
        return []
    edges_q = select(db.MdmRelationshipInstance).where(
        db.MdmRelationshipInstance.rel_type_id == rt.rel_type_id,
        db.MdmRelationshipInstance.source_entity_id == entity_id,
        db.MdmRelationshipInstance.is_active.is_(True),
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
            "security_entity_id": e.target_entity_id,
            "properties": e.properties,
            "effective_from": e.effective_from,
            "effective_to": e.effective_to,
        }
        for e in session.scalars(edges_q).all()
    ]
