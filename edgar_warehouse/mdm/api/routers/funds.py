"""Fund domain endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.api.deps import get_db
from edgar_warehouse.mdm.api.schemas.entities import AdviserOut, FundOut

router = APIRouter(prefix="/funds", tags=["funds"])


@router.get("/{entity_id}", response_model=FundOut)
def get_fund(entity_id: str, session: Session = Depends(get_db)) -> FundOut:
    f = session.get(db.MdmFund, entity_id)
    if f is None:
        raise HTTPException(404, "fund not found")
    return FundOut.model_validate(f)


@router.get("/{entity_id}/adviser", response_model=AdviserOut)
def get_fund_adviser(entity_id: str, session: Session = Depends(get_db)) -> AdviserOut:
    f = session.get(db.MdmFund, entity_id)
    if f is None or f.adviser_entity_id is None:
        raise HTTPException(404, "adviser not linked")
    a = session.get(db.MdmAdviser, f.adviser_entity_id)
    if a is None:
        raise HTTPException(404, "adviser not found")
    return AdviserOut.model_validate(a)
