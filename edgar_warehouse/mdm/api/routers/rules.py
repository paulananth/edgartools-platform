"""Stewardship rules management — source priority, survivorship, thresholds, normalization.

All endpoints write directly to the rule tables. The MDMRuleEngine reloads rules
at pipeline startup, so changes here take effect on the next pipeline run."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db
from edgar_warehouse.mdm.api.deps import get_db
from edgar_warehouse.mdm.api.schemas.stewardship import (
    FieldSurvivorshipIn,
    FieldSurvivorshipPatch,
    MatchThresholdIn,
    MatchThresholdPatch,
    NormalizationIn,
    NormalizationPatch,
    SourcePriorityIn,
    SourcePriorityPatch,
)

router = APIRouter(prefix="/stewardship/rules", tags=["rules"])


# -- source-priority ---------------------------------------------------------

@router.get("/source-priority")
def list_source_priority(
    entity_type: Optional[str] = None, session: Session = Depends(get_db)
):
    q = select(db.MdmSourcePriority).where(db.MdmSourcePriority.is_active == True)
    if entity_type:
        q = q.where(db.MdmSourcePriority.entity_type == entity_type)
    return [
        {
            "rule_id": r.rule_id,
            "entity_type": r.entity_type,
            "source_system": r.source_system,
            "priority": r.priority,
            "description": r.description,
        }
        for r in session.scalars(q).all()
    ]


@router.post("/source-priority")
def add_source_priority(payload: SourcePriorityIn, session: Session = Depends(get_db)):
    row = db.MdmSourcePriority(
        entity_type=payload.entity_type,
        source_system=payload.source_system,
        priority=payload.priority,
        description=payload.description,
    )
    session.add(row)
    session.commit()
    return {"rule_id": row.rule_id}


@router.patch("/source-priority/{rule_id}")
def patch_source_priority(
    rule_id: str, payload: SourcePriorityPatch, session: Session = Depends(get_db)
):
    row = session.get(db.MdmSourcePriority, rule_id)
    if row is None:
        raise HTTPException(404, "rule not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    session.commit()
    return {"rule_id": rule_id}


# -- field-survivorship ------------------------------------------------------

@router.get("/field-survivorship")
def list_survivorship(
    entity_type: Optional[str] = None, session: Session = Depends(get_db)
):
    q = select(db.MdmFieldSurvivorship).where(db.MdmFieldSurvivorship.is_active == True)
    if entity_type:
        q = q.where(db.MdmFieldSurvivorship.entity_type == entity_type)
    return [
        {
            "rule_id": r.rule_id,
            "entity_type": r.entity_type,
            "field_name": r.field_name,
            "rule_type": r.rule_type,
            "source_system": r.source_system,
            "preferred_source_order": r.preferred_source_order,
            "notes": r.notes,
        }
        for r in session.scalars(q).all()
    ]


@router.post("/field-survivorship")
def add_survivorship(payload: FieldSurvivorshipIn, session: Session = Depends(get_db)):
    row = db.MdmFieldSurvivorship(
        entity_type=payload.entity_type,
        field_name=payload.field_name,
        rule_type=payload.rule_type,
        source_system=payload.source_system,
        preferred_source_order=payload.preferred_source_order,
        notes=payload.notes,
    )
    session.add(row)
    session.commit()
    return {"rule_id": row.rule_id}


@router.patch("/field-survivorship/{rule_id}")
def patch_survivorship(
    rule_id: str, payload: FieldSurvivorshipPatch, session: Session = Depends(get_db)
):
    row = session.get(db.MdmFieldSurvivorship, rule_id)
    if row is None:
        raise HTTPException(404, "rule not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    session.commit()
    return {"rule_id": rule_id}


# -- match-thresholds --------------------------------------------------------

@router.get("/match-thresholds")
def list_match_thresholds(session: Session = Depends(get_db)):
    rows = session.scalars(
        select(db.MdmMatchThreshold).where(db.MdmMatchThreshold.is_active == True)
    ).all()
    return [
        {
            "rule_id": r.rule_id,
            "entity_type": r.entity_type,
            "match_method": r.match_method,
            "auto_merge_min": r.auto_merge_min,
            "review_min": r.review_min,
        }
        for r in rows
    ]


@router.post("/match-thresholds")
def add_match_threshold(payload: MatchThresholdIn, session: Session = Depends(get_db)):
    row = db.MdmMatchThreshold(
        entity_type=payload.entity_type,
        match_method=payload.match_method,
        auto_merge_min=payload.auto_merge_min,
        review_min=payload.review_min,
    )
    session.add(row)
    session.commit()
    return {"rule_id": row.rule_id}


@router.patch("/match-thresholds/{rule_id}")
def patch_match_threshold(
    rule_id: str, payload: MatchThresholdPatch, session: Session = Depends(get_db)
):
    row = session.get(db.MdmMatchThreshold, rule_id)
    if row is None:
        raise HTTPException(404, "rule not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    session.commit()
    return {"rule_id": rule_id}


# -- normalization -----------------------------------------------------------

@router.get("/normalization")
def list_normalization(
    rule_type: Optional[str] = None, session: Session = Depends(get_db)
):
    q = select(db.MdmNormalizationRule).where(db.MdmNormalizationRule.is_active == True)
    if rule_type:
        q = q.where(db.MdmNormalizationRule.rule_type == rule_type)
    return [
        {
            "rule_id": r.rule_id,
            "rule_type": r.rule_type,
            "input_value": r.input_value,
            "canonical_value": r.canonical_value,
            "entity_type": r.entity_type,
        }
        for r in session.scalars(q).all()
    ]


@router.post("/normalization")
def add_normalization(payload: NormalizationIn, session: Session = Depends(get_db)):
    row = db.MdmNormalizationRule(
        rule_type=payload.rule_type,
        input_value=payload.input_value,
        canonical_value=payload.canonical_value,
        entity_type=payload.entity_type,
    )
    session.add(row)
    session.commit()
    return {"rule_id": row.rule_id}


@router.patch("/normalization/{rule_id}")
def patch_normalization(
    rule_id: str, payload: NormalizationPatch, session: Session = Depends(get_db)
):
    row = session.get(db.MdmNormalizationRule, rule_id)
    if row is None:
        raise HTTPException(404, "rule not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    session.commit()
    return {"rule_id": rule_id}


@router.delete("/normalization/{rule_id}")
def delete_normalization(rule_id: str, session: Session = Depends(get_db)):
    row = session.get(db.MdmNormalizationRule, rule_id)
    if row is None:
        raise HTTPException(404, "rule not found")
    session.delete(row)
    session.commit()
    return {"status": "deleted"}
