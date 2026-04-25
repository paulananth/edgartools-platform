-- =============================================================================
-- MDM Initial Schema Migration
-- Migration: 001_initial_schema.sql
-- Description: Creates all 19 MDM PostgreSQL tables
--   Registry tables (2):   mdm_entity, mdm_source_ref
--   Domain tables (5):     mdm_company, mdm_adviser, mdm_person,
--                          mdm_security, mdm_fund
--   Rules tables (4):      mdm_source_priority, mdm_field_survivorship,
--                          mdm_match_threshold, mdm_normalization_rule
--   Pipeline tables (3):   mdm_entity_attribute_stage, mdm_match_review,
--                          mdm_change_log
--   Graph registry (5):    mdm_entity_type_definition, mdm_relationship_type,
--                          mdm_relationship_property_def,
--                          mdm_relationship_source_mapping,
--                          mdm_relationship_instance
-- =============================================================================

-- pgcrypto provides gen_random_uuid(). Required for PG < 13; no-op otherwise.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- REGISTRY TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mdm_entity (
    entity_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type      TEXT NOT NULL CHECK (entity_type IN ('company','adviser','person','security','fund')),
    is_quarantined   BOOLEAN NOT NULL DEFAULT FALSE,
    resolution_method TEXT,
    confidence       FLOAT,
    valid_from       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to         TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version          INT NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mdm_source_ref (
    entity_id        UUID NOT NULL REFERENCES mdm_entity(entity_id),
    source_system    TEXT NOT NULL,
    source_id        TEXT NOT NULL,
    source_priority  INT NOT NULL,
    confidence       FLOAT,
    matched_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (entity_id, source_system, source_id)
);

-- ---------------------------------------------------------------------------
-- DOMAIN GOLDEN RECORD TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mdm_company (
    entity_id              UUID PRIMARY KEY REFERENCES mdm_entity(entity_id),
    cik                    BIGINT UNIQUE NOT NULL,
    canonical_name         TEXT NOT NULL,
    ein                    TEXT,
    sic_code               TEXT,
    sic_description        TEXT,
    state_of_incorporation TEXT,
    fiscal_year_end        TEXT,
    primary_ticker         TEXT,
    primary_exchange       TEXT,
    tracking_status        TEXT,
    valid_from             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to               TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS mdm_adviser (
    entity_id                UUID PRIMARY KEY REFERENCES mdm_entity(entity_id),
    cik                      BIGINT,
    crd_number               TEXT UNIQUE,
    sec_file_number          TEXT,
    canonical_name           TEXT NOT NULL,
    adviser_type             TEXT,
    hq_city                  TEXT,
    hq_state                 TEXT,
    aum_total                NUMERIC,
    fund_count               INT,
    linked_company_entity_id UUID REFERENCES mdm_entity(entity_id),
    valid_from               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to                 TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS mdm_person (
    entity_id              UUID PRIMARY KEY REFERENCES mdm_entity(entity_id),
    owner_cik              BIGINT,
    canonical_name         TEXT NOT NULL,
    name_variants          JSONB,
    primary_role           TEXT,
    role_titles            JSONB,
    affiliated_company_count INT DEFAULT 0,
    valid_from             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to               TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS mdm_security (
    entity_id              UUID PRIMARY KEY REFERENCES mdm_entity(entity_id),
    issuer_entity_id       UUID REFERENCES mdm_entity(entity_id),
    canonical_title        TEXT NOT NULL,
    security_type          TEXT,
    cusip                  TEXT,
    isin                   TEXT,
    valid_from             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to               TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS mdm_fund (
    entity_id              UUID PRIMARY KEY REFERENCES mdm_entity(entity_id),
    adviser_entity_id      UUID REFERENCES mdm_entity(entity_id),
    canonical_name         TEXT NOT NULL,
    fund_type              TEXT,
    jurisdiction           TEXT,
    aum_amount             NUMERIC,
    aum_as_of_date         DATE,
    valid_from             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to               TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- RULES TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mdm_source_priority (
    rule_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type   TEXT NOT NULL,
    source_system TEXT NOT NULL,
    priority      INT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    description   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_type, source_system)
);

CREATE TABLE IF NOT EXISTS mdm_field_survivorship (
    rule_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type            TEXT NOT NULL,
    field_name             TEXT NOT NULL,
    rule_type              TEXT NOT NULL CHECK (rule_type IN ('source_priority','most_recent','immutable','highest_source_rank','custom')),
    source_system          TEXT,
    preferred_source_order JSONB,
    notes                  TEXT,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_type, field_name)
);

CREATE TABLE IF NOT EXISTS mdm_match_threshold (
    rule_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     TEXT NOT NULL,
    match_method    TEXT NOT NULL CHECK (match_method IN ('cik_exact','fuzzy_name','ml_splink')),
    auto_merge_min  FLOAT NOT NULL,
    review_min      FLOAT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_type, match_method)
);

CREATE TABLE IF NOT EXISTS mdm_normalization_rule (
    rule_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_type       TEXT NOT NULL CHECK (rule_type IN ('legal_suffix','title_alias','address_abbr','state_code','country_code')),
    input_value     TEXT NOT NULL,
    canonical_value TEXT NOT NULL,
    entity_type     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rule_type, input_value)
);

-- ---------------------------------------------------------------------------
-- PIPELINE TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mdm_entity_attribute_stage (
    stage_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       UUID NOT NULL REFERENCES mdm_entity(entity_id),
    source_system   TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    field_value     TEXT,
    global_priority INT NOT NULL,
    effective_date  DATE,
    was_selected    BOOLEAN NOT NULL DEFAULT FALSE,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_attr_stage_entity_field ON mdm_entity_attribute_stage(entity_id, field_name);
CREATE INDEX IF NOT EXISTS idx_attr_stage_selected ON mdm_entity_attribute_stage(entity_id, was_selected);

CREATE TABLE IF NOT EXISTS mdm_match_review (
    review_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id_a      UUID NOT NULL REFERENCES mdm_entity(entity_id),
    entity_id_b      UUID NOT NULL REFERENCES mdm_entity(entity_id),
    match_score      FLOAT NOT NULL,
    match_evidence   JSONB,
    status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected','quarantined')),
    reviewed_by      TEXT,
    reviewed_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mdm_change_log (
    change_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id        UUID NOT NULL REFERENCES mdm_entity(entity_id),
    entity_type      TEXT NOT NULL,
    changed_fields   JSONB,
    changed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    exported_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_change_log_pending ON mdm_change_log(exported_at) WHERE exported_at IS NULL;

-- ---------------------------------------------------------------------------
-- GRAPH REGISTRY TABLES
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS mdm_entity_type_definition (
    entity_type       TEXT PRIMARY KEY,
    neo4j_label       TEXT NOT NULL UNIQUE,
    domain_table      TEXT NOT NULL,
    api_path_prefix   TEXT NOT NULL,
    primary_id_field  TEXT NOT NULL,
    display_name      TEXT NOT NULL,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS mdm_relationship_type (
    rel_type_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rel_type_name      TEXT UNIQUE NOT NULL,
    source_node_type   TEXT NOT NULL REFERENCES mdm_entity_type_definition(entity_type),
    target_node_type   TEXT NOT NULL REFERENCES mdm_entity_type_definition(entity_type),
    direction          TEXT NOT NULL CHECK (direction IN ('outbound','inbound','both')),
    is_temporal        BOOLEAN NOT NULL DEFAULT TRUE,
    dedup_key_fields   JSONB,
    merge_strategy     TEXT NOT NULL DEFAULT 'extend_temporal' CHECK (merge_strategy IN ('extend_temporal','always_insert','replace')),
    description        TEXT,
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mdm_relationship_property_def (
    prop_def_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rel_type_id        UUID NOT NULL REFERENCES mdm_relationship_type(rel_type_id),
    property_name      TEXT NOT NULL,
    data_type          TEXT NOT NULL CHECK (data_type IN ('text','float','date','boolean','integer')),
    is_required        BOOLEAN NOT NULL DEFAULT FALSE,
    default_value      TEXT,
    description        TEXT,
    UNIQUE (rel_type_id, property_name)
);

CREATE TABLE IF NOT EXISTS mdm_relationship_source_mapping (
    mapping_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rel_type_id         UUID NOT NULL REFERENCES mdm_relationship_type(rel_type_id),
    source_system       TEXT NOT NULL,
    source_table        TEXT NOT NULL,
    source_entity_field TEXT NOT NULL,
    target_entity_field TEXT NOT NULL,
    source_entity_type  TEXT NOT NULL REFERENCES mdm_entity_type_definition(entity_type),
    target_entity_type  TEXT NOT NULL REFERENCES mdm_entity_type_definition(entity_type),
    property_mapping    JSONB NOT NULL,
    effective_from_field TEXT,
    effective_to_field   TEXT,
    filter_condition    JSONB,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    description         TEXT,
    UNIQUE (rel_type_id, source_system, source_table)
);

CREATE TABLE IF NOT EXISTS mdm_relationship_instance (
    instance_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rel_type_id        UUID NOT NULL REFERENCES mdm_relationship_type(rel_type_id),
    source_entity_id   UUID NOT NULL REFERENCES mdm_entity(entity_id),
    target_entity_id   UUID NOT NULL REFERENCES mdm_entity(entity_id),
    properties         JSONB,
    effective_from     DATE,
    effective_to       DATE,
    source_system      TEXT,
    source_accession   TEXT,
    graph_synced_at    TIMESTAMPTZ,
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rel_instance_dedup ON mdm_relationship_instance(source_entity_id, target_entity_id, rel_type_id);
CREATE INDEX IF NOT EXISTS idx_rel_instance_pending_sync ON mdm_relationship_instance(graph_synced_at) WHERE graph_synced_at IS NULL;
