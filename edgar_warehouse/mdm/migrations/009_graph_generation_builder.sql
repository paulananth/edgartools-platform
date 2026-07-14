-- =============================================================================
-- Phase 7 Plan 04: Parallel Generation Builder, Partition Manifests
-- Migration: 009_graph_generation_builder.sql
-- Description: Adds mdm_graph_generation (one row per requested generation
--              build) and mdm_graph_partition (one immutable, content-
--              addressed row per node-type/relationship-type/shard within a
--              generation). Additive-only.
-- =============================================================================

CREATE TABLE IF NOT EXISTS mdm_graph_generation (
    generation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status TEXT NOT NULL DEFAULT 'building',
    committed_watermark TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rule_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,
    failure_reasons JSONB,
    CONSTRAINT ck_graph_generation_status
        CHECK (status IN ('building','verified','activated','failed'))
);

CREATE TABLE IF NOT EXISTS mdm_graph_partition (
    partition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id UUID NOT NULL REFERENCES mdm_graph_generation(generation_id),
    kind TEXT NOT NULL,
    type_name TEXT NOT NULL,
    shard_index INTEGER NOT NULL DEFAULT 0,
    shard_count INTEGER NOT NULL DEFAULT 1,
    mdm_watermark TIMESTAMPTZ NOT NULL,
    rule_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    stable_key_hash TEXT NOT NULL,
    property_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reused_from_partition_id UUID REFERENCES mdm_graph_partition(partition_id),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_graph_partition_generation_shard
        UNIQUE (generation_id, kind, type_name, shard_index),
    CONSTRAINT ck_graph_partition_kind CHECK (kind IN ('node','edge')),
    CONSTRAINT ck_graph_partition_status
        CHECK (status IN ('pending','building','built','reused','failed'))
);

CREATE INDEX IF NOT EXISTS idx_graph_partition_content_hash
    ON mdm_graph_partition(content_hash);
