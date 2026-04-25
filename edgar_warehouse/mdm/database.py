"""SQLAlchemy models for the MDM PostgreSQL layer."""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import (
    UUID,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


def get_engine(url: str | None = None) -> Engine:
    url = url or os.environ["MDM_DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True)


def get_session(engine: Engine) -> Session:
    return Session(engine)


# ---------------------------------------------------------------------------
# REGISTRY TABLES
# ---------------------------------------------------------------------------

class MdmEntity(Base):
    __tablename__ = "mdm_entity"

    entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
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
            "entity_type IN ('company','adviser','person','security','fund')",
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
        UUID(as_uuid=False),
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
        UUID(as_uuid=False),
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
    primary_ticker: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_exchange: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tracking_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    valid_from: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    valid_to: Mapped[Optional[object]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )


class MdmAdviser(Base):
    __tablename__ = "mdm_adviser"

    entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
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
        UUID(as_uuid=False),
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
        UUID(as_uuid=False),
        ForeignKey("mdm_entity.entity_id"),
        primary_key=True,
    )
    owner_cik: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    name_variants: Mapped[Optional[object]] = mapped_column(type_=JSONB, nullable=True)
    primary_role: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role_titles: Mapped[Optional[object]] = mapped_column(type_=JSONB, nullable=True)
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
        UUID(as_uuid=False),
        ForeignKey("mdm_entity.entity_id"),
        primary_key=True,
    )
    issuer_entity_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mdm_entity.entity_id"),
        nullable=True,
    )
    canonical_title: Mapped[str] = mapped_column(Text, nullable=False)
    security_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
        UUID(as_uuid=False),
        ForeignKey("mdm_entity.entity_id"),
        primary_key=True,
    )
    adviser_entity_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
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


# ---------------------------------------------------------------------------
# RULES TABLES
# ---------------------------------------------------------------------------

class MdmSourcePriority(Base):
    __tablename__ = "mdm_source_priority"

    rule_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
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
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferred_source_order: Mapped[Optional[object]] = mapped_column(
        type_=JSONB, nullable=True
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
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
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
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
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
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
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
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    entity_id_a: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    entity_id_b: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    match_evidence: Mapped[Optional[object]] = mapped_column(type_=JSONB, nullable=True)
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
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    changed_fields: Mapped[Optional[object]] = mapped_column(type_=JSONB, nullable=True)
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
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
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
    dedup_key_fields: Mapped[Optional[object]] = mapped_column(type_=JSONB, nullable=True)
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
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    rel_type_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
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
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    rel_type_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
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
    property_mapping: Mapped[object] = mapped_column(type_=JSONB, nullable=False)
    effective_from_field: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_to_field: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filter_condition: Mapped[Optional[object]] = mapped_column(type_=JSONB, nullable=True)
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
    __tablename__ = "mdm_relationship_instance"

    instance_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    rel_type_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mdm_relationship_type.rel_type_id"),
        nullable=False,
    )
    source_entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    target_entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("mdm_entity.entity_id"),
        nullable=False,
    )
    properties: Mapped[Optional[object]] = mapped_column(type_=JSONB, nullable=True)
    effective_from: Mapped[Optional[object]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[object]] = mapped_column(Date, nullable=True)
    source_system: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_accession: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    )

    rel_type: Mapped["MdmRelationshipType"] = relationship(
        "MdmRelationshipType", back_populates="instances"
    )
