"""Runtime migration helpers for the MDM relational store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import database as db


MDM_TABLES = [
    "mdm_entity",
    "mdm_source_ref",
    "mdm_company",
    "mdm_adviser",
    "mdm_person",
    "mdm_security",
    "mdm_fund",
    "mdm_source_priority",
    "mdm_field_survivorship",
    "mdm_match_threshold",
    "mdm_normalization_rule",
    "mdm_entity_attribute_stage",
    "mdm_match_review",
    "mdm_change_log",
    "mdm_entity_type_definition",
    "mdm_relationship_type",
    "mdm_relationship_property_def",
    "mdm_relationship_source_mapping",
    "mdm_relationship_instance",
]


_MSSQL_SCHEMA_STATEMENTS = [
    """
    IF OBJECT_ID('mdm_entity', 'U') IS NULL
    CREATE TABLE mdm_entity (
        entity_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_entity PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        entity_type NVARCHAR(32) NOT NULL,
        is_quarantined BIT NOT NULL DEFAULT 0,
        resolution_method NVARCHAR(255) NULL,
        confidence FLOAT NULL,
        valid_from DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        valid_to DATETIMEOFFSET NULL,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        version INT NOT NULL DEFAULT 1,
        CONSTRAINT ck_mdm_entity_type CHECK (entity_type IN ('company','adviser','person','security','fund'))
    )
    """,
    """
    IF OBJECT_ID('mdm_source_ref', 'U') IS NULL
    CREATE TABLE mdm_source_ref (
        entity_id NVARCHAR(36) NOT NULL REFERENCES mdm_entity(entity_id),
        source_system NVARCHAR(128) NOT NULL,
        source_id NVARCHAR(255) NOT NULL,
        source_priority INT NOT NULL,
        confidence FLOAT NULL,
        matched_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT pk_mdm_source_ref PRIMARY KEY (entity_id, source_system, source_id)
    )
    """,
    """
    IF OBJECT_ID('mdm_company', 'U') IS NULL
    CREATE TABLE mdm_company (
        entity_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_company PRIMARY KEY REFERENCES mdm_entity(entity_id),
        cik BIGINT NOT NULL CONSTRAINT uq_mdm_company_cik UNIQUE,
        canonical_name NVARCHAR(512) NOT NULL,
        ein NVARCHAR(64) NULL,
        sic_code NVARCHAR(32) NULL,
        sic_description NVARCHAR(512) NULL,
        state_of_incorporation NVARCHAR(64) NULL,
        fiscal_year_end NVARCHAR(16) NULL,
        primary_ticker NVARCHAR(64) NULL,
        primary_exchange NVARCHAR(128) NULL,
        tracking_status NVARCHAR(64) NULL,
        valid_from DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        valid_to DATETIMEOFFSET NULL
    )
    """,
    """
    IF OBJECT_ID('mdm_adviser', 'U') IS NULL
    CREATE TABLE mdm_adviser (
        entity_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_adviser PRIMARY KEY REFERENCES mdm_entity(entity_id),
        cik BIGINT NULL,
        crd_number NVARCHAR(64) NULL CONSTRAINT uq_mdm_adviser_crd UNIQUE,
        sec_file_number NVARCHAR(128) NULL,
        canonical_name NVARCHAR(512) NOT NULL,
        adviser_type NVARCHAR(128) NULL,
        hq_city NVARCHAR(255) NULL,
        hq_state NVARCHAR(64) NULL,
        aum_total DECIMAL(38, 6) NULL,
        fund_count INT NULL,
        linked_company_entity_id NVARCHAR(36) NULL REFERENCES mdm_entity(entity_id),
        valid_from DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        valid_to DATETIMEOFFSET NULL
    )
    """,
    """
    IF OBJECT_ID('mdm_person', 'U') IS NULL
    CREATE TABLE mdm_person (
        entity_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_person PRIMARY KEY REFERENCES mdm_entity(entity_id),
        owner_cik BIGINT NULL,
        canonical_name NVARCHAR(512) NOT NULL,
        name_variants NVARCHAR(MAX) NULL,
        primary_role NVARCHAR(255) NULL,
        role_titles NVARCHAR(MAX) NULL,
        affiliated_company_count INT NOT NULL DEFAULT 0,
        valid_from DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        valid_to DATETIMEOFFSET NULL
    )
    """,
    """
    IF OBJECT_ID('mdm_security', 'U') IS NULL
    CREATE TABLE mdm_security (
        entity_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_security PRIMARY KEY REFERENCES mdm_entity(entity_id),
        issuer_entity_id NVARCHAR(36) NULL REFERENCES mdm_entity(entity_id),
        canonical_title NVARCHAR(512) NOT NULL,
        security_type NVARCHAR(128) NULL,
        cusip NVARCHAR(64) NULL,
        isin NVARCHAR(64) NULL,
        valid_from DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        valid_to DATETIMEOFFSET NULL
    )
    """,
    """
    IF OBJECT_ID('mdm_fund', 'U') IS NULL
    CREATE TABLE mdm_fund (
        entity_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_fund PRIMARY KEY REFERENCES mdm_entity(entity_id),
        adviser_entity_id NVARCHAR(36) NULL REFERENCES mdm_entity(entity_id),
        canonical_name NVARCHAR(512) NOT NULL,
        fund_type NVARCHAR(128) NULL,
        jurisdiction NVARCHAR(128) NULL,
        aum_amount DECIMAL(38, 6) NULL,
        aum_as_of_date DATE NULL,
        valid_from DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        valid_to DATETIMEOFFSET NULL
    )
    """,
    """
    IF OBJECT_ID('mdm_source_priority', 'U') IS NULL
    CREATE TABLE mdm_source_priority (
        rule_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_source_priority PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        entity_type NVARCHAR(32) NOT NULL,
        source_system NVARCHAR(128) NOT NULL,
        priority INT NOT NULL,
        is_active BIT NOT NULL DEFAULT 1,
        description NVARCHAR(MAX) NULL,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT uq_source_priority UNIQUE (entity_type, source_system)
    )
    """,
    """
    IF OBJECT_ID('mdm_field_survivorship', 'U') IS NULL
    CREATE TABLE mdm_field_survivorship (
        rule_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_field_survivorship PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        entity_type NVARCHAR(32) NOT NULL,
        field_name NVARCHAR(128) NOT NULL,
        rule_type NVARCHAR(64) NOT NULL,
        source_system NVARCHAR(128) NULL,
        preferred_source_order NVARCHAR(MAX) NULL,
        notes NVARCHAR(MAX) NULL,
        is_active BIT NOT NULL DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT ck_field_survivorship_rule_type CHECK (rule_type IN ('source_priority','most_recent','immutable','highest_source_rank','custom')),
        CONSTRAINT uq_field_survivorship UNIQUE (entity_type, field_name)
    )
    """,
    """
    IF OBJECT_ID('mdm_match_threshold', 'U') IS NULL
    CREATE TABLE mdm_match_threshold (
        rule_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_match_threshold PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        entity_type NVARCHAR(32) NOT NULL,
        match_method NVARCHAR(64) NOT NULL,
        auto_merge_min FLOAT NOT NULL,
        review_min FLOAT NOT NULL,
        is_active BIT NOT NULL DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT ck_match_threshold_method CHECK (match_method IN ('cik_exact','fuzzy_name','ml_splink')),
        CONSTRAINT uq_match_threshold UNIQUE (entity_type, match_method)
    )
    """,
    """
    IF OBJECT_ID('mdm_normalization_rule', 'U') IS NULL
    CREATE TABLE mdm_normalization_rule (
        rule_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_normalization_rule PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        rule_type NVARCHAR(64) NOT NULL,
        input_value NVARCHAR(255) NOT NULL,
        canonical_value NVARCHAR(255) NOT NULL,
        entity_type NVARCHAR(32) NULL,
        is_active BIT NOT NULL DEFAULT 1,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT ck_normalization_rule_type CHECK (rule_type IN ('legal_suffix','title_alias','address_abbr','state_code','country_code')),
        CONSTRAINT uq_normalization_rule UNIQUE (rule_type, input_value)
    )
    """,
    """
    IF OBJECT_ID('mdm_entity_attribute_stage', 'U') IS NULL
    CREATE TABLE mdm_entity_attribute_stage (
        stage_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_entity_attribute_stage PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        entity_id NVARCHAR(36) NOT NULL REFERENCES mdm_entity(entity_id),
        source_system NVARCHAR(128) NOT NULL,
        source_id NVARCHAR(255) NOT NULL,
        field_name NVARCHAR(128) NOT NULL,
        field_value NVARCHAR(MAX) NULL,
        global_priority INT NOT NULL,
        effective_date DATE NULL,
        was_selected BIT NOT NULL DEFAULT 0,
        loaded_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME()
    )
    """,
    """
    IF OBJECT_ID('mdm_match_review', 'U') IS NULL
    CREATE TABLE mdm_match_review (
        review_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_match_review PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        entity_id_a NVARCHAR(36) NOT NULL REFERENCES mdm_entity(entity_id),
        entity_id_b NVARCHAR(36) NOT NULL REFERENCES mdm_entity(entity_id),
        match_score FLOAT NOT NULL,
        match_evidence NVARCHAR(MAX) NULL,
        status NVARCHAR(32) NOT NULL DEFAULT 'pending',
        reviewed_by NVARCHAR(255) NULL,
        reviewed_at DATETIMEOFFSET NULL,
        created_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT ck_match_review_status CHECK (status IN ('pending','accepted','rejected','quarantined'))
    )
    """,
    """
    IF OBJECT_ID('mdm_change_log', 'U') IS NULL
    CREATE TABLE mdm_change_log (
        change_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_change_log PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        entity_id NVARCHAR(36) NOT NULL REFERENCES mdm_entity(entity_id),
        entity_type NVARCHAR(32) NOT NULL,
        changed_fields NVARCHAR(MAX) NULL,
        changed_at DATETIMEOFFSET NOT NULL DEFAULT SYSUTCDATETIME(),
        exported_at DATETIMEOFFSET NULL
    )
    """,
    """
    IF OBJECT_ID('mdm_entity_type_definition', 'U') IS NULL
    CREATE TABLE mdm_entity_type_definition (
        entity_type NVARCHAR(32) NOT NULL CONSTRAINT pk_mdm_entity_type_definition PRIMARY KEY,
        neo4j_label NVARCHAR(128) NOT NULL CONSTRAINT uq_mdm_entity_type_neo4j_label UNIQUE,
        domain_table NVARCHAR(128) NOT NULL,
        api_path_prefix NVARCHAR(128) NOT NULL,
        primary_id_field NVARCHAR(128) NOT NULL,
        display_name NVARCHAR(255) NOT NULL,
        is_active BIT NOT NULL DEFAULT 1
    )
    """,
    """
    IF OBJECT_ID('mdm_relationship_type', 'U') IS NULL
    CREATE TABLE mdm_relationship_type (
        rel_type_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_relationship_type PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        rel_type_name NVARCHAR(128) NOT NULL CONSTRAINT uq_mdm_relationship_type_name UNIQUE,
        source_node_type NVARCHAR(32) NOT NULL REFERENCES mdm_entity_type_definition(entity_type),
        target_node_type NVARCHAR(32) NOT NULL REFERENCES mdm_entity_type_definition(entity_type),
        direction NVARCHAR(32) NOT NULL,
        is_temporal BIT NOT NULL DEFAULT 1,
        dedup_key_fields NVARCHAR(MAX) NULL,
        merge_strategy NVARCHAR(64) NOT NULL DEFAULT 'extend_temporal',
        description NVARCHAR(MAX) NULL,
        is_active BIT NOT NULL DEFAULT 1,
        created_at DATETIMEOFFSET NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT ck_rel_type_direction CHECK (direction IN ('outbound','inbound','both')),
        CONSTRAINT ck_rel_type_merge_strategy CHECK (merge_strategy IN ('extend_temporal','always_insert','replace'))
    )
    """,
    """
    IF OBJECT_ID('mdm_relationship_property_def', 'U') IS NULL
    CREATE TABLE mdm_relationship_property_def (
        prop_def_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_relationship_property_def PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        rel_type_id NVARCHAR(36) NOT NULL REFERENCES mdm_relationship_type(rel_type_id),
        property_name NVARCHAR(128) NOT NULL,
        data_type NVARCHAR(32) NOT NULL,
        is_required BIT NOT NULL DEFAULT 0,
        default_value NVARCHAR(255) NULL,
        description NVARCHAR(MAX) NULL,
        CONSTRAINT ck_prop_def_data_type CHECK (data_type IN ('text','float','date','boolean','integer')),
        CONSTRAINT uq_prop_def UNIQUE (rel_type_id, property_name)
    )
    """,
    """
    IF OBJECT_ID('mdm_relationship_source_mapping', 'U') IS NULL
    CREATE TABLE mdm_relationship_source_mapping (
        mapping_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_relationship_source_mapping PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        rel_type_id NVARCHAR(36) NOT NULL REFERENCES mdm_relationship_type(rel_type_id),
        source_system NVARCHAR(128) NOT NULL,
        source_table NVARCHAR(128) NOT NULL,
        source_entity_field NVARCHAR(128) NOT NULL,
        target_entity_field NVARCHAR(128) NOT NULL,
        source_entity_type NVARCHAR(32) NOT NULL REFERENCES mdm_entity_type_definition(entity_type),
        target_entity_type NVARCHAR(32) NOT NULL REFERENCES mdm_entity_type_definition(entity_type),
        property_mapping NVARCHAR(MAX) NOT NULL,
        effective_from_field NVARCHAR(128) NULL,
        effective_to_field NVARCHAR(128) NULL,
        filter_condition NVARCHAR(MAX) NULL,
        is_active BIT NOT NULL DEFAULT 1,
        description NVARCHAR(MAX) NULL,
        CONSTRAINT uq_rel_source_mapping UNIQUE (rel_type_id, source_system, source_table)
    )
    """,
    """
    IF OBJECT_ID('mdm_relationship_instance', 'U') IS NULL
    CREATE TABLE mdm_relationship_instance (
        instance_id NVARCHAR(36) NOT NULL CONSTRAINT pk_mdm_relationship_instance PRIMARY KEY DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID())),
        rel_type_id NVARCHAR(36) NOT NULL REFERENCES mdm_relationship_type(rel_type_id),
        source_entity_id NVARCHAR(36) NOT NULL REFERENCES mdm_entity(entity_id),
        target_entity_id NVARCHAR(36) NOT NULL REFERENCES mdm_entity(entity_id),
        properties NVARCHAR(MAX) NULL,
        effective_from DATE NULL,
        effective_to DATE NULL,
        source_system NVARCHAR(128) NULL,
        source_accession NVARCHAR(255) NULL,
        graph_synced_at DATETIMEOFFSET NULL,
        is_active BIT NOT NULL DEFAULT 1,
        created_at DATETIMEOFFSET NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIMEOFFSET NULL DEFAULT SYSUTCDATETIME()
    )
    """,
    "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_attr_stage_entity_field') CREATE INDEX idx_attr_stage_entity_field ON mdm_entity_attribute_stage(entity_id, field_name)",
    "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_attr_stage_selected') CREATE INDEX idx_attr_stage_selected ON mdm_entity_attribute_stage(entity_id, was_selected)",
    "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_change_log_pending') CREATE INDEX idx_change_log_pending ON mdm_change_log(exported_at) WHERE exported_at IS NULL",
    "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_rel_instance_dedup') CREATE INDEX idx_rel_instance_dedup ON mdm_relationship_instance(source_entity_id, target_entity_id, rel_type_id)",
    "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_rel_instance_pending_sync') CREATE INDEX idx_rel_instance_pending_sync ON mdm_relationship_instance(graph_synced_at) WHERE graph_synced_at IS NULL",
    "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'idx_mdm_company_tracking_status') CREATE INDEX idx_mdm_company_tracking_status ON mdm_company(tracking_status)",
]


def migrate(engine: Engine, seed: bool = True) -> dict[str, Any]:
    """Apply schema and seed data for the current database dialect."""
    dialect = engine.dialect.name
    if dialect in {"mssql", "pyodbc"}:
        with engine.begin() as conn:
            for statement in _MSSQL_SCHEMA_STATEMENTS:
                conn.execute(text(statement))
    else:
        _apply_sql_file(engine, "001_initial_schema.sql")
        _apply_sql_file(engine, "003_tracking_status_index.sql")

    if seed:
        with Session(engine) as session:
            seed_defaults(session)
            session.commit()
    return {"dialect": dialect, "seeded": seed, "tables": count_tables(engine)}


def check_connectivity(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    return {
        "dialect": engine.dialect.name,
        "connected": True,
        "missing_tables": [table for table in MDM_TABLES if table not in existing],
    }


def count_tables(engine: Engine) -> dict[str, int | None]:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    counts: dict[str, int | None] = {}
    with engine.connect() as conn:
        for table in MDM_TABLES:
            if table not in existing:
                counts[table] = None
                continue
            counts[table] = int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
    return counts


def seed_defaults(session: Session) -> None:
    _seed_entity_types(session)
    _seed_source_priorities(session)
    _seed_field_rules(session)
    _seed_match_thresholds(session)
    _seed_normalization_rules(session)
    _seed_relationship_types(session)
    _seed_relationship_properties(session)
    _seed_relationship_mappings(session)


def _apply_sql_file(engine: Engine, filename: str) -> None:
    path = Path(__file__).with_name(filename)
    sql = path.read_text(encoding="utf-8")
    statements = [statement.strip() for statement in _split_sql(sql) if statement.strip()]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def _split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "'" and (index + 1 >= len(sql) or sql[index + 1] != "'"):
            in_single = not in_single
        if char == ";" and not in_single:
            statements.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    if current:
        statements.append("".join(current))
    return statements


def _first(session: Session, model: type, **criteria: Any):
    return session.scalar(select(model).filter_by(**criteria))


def _add_if_missing(session: Session, model: type, criteria: dict[str, Any], values: dict[str, Any]) -> Any:
    row = _first(session, model, **criteria)
    if row is not None:
        return row
    row = model(**criteria, **values)
    session.add(row)
    session.flush()
    return row


def _seed_entity_types(session: Session) -> None:
    rows = [
        ("company", "Company", "mdm_company", "/companies", "cik", "Company"),
        ("adviser", "Adviser", "mdm_adviser", "/advisers", "crd_number", "Investment Adviser"),
        ("person", "Person", "mdm_person", "/persons", "entity_id", "Person"),
        ("security", "Security", "mdm_security", "/securities", "entity_id", "Security"),
        ("fund", "Fund", "mdm_fund", "/funds", "entity_id", "Private Fund"),
    ]
    for entity_type, label, table, path, primary_id, display_name in rows:
        _add_if_missing(
            session,
            db.MdmEntityTypeDefinition,
            {"entity_type": entity_type},
            {
                "neo4j_label": label,
                "domain_table": table,
                "api_path_prefix": path,
                "primary_id_field": primary_id,
                "display_name": display_name,
            },
        )


def _seed_source_priorities(session: Session) -> None:
    rows = [
        ("all", "edgar_cik", 1, "SEC CIK submission data"),
        ("all", "adv_filing", 2, "Form ADV filing data"),
        ("all", "ownership_filing", 3, "Form 3/4/5 derived data"),
        ("all", "derived", 4, "Computed or inferred values"),
    ]
    for entity_type, source_system, priority, description in rows:
        _add_if_missing(
            session,
            db.MdmSourcePriority,
            {"entity_type": entity_type, "source_system": source_system},
            {"priority": priority, "description": description},
        )


def _seed_field_rules(session: Session) -> None:
    rows = [
        ("company", "canonical_name", "source_priority", None, None),
        ("company", "ein", "immutable", "edgar_cik", None),
        ("company", "sic_code", "immutable", "edgar_cik", None),
        ("company", "sic_description", "immutable", "edgar_cik", None),
        ("company", "primary_ticker", "highest_source_rank", None, None),
        ("adviser", "canonical_name", "source_priority", None, ["adv_filing", "edgar_cik"]),
        ("adviser", "aum_total", "most_recent", "adv_filing", None),
        ("person", "canonical_name", "source_priority", None, None),
        ("person", "primary_role", "most_recent", None, None),
    ]
    for entity_type, field_name, rule_type, source_system, preferred_order in rows:
        _add_if_missing(
            session,
            db.MdmFieldSurvivorship,
            {"entity_type": entity_type, "field_name": field_name},
            {
                "rule_type": rule_type,
                "source_system": source_system,
                "preferred_source_order": preferred_order,
            },
        )


def _seed_match_thresholds(session: Session) -> None:
    rows = [
        ("person", "cik_exact", 1.00, 1.00),
        ("person", "fuzzy_name", 0.92, 0.80),
        ("person", "ml_splink", 0.95, 0.75),
        ("company", "fuzzy_name", 0.95, 0.85),
        ("adviser", "fuzzy_name", 0.92, 0.80),
    ]
    for entity_type, method, auto_merge, review in rows:
        _add_if_missing(
            session,
            db.MdmMatchThreshold,
            {"entity_type": entity_type, "match_method": method},
            {"auto_merge_min": auto_merge, "review_min": review},
        )


def _seed_normalization_rules(session: Session) -> None:
    rows = [
        ("legal_suffix", "inc", ""),
        ("legal_suffix", "incorporated", ""),
        ("legal_suffix", "llc", ""),
        ("legal_suffix", "corp", ""),
        ("legal_suffix", "corporation", ""),
        ("legal_suffix", "ltd", ""),
        ("legal_suffix", "limited", ""),
        ("legal_suffix", "trust", ""),
        ("legal_suffix", "fund", ""),
        ("legal_suffix", "group", ""),
        ("title_alias", "CHIEF EXECUTIVE OFFICER", "CEO"),
        ("title_alias", "CEO", "CEO"),
        ("title_alias", "CHIEF FINANCIAL OFFICER", "CFO"),
        ("title_alias", "CFO", "CFO"),
        ("title_alias", "DIRECTOR", "Director"),
        ("address_abbr", "ST", "Street"),
        ("address_abbr", "AVE", "Avenue"),
        ("address_abbr", "BLVD", "Boulevard"),
        ("address_abbr", "DR", "Drive"),
        ("address_abbr", "STE", "Suite"),
        ("address_abbr", "RD", "Road"),
        ("state_code", "CALIFORNIA", "CA"),
        ("state_code", "NEW YORK", "NY"),
        ("state_code", "DELAWARE", "DE"),
        ("state_code", "TEXAS", "TX"),
        ("state_code", "DISTRICT OF COLUMBIA", "DC"),
        ("country_code", "UNITED STATES", "US"),
        ("country_code", "UNITED STATES OF AMERICA", "US"),
        ("country_code", "USA", "US"),
        ("country_code", "CANADA", "CA"),
        ("country_code", "UNITED KINGDOM", "GB"),
    ]
    for rule_type, input_value, canonical_value in rows:
        _add_if_missing(
            session,
            db.MdmNormalizationRule,
            {"rule_type": rule_type, "input_value": input_value},
            {"canonical_value": canonical_value},
        )


def _seed_relationship_types(session: Session) -> None:
    rows = [
        ("IS_INSIDER", "person", "company", "outbound", ["source_entity_id", "target_entity_id", "title"], "extend_temporal", "Person is officer/director/10pct owner of company"),
        ("HOLDS", "person", "security", "outbound", ["source_entity_id", "target_entity_id"], "extend_temporal", "Person holds a security position"),
        ("ISSUED_BY", "security", "company", "outbound", ["source_entity_id", "target_entity_id"], "extend_temporal", "Security is issued by company"),
        ("IS_ENTITY_OF", "adviser", "company", "outbound", ["source_entity_id", "target_entity_id"], "replace", "Adviser is the same legal entity as a registered company"),
        ("MANAGES_FUND", "adviser", "fund", "outbound", ["source_entity_id", "target_entity_id"], "extend_temporal", "Adviser manages a private fund"),
        ("IS_PERSON_OF", "adviser", "person", "outbound", ["source_entity_id", "target_entity_id"], "replace", "Individual investment adviser is the same natural person as an ownership reporting owner"),
    ]
    for rel_type_name, src, tgt, direction, dedup, strategy, description in rows:
        _add_if_missing(
            session,
            db.MdmRelationshipType,
            {"rel_type_name": rel_type_name},
            {
                "source_node_type": src,
                "target_node_type": tgt,
                "direction": direction,
                "dedup_key_fields": dedup,
                "merge_strategy": strategy,
                "description": description,
            },
        )


def _seed_relationship_properties(session: Session) -> None:
    rows = [
        ("IS_INSIDER", "role", "text", True, "Officer/director role category"),
        ("IS_INSIDER", "title", "text", False, "Exact title string from filing"),
        ("IS_INSIDER", "source_accession", "text", False, "Source filing accession number"),
        ("HOLDS", "shares_owned", "float", False, "Number of shares held"),
        ("HOLDS", "direct_indirect", "text", False, "D = direct ownership, I = indirect"),
        ("HOLDS", "as_of_date", "date", False, "Date of the reported position"),
        ("HOLDS", "source_accession", "text", False, "Source filing accession number"),
        ("MANAGES_FUND", "since_date", "date", False, "Date adviser began managing the fund"),
        ("MANAGES_FUND", "source_accession", "text", False, "Source ADV filing accession number"),
    ]
    for rel_type_name, property_name, data_type, is_required, description in rows:
        rel_type = _first(session, db.MdmRelationshipType, rel_type_name=rel_type_name)
        if rel_type is None:
            continue
        _add_if_missing(
            session,
            db.MdmRelationshipPropertyDef,
            {"rel_type_id": rel_type.rel_type_id, "property_name": property_name},
            {
                "data_type": data_type,
                "is_required": is_required,
                "description": description,
            },
        )


def _seed_relationship_mappings(session: Session) -> None:
    rows = [
        (
            "IS_INSIDER",
            "ownership_filing",
            "sec_ownership_reporting_owner",
            "owner_cik",
            "accession_number",
            "person",
            "company",
            {"title": "officer_title", "source_accession": "accession_number"},
            "IS_INSIDER from Form 3/4/5 reporting owner rows.",
        ),
        (
            "MANAGES_FUND",
            "adv_filing",
            "sec_adv_private_fund",
            "accession_number",
            "fund_name",
            "adviser",
            "fund",
            {"source_accession": "accession_number", "fund_type": "fund_type"},
            "MANAGES_FUND from Form ADV private funds.",
        ),
        (
            "IS_ENTITY_OF",
            "derived",
            "mdm_adviser",
            "cik",
            "cik",
            "adviser",
            "company",
            {},
            "IS_ENTITY_OF derived by matching adviser CIK to company CIK.",
        ),
    ]
    for rel_type_name, source_system, source_table, source_field, target_field, source_type, target_type, mapping, description in rows:
        rel_type = _first(session, db.MdmRelationshipType, rel_type_name=rel_type_name)
        if rel_type is None:
            continue
        _add_if_missing(
            session,
            db.MdmRelationshipSourceMapping,
            {
                "rel_type_id": rel_type.rel_type_id,
                "source_system": source_system,
                "source_table": source_table,
            },
            {
                "source_entity_field": source_field,
                "target_entity_field": target_field,
                "source_entity_type": source_type,
                "target_entity_type": target_type,
                "property_mapping": mapping,
                "description": description,
            },
        )
