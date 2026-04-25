"""Pydantic schemas for stewardship + rules management."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ReviewOut(_Base):
    review_id: str
    entity_id_a: str
    entity_id_b: str
    match_score: float
    status: str
    match_evidence: Optional[dict[str, Any]] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class MergeRequest(BaseModel):
    entity_id_keep: str
    entity_id_discard: str
    reason: str = ""


class FieldOverrideRequest(BaseModel):
    field: str
    value: Any
    reason: str


class SourcePriorityIn(BaseModel):
    entity_type: str
    source_system: str
    priority: int
    description: Optional[str] = None


class SourcePriorityPatch(BaseModel):
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class FieldSurvivorshipIn(BaseModel):
    entity_type: str
    field_name: str
    rule_type: str
    source_system: Optional[str] = None
    preferred_source_order: Optional[list[str]] = None
    notes: Optional[str] = None


class FieldSurvivorshipPatch(BaseModel):
    rule_type: Optional[str] = None
    source_system: Optional[str] = None
    preferred_source_order: Optional[list[str]] = None
    is_active: Optional[bool] = None


class MatchThresholdIn(BaseModel):
    entity_type: str
    match_method: str
    auto_merge_min: float
    review_min: float


class MatchThresholdPatch(BaseModel):
    auto_merge_min: Optional[float] = None
    review_min: Optional[float] = None
    is_active: Optional[bool] = None


class NormalizationIn(BaseModel):
    rule_type: str
    input_value: str
    canonical_value: str
    entity_type: Optional[str] = None


class NormalizationPatch(BaseModel):
    canonical_value: Optional[str] = None
    is_active: Optional[bool] = None


class AttributeStageRow(_Base):
    field_name: str
    source_system: str
    source_id: str
    field_value: Optional[str] = None
    global_priority: int
    effective_date: Optional[Any] = None
    was_selected: bool
