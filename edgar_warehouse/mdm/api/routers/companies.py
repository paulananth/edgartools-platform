"""Company domain endpoints."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.api.deps import get_db
from edgar_warehouse.mdm.api.schemas.entities import (
    AdviserOut,
    CompanyOut,
    PersonOut,
    SecurityOut,
)

router = APIRouter(prefix="/companies", tags=["companies"])


def _company_by_cik(session: Session, cik: int) -> db.MdmCompany:
    c = session.scalar(select(db.MdmCompany).where(db.MdmCompany.cik == cik))
    if c is None:
        raise HTTPException(404, "company not found")
    return c


@router.get("/{cik}", response_model=CompanyOut)
def get_company(cik: int, session: Session = Depends(get_db)) -> CompanyOut:
    return CompanyOut.model_validate(_company_by_cik(session, cik))


@router.get("/{cik}/insiders", response_model=list[PersonOut])
def get_insiders(
    cik: int,
    as_of: Optional[date] = Query(default=None),
    session: Session = Depends(get_db),
) -> list[PersonOut]:
    company = _company_by_cik(session, cik)
    rt = session.scalar(
        select(db.MdmRelationshipType).where(db.MdmRelationshipType.rel_type_name == "IS_INSIDER")
    )
    if rt is None:
        return []
    edges_q = select(db.MdmRelationshipInstance).where(
        db.MdmRelationshipInstance.rel_type_id == rt.rel_type_id,
        db.MdmRelationshipInstance.target_entity_id == company.entity_id,
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
    edges = session.scalars(edges_q).all()
    person_ids = [e.source_entity_id for e in edges]
    if not person_ids:
        return []
    persons = session.scalars(
        select(db.MdmPerson).where(db.MdmPerson.entity_id.in_(person_ids))
    ).all()
    return [PersonOut.model_validate(p) for p in persons]


@router.get("/{cik}/advisers", response_model=list[AdviserOut])
def get_advisers(cik: int, session: Session = Depends(get_db)) -> list[AdviserOut]:
    company = _company_by_cik(session, cik)
    rows = session.scalars(
        select(db.MdmAdviser).where(db.MdmAdviser.linked_company_entity_id == company.entity_id)
    ).all()
    return [AdviserOut.model_validate(r) for r in rows]


@router.get("/{cik}/securities", response_model=list[SecurityOut])
def get_securities(cik: int, session: Session = Depends(get_db)) -> list[SecurityOut]:
    company = _company_by_cik(session, cik)
    rows = session.scalars(
        select(db.MdmSecurity).where(db.MdmSecurity.issuer_entity_id == company.entity_id)
    ).all()
    return [SecurityOut.model_validate(r) for r in rows]
