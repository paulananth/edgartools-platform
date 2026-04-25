"""Pydantic schemas for entity-shaped responses."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EntityOut(_Base):
    entity_id: str
    entity_type: str
    is_quarantined: bool
    resolution_method: Optional[str] = None
    confidence: Optional[float] = None
    valid_from: datetime
    valid_to: Optional[datetime] = None


class SourceRefOut(_Base):
    source_system: str
    source_id: str
    source_priority: int
    confidence: Optional[float] = None
    matched_at: datetime


class CompanyOut(_Base):
    entity_id: str
    cik: int
    canonical_name: str
    ein: Optional[str] = None
    sic_code: Optional[str] = None
    sic_description: Optional[str] = None
    state_of_incorporation: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    primary_ticker: Optional[str] = None
    primary_exchange: Optional[str] = None
    tracking_status: Optional[str] = None


class AdviserOut(_Base):
    entity_id: str
    cik: Optional[int] = None
    crd_number: Optional[str] = None
    sec_file_number: Optional[str] = None
    canonical_name: str
    adviser_type: Optional[str] = None
    hq_city: Optional[str] = None
    hq_state: Optional[str] = None
    aum_total: Optional[float] = None
    fund_count: Optional[int] = None
    linked_company_entity_id: Optional[str] = None


class PersonOut(_Base):
    entity_id: str
    owner_cik: Optional[int] = None
    canonical_name: str
    name_variants: Optional[list[str]] = None
    primary_role: Optional[str] = None
    role_titles: Optional[list[str]] = None
    affiliated_company_count: Optional[int] = None


class SecurityOut(_Base):
    entity_id: str
    issuer_entity_id: Optional[str] = None
    canonical_title: str
    security_type: Optional[str] = None
    cusip: Optional[str] = None
    isin: Optional[str] = None


class FundOut(_Base):
    entity_id: str
    adviser_entity_id: Optional[str] = None
    canonical_name: str
    fund_type: Optional[str] = None
    jurisdiction: Optional[str] = None
    aum_amount: Optional[float] = None
    aum_as_of_date: Optional[date] = None


class ResolveRequest(BaseModel):
    source_system: str
    source_id: str
    entity_type: str
    raw_attributes: dict[str, Any]


class ResolveResponse(BaseModel):
    entity_id: str
    confidence: Optional[float] = None
    resolution_method: Optional[str] = None
    is_quarantined: bool


class PageMeta(BaseModel):
    page: int
    limit: int
    total: int


class EntitiesPage(BaseModel):
    items: list[EntityOut]
    meta: PageMeta
