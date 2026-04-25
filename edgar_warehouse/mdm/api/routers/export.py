"""Export endpoints — read pending changes and full snapshots."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.api.deps import get_db
from edgar_warehouse.mdm.export import DOMAIN_TO_TABLE, MDMExporter

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/changes")
def get_changes(
    since: Optional[datetime] = Query(default=None),
    entity_type: Optional[str] = None,
    limit: int = Query(default=500, ge=1, le=5000),
    session: Session = Depends(get_db),
):
    q = select(db.MdmChangeLog).where(db.MdmChangeLog.exported_at.is_(None))
    if since:
        q = q.where(db.MdmChangeLog.changed_at >= since)
    if entity_type:
        q = q.where(db.MdmChangeLog.entity_type == entity_type)
    rows = session.scalars(q.limit(limit)).all()
    return [
        {
            "change_id": r.change_id,
            "entity_id": r.entity_id,
            "entity_type": r.entity_type,
            "changed_fields": r.changed_fields,
            "changed_at": r.changed_at,
        }
        for r in rows
    ]


@router.get("/snapshot/{entity_type}")
def snapshot(
    entity_type: str,
    limit: int = Query(default=1000, ge=1, le=10000),
    session: Session = Depends(get_db),
):
    target = DOMAIN_TO_TABLE.get(entity_type)
    if target is None:
        raise HTTPException(400, f"unsupported entity_type {entity_type}")
    _pg, _sf, model = target
    rows = session.scalars(select(model).limit(limit)).all()
    return [MDMExporter._serialize(r) for r in rows]
