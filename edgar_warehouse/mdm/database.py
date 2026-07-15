"""SQLAlchemy models for the MDM relational layer."""
from __future__ import annotations

import hashlib
import os
import uuid
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
)
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class GUID(TypeDecorator):
    """Portable UUID/GUID type.

    PostgreSQL keeps native UUID columns; other dialects (e.g. SQLite in tests)
    fall back to fixed-length text GUIDs.
    """

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=False))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return str(value)


def _uuid_string() -> str:
    return str(uuid.uuid4())


def relationship_logical_id(rel_type_id: str, source_entity_id: str, target_entity_id: str) -> str:
    """Deterministic immutable logical relationship ID.

    Stable across re-derivation and generations: identical (rel_type,
    source, target) always yields the same ID, so backfills and reruns
    never mint a second logical ID for the same relationship.

    Uses md5 (not uuid.uuid5) so the value is byte-for-byte reproducible by
    the Postgres migration's SQL-only backfill (006_relationship_temporal_
    contract.sql), which has no uuid5/SHA-1 primitive available without an
    extra extension. A row backfilled by the migration and a row later
    written by this function for the same triple MUST resolve to the same
    relationship_id -- if the two algorithms diverged, every pre-migration
    relationship would silently get a second, mismatched logical ID the
    first time this code path touched it.
    """
    digest = hashlib.md5(
        f"{rel_type_id}:{source_entity_id}:{target_entity_id}".encode("utf-8")
    ).hexdigest()
    return f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _default_relationship_id(context) -> str:
    """Column default: auto-derive relationship_id from sibling columns on INSERT.

    Any code path that constructs ``MdmRelationshipInstance`` without
    explicitly setting ``relationship_id`` (e.g. direct ORM inserts outside
    ``graph.py``'s ``ensure_relationship``) still gets the correct
    deterministic logical ID rather than a NULL/missing value.
    """
    params = context.get_current_parameters()
    return relationship_logical_id(
        params["rel_type_id"], params["source_entity_id"], params["target_entity_id"]
    )


def get_engine(url: str | None = None) -> Engine:
    url = url or os.environ["MDM_DATABASE_URL"]
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("mssql"):
        kwargs["fast_executemany"] = True
    engine = create_engine(url, **kwargs)
    from edgar_warehouse.mdm.observability import install_mdm_sql_logging

    install_mdm_sql_logging(engine)
    return engine


def get_session(engine: Engine) -> Session:
    return Session(engine)


# ---------------------------------------------------------------------------
# REGISTRY TABLES
# ---------------------------------------------------------------------------

class MdmEntity(Base):
    __tablename__ = "mdm_entity"

    entity_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    entity_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_quarantined: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    resolution_method: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    valid_from: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    valid_to: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('company','adviser','person','security','fund','audit_firm')",
            name="ck_mdm_entity_type",
        ),
    )

    # Relationships
    source_refs: Mapped[list["MdmSourceRef"]] = relationship(
        "MdmSourceRef", back_populates="entity", cascade="all, delete-orphan"
    )
    attribute_stages: Mapped[list["MdmEntityAttributeStage"]] = relationship(
        "MdmEntityAttributeStage", back_populates="entity", cascade="all, delete-orphan"
    )
    change_logs: Mapped[list["MdmChangeLog"]] = relationship(
        "MdmChangeLog", back_populates="entity", cascade="all, delete-orphan"
    )


class MdmSourceRef(Base):
    __tablename__ = "mdm_source_ref"

    entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        primary_key=True,
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    source_priority: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    matched_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )

    entity: Mapped["MdmEntity"] = relationship("MdmEntity", back_populates="source_refs")


# ---------------------------------------------------------------------------
# DOMAIN GOLDEN RECORD TABLES
# ---------------------------------------------------------------------------

class MdmCompany(Base):
    __tablename__ = "mdm_company"

    entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        primary_key=True,
    )
    cik: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    ein: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sic_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sic_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state_of_incorporation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fiscal_year_end: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ticker: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_ticker: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_exchange: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tracking_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_company_entity_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        nullable=True,
    )
    valid_from: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    valid_to: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class MdmAdviser(Base):
    __tablename__ = "mdm_adviser"

    entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        primary_key=True,
    )
    cik: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    crd_number: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)
    sec_file_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    adviser_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hq_city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hq_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aum_total: Mapped[Optional[object]] = mapped_column(Numeric, nullable=True)
    fund_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    linked_company_entity_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        nullable=True,
    )
    valid_from: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    valid_to: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class MdmPerson(Base):
    __tablename__ = "mdm_person"

    entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        primary_key=True,
    )
    owner_cik: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    name_variants: Mapped[Optional[object]] = mapped_column(type_=JSON, nullable=True)
    primary_role: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role_titles: Mapped[Optional[object]] = mapped_column(type_=JSON, nullable=True)
    affiliated_company_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    valid_from: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    valid_to: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class MdmSecurity(Base):
    __tablename__ = "mdm_security"

    entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        primary_key=True,
    )
    issuer_entity_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        nullable=True,
    )
    canonical_title: Mapped[str] = mapped_column(Text, nullable=False)
    security_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # security_class: hybrid enum — equity/etf_fund/fixed_income/warrant/unknown_security
    # Populated by SecurityResolver (Form 4 path) and _ensure_security_by_cusip (13F path).
    security_class: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cusip: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    isin: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    valid_from: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    valid_to: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class MdmFund(Base):
    __tablename__ = "mdm_fund"

    entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        primary_key=True,
    )
    adviser_entity_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        nullable=True,
    )
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    fund_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jurisdiction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aum_amount: Mapped[Optional[object]] = mapped_column(Numeric, nullable=True)
    aum_as_of_date: Mapped[Optional[object]] = mapped_column(Date, nullable=True)
    valid_from: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    valid_to: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class MdmAuditFirm(Base):
    """Golden record for an independent audit firm (PCAOB-registered).

    Seeded once from migration 005_fundamentals_relationships.sql (Big 4 + Next 6).
    Additional firms can be added via seed_pcaob_registry.py (optional full registry).
    Entity type 'audit_firm' must be registered in mdm_entity_type_definition.
    """

    __tablename__ = "mdm_audit_firm"

    entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        primary_key=True,
    )
    firm_name: Mapped[str] = mapped_column(Text, nullable=False)
    # PCAOB registration number — authoritative identifier (AD-08)
    pcaob_firm_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    big4: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )


# ---------------------------------------------------------------------------
# RULES TABLES
# ---------------------------------------------------------------------------

class MdmSourcePriority(Base):
    __tablename__ = "mdm_source_priority"

    rule_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("entity_type", "source_system", name="uq_source_priority"),
    )


class MdmFieldSurvivorship(Base):
    __tablename__ = "mdm_field_survivorship"

    rule_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferred_source_order: Mapped[Optional[object]] = mapped_column(
        type_=JSON, nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "rule_type IN ('source_priority','most_recent','immutable','highest_source_rank','custom')",
            name="ck_field_survivorship_rule_type",
        ),
        UniqueConstraint("entity_type", "field_name", name="uq_field_survivorship"),
    )


class MdmMatchThreshold(Base):
    __tablename__ = "mdm_match_threshold"

    rule_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    match_method: Mapped[str] = mapped_column(Text, nullable=False)
    auto_merge_min: Mapped[float] = mapped_column(Float, nullable=False)
    review_min: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "match_method IN ('cik_exact','fuzzy_name','ml_splink')",
            name="ck_match_threshold_method",
        ),
        UniqueConstraint("entity_type", "match_method", name="uq_match_threshold"),
    )


class MdmNormalizationRule(Base):
    __tablename__ = "mdm_normalization_rule"

    rule_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    input_value: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_value: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "rule_type IN ('legal_suffix','title_alias','address_abbr','state_code','country_code')",
            name="ck_normalization_rule_type",
        ),
        UniqueConstraint("rule_type", "input_value", name="uq_normalization_rule"),
    )


# ---------------------------------------------------------------------------
# PIPELINE TABLES
# ---------------------------------------------------------------------------

class MdmEntityAttributeStage(Base):
    __tablename__ = "mdm_entity_attribute_stage"

    stage_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    field_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    global_priority: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_date: Mapped[Optional[object]] = mapped_column(Date, nullable=True)
    was_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    loaded_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("idx_attr_stage_entity_field", "entity_id", "field_name"),
        Index("idx_attr_stage_selected", "entity_id", "was_selected"),
    )

    entity: Mapped["MdmEntity"] = relationship(
        "MdmEntity", back_populates="attribute_stages"
    )


class MdmMatchReview(Base):
    __tablename__ = "mdm_match_review"

    review_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    entity_id_a: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    entity_id_b: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    match_evidence: Mapped[Optional[object]] = mapped_column(type_=JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    reviewed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','accepted','rejected','quarantined')",
            name="ck_match_review_status",
        ),
    )


class MdmChangeLog(Base):
    __tablename__ = "mdm_change_log"

    change_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    changed_fields: Mapped[Optional[object]] = mapped_column(type_=JSON, nullable=True)
    changed_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    exported_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "idx_change_log_pending",
            "exported_at",
            postgresql_where=text("exported_at IS NULL"),
        ),
    )

    entity: Mapped["MdmEntity"] = relationship(
        "MdmEntity", back_populates="change_logs"
    )


# ---------------------------------------------------------------------------
# GRAPH REGISTRY TABLES
# ---------------------------------------------------------------------------

class MdmEntityTypeDefinition(Base):
    __tablename__ = "mdm_entity_type_definition"

    entity_type: Mapped[str] = mapped_column(Text, primary_key=True)
    neo4j_label: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    domain_table: Mapped[str] = mapped_column(Text, nullable=False)
    api_path_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    primary_id_field: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )


class MdmRelationshipType(Base):
    __tablename__ = "mdm_relationship_type"

    rel_type_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    rel_type_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    source_node_type: Mapped[str] = mapped_column(
        Text,
        ForeignKey("mdm_entity_type_definition.entity_type"),
        nullable=False,
    )
    target_node_type: Mapped[str] = mapped_column(
        Text,
        ForeignKey("mdm_entity_type_definition.entity_type"),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    is_temporal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    dedup_key_fields: Mapped[Optional[object]] = mapped_column(type_=JSON, nullable=True)
    merge_strategy: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'extend_temporal'")
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "direction IN ('outbound','inbound','both')",
            name="ck_rel_type_direction",
        ),
        CheckConstraint(
            "merge_strategy IN ('extend_temporal','always_insert','replace')",
            name="ck_rel_type_merge_strategy",
        ),
    )

    property_defs: Mapped[list["MdmRelationshipPropertyDef"]] = relationship(
        "MdmRelationshipPropertyDef", back_populates="rel_type", cascade="all, delete-orphan"
    )
    source_mappings: Mapped[list["MdmRelationshipSourceMapping"]] = relationship(
        "MdmRelationshipSourceMapping", back_populates="rel_type", cascade="all, delete-orphan"
    )
    instances: Mapped[list["MdmRelationshipInstance"]] = relationship(
        "MdmRelationshipInstance", back_populates="rel_type", cascade="all, delete-orphan"
    )


class MdmRelationshipPropertyDef(Base):
    __tablename__ = "mdm_relationship_property_def"

    prop_def_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    rel_type_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_relationship_type.rel_type_id"),
        nullable=False,
    )
    property_name: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[str] = mapped_column(Text, nullable=False)
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    default_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "data_type IN ('text','float','date','boolean','integer')",
            name="ck_prop_def_data_type",
        ),
        UniqueConstraint("rel_type_id", "property_name", name="uq_prop_def"),
    )

    rel_type: Mapped["MdmRelationshipType"] = relationship(
        "MdmRelationshipType", back_populates="property_defs"
    )


class MdmRelationshipSourceMapping(Base):
    __tablename__ = "mdm_relationship_source_mapping"

    mapping_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    rel_type_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_relationship_type.rel_type_id"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_table: Mapped[str] = mapped_column(Text, nullable=False)
    source_entity_field: Mapped[str] = mapped_column(Text, nullable=False)
    target_entity_field: Mapped[str] = mapped_column(Text, nullable=False)
    source_entity_type: Mapped[str] = mapped_column(
        Text,
        ForeignKey("mdm_entity_type_definition.entity_type"),
        nullable=False,
    )
    target_entity_type: Mapped[str] = mapped_column(
        Text,
        ForeignKey("mdm_entity_type_definition.entity_type"),
        nullable=False,
    )
    property_mapping: Mapped[object] = mapped_column(type_=JSON, nullable=False)
    effective_from_field: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_to_field: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filter_condition: Mapped[Optional[object]] = mapped_column(type_=JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "rel_type_id",
            "source_system",
            "source_table",
            name="uq_rel_source_mapping",
        ),
    )

    rel_type: Mapped["MdmRelationshipType"] = relationship(
        "MdmRelationshipType", back_populates="source_mappings"
    )


class MdmRelationshipInstance(Base):
    """A relationship-version row.

    ``instance_id`` is this version's immutable ID (never reassigned).
    ``relationship_id`` is the immutable *logical* relationship ID shared by
    every version of the same (rel_type, source, target) triple -- it is
    deterministic (see ``relationship_logical_id``), not a separate lookup
    table, so backfill and reruns never mint a second logical ID for the
    same relationship.
    """

    __tablename__ = "mdm_relationship_instance"

    instance_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    relationship_id: Mapped[str] = mapped_column(
        GUID(), nullable=False, default=_default_relationship_id
    )
    rel_type_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_relationship_type.rel_type_id"),
        nullable=False,
    )
    source_entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    target_entity_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    properties: Mapped[Optional[object]] = mapped_column(type_=JSON, nullable=True)
    effective_from: Mapped[Optional[object]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[object]] = mapped_column(Date, nullable=True)
    valid_from_date: Mapped[Optional[object]] = mapped_column(Date, nullable=True)
    valid_to_date: Mapped[Optional[object]] = mapped_column(Date, nullable=True)
    date_provenance: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'unknown'")
    )
    relationship_kind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'direct'")
    )
    source_system: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_accession: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_evidence: Mapped[Optional[object]] = mapped_column(type_=JSON, nullable=True)
    superseded_by_version_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("mdm_relationship_instance.instance_id"),
        nullable=True,
    )
    quarantined: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    quarantine_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graph_synced_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, server_default=text("NOW()")
    )
    updated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, server_default=text("NOW()")
    )

    __table_args__ = (
        Index(
            "idx_rel_instance_dedup",
            "source_entity_id",
            "target_entity_id",
            "rel_type_id",
        ),
        Index(
            "idx_rel_instance_pending_sync",
            "graph_synced_at",
            postgresql_where=text("graph_synced_at IS NULL"),
        ),
        Index("idx_rel_instance_relationship_id", "relationship_id"),
        CheckConstraint(
            "valid_from_date IS NULL OR valid_to_date IS NULL OR valid_to_date > valid_from_date",
            name="ck_rel_instance_valid_interval",
        ),
        CheckConstraint(
            "date_provenance IN ('reported','filing_date_proxy','unknown')",
            name="ck_rel_instance_date_provenance",
        ),
        CheckConstraint(
            "relationship_kind IN ('direct','derived')",
            name="ck_rel_instance_relationship_kind",
        ),
    )

    rel_type: Mapped["MdmRelationshipType"] = relationship(
        "MdmRelationshipType", back_populates="instances"
    )


class MdmRelationshipSourcePriority(Base):
    """Per-relationship-type source priority for conflict tie-breaks.

    Lower ``priority`` wins (same convention as ``MdmSourcePriority`` /
    ``survivorship.py``'s "lowest-numbered is highest-authority" rule).
    Overlapping, differing-property versions of the same logical
    relationship are resolved by this table; a triple with no configured
    row for either side's source is quarantined rather than silently
    picking a winner.
    """

    __tablename__ = "mdm_relationship_source_priority"

    rule_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    rel_type_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_relationship_type.rel_type_id"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("rel_type_id", "source_system", name="uq_rel_source_priority"),
    )


class MdmRelationshipCoverage(Base):
    """One coverage record per (generation, relationship type) -- 07-02 (RCOV-01/02).

    ``status`` is exhaustive and mutually exclusive: every active
    ``MdmRelationshipType`` must have exactly one row per generation.
    ``populated`` means nonzero graph-verified edges; ``valid_zero`` means
    proven-zero-for-now but re-evaluated every generation (not a permanent
    exclusion); ``excluded`` means a permanent, evidenced source-coverage or
    capability gap. ``population_fingerprint`` is a deterministic hash of the
    exact evaluated population -- a changed fingerprint means the underlying
    evidence has moved and the row is stale until recomputed.
    """

    __tablename__ = "mdm_relationship_coverage"

    coverage_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    generation_id: Mapped[str] = mapped_column(Text, nullable=False)
    rel_type_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_relationship_type.rel_type_id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    expected_edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_query_version: Mapped[str] = mapped_column(Text, nullable=False)
    evaluated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    population_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    review_trigger: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("generation_id", "rel_type_id", name="uq_rel_coverage_generation_type"),
        CheckConstraint(
            "status IN ('populated','valid_zero','excluded')",
            name="ck_rel_coverage_status",
        ),
        CheckConstraint(
            "evidence_category IS NULL OR evidence_category IN "
            "('source_unavailable','capability_not_implemented','scoped_zero_overlap',"
            "'structural_api_limitation','root_caused_fix_deferred')",
            name="ck_rel_coverage_evidence_category",
        ),
    )


class MdmPublicationRequest(Base):
    """Transactional MDM -> graph publication outbox (07-03, RSYNC-01/03).

    Created in the SAME session/transaction as the relationship-changing
    write it accompanies (see publication.request_publication) -- a
    session.rollback() removes both the MDM changes and this request
    atomically. A separate coordinator claims (lease-based), builds,
    verifies, and activates generations through ``lifecycle_state``;
    writers never call Snowflake/Neo4j orchestration code directly.
    """

    __tablename__ = "mdm_publication_request"

    request_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    lifecycle_state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'mdm_committed'")
    )
    committed_watermark: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    claimed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    claimed_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    lease_expires_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_backfill: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    backfill_deadline: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    generation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_summary: Mapped[Optional[object]] = mapped_column(type_=JSON, nullable=True)
    activated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN ('mdm_committed','graph_pending','graph_building',"
            "'graph_verified','graph_active','failed')",
            name="ck_pub_request_lifecycle_state",
        ),
        Index("idx_pub_request_lifecycle_state", "lifecycle_state"),
    )


class MdmGraphGeneration(Base):
    """One requested graph generation build (07-04, RSYNC-04).

    Coalesces one or more ``MdmPublicationRequest`` rows (via their
    ``generation_id`` FK-by-value) behind a single frozen
    ``committed_watermark``. Partitions (``MdmGraphPartition``) fan out per
    node/relationship type against this watermark; fan-in verifies them and
    flips ``status`` to ``verified``, then (07-05's activation pointer)
    ``activated``.
    """

    __tablename__ = "mdm_graph_generation"

    generation_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'building'")
    )
    committed_watermark: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    rule_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    verified_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    activated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    failure_reasons: Mapped[Optional[object]] = mapped_column(type_=JSON, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('building','verified','activated','failed')",
            name="ck_graph_generation_status",
        ),
    )


class MdmGraphPartition(Base):
    """One immutable content-addressed partition within a generation (07-04, RSYNC-04).

    Content address = (kind, type_name, shard_index, mdm_watermark,
    rule_version, schema_version, input_fingerprint) -> ``content_hash``. A
    partition with a ``content_hash`` matching a prior ``built`` partition
    (from any generation) is reused (``status='reused'``,
    ``reused_from_partition_id`` set) instead of rebuilt.
    """

    __tablename__ = "mdm_graph_partition"

    partition_id: Mapped[str] = mapped_column(
        GUID(), primary_key=True, default=_uuid_string
    )
    generation_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("mdm_graph_generation.generation_id"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    type_name: Mapped[str] = mapped_column(Text, nullable=False)
    shard_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    shard_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    mdm_watermark: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    rule_version: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    stable_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    property_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    reused_from_partition_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("mdm_graph_partition.partition_id"),
        nullable=True,
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "generation_id", "kind", "type_name", "shard_index",
            name="uq_graph_partition_generation_shard",
        ),
        Index("idx_graph_partition_content_hash", "content_hash"),
        CheckConstraint("kind IN ('node','edge')", name="ck_graph_partition_kind"),
        CheckConstraint(
            "status IN ('pending','building','built','reused','failed')",
            name="ck_graph_partition_status",
        ),
    )
