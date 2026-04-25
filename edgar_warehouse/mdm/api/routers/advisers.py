"""Adviser domain endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.api.deps import get_db
from edgar_warehouse.mdm.api.schemas.entities import AdviserOut, CompanyOut, FundOut

router = APIRouter(prefix="/advisers", tags=["advisers"])


def _by_crd(session: Session, crd_number: str) -> db.MdmAdviser:
    a = session.scalar(select(db.MdmAdviser).where(db.MdmAdviser.crd_number == crd_number))
    if a is None:
        raise HTTPException(404, "adviser not found")
    return a


@router.get("/{crd_number}", response_model=AdviserOut)
def get_adviser(crd_number: str, session: Session = Depends(get_db)) -> AdviserOut:
    return AdviserOut.model_validate(_by_crd(session, crd_number))


@router.get("/{crd_number}/funds", response_model=list[FundOut])
def get_funds(crd_number: str, session: Session = Depends(get_db)) -> list[FundOut]:
    a = _by_crd(session, crd_number)
    rows = session.scalars(
        select(db.MdmFund).where(db.MdmFund.adviser_entity_id == a.entity_id)
    ).all()
    return [FundOut.model_validate(r) for r in rows]


@router.get("/{crd_number}/companies", response_model=list[CompanyOut])
def get_companies(crd_number: str, session: Session = Depends(get_db)) -> list[CompanyOut]:
    a = _by_crd(session, crd_number)
    if a.linked_company_entity_id is None:
        return []
    c = session.scalar(
        select(db.MdmCompany).where(db.MdmCompany.entity_id == a.linked_company_entity_id)
    )
    return [CompanyOut.model_validate(c)] if c else []
