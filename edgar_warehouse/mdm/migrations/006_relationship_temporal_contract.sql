-- =============================================================================
-- Phase 7 Plan 01: Relationship Identity, Temporal Contract, And Conflict Policy
-- Migration: 006_relationship_temporal_contract.sql
-- Description: Additive-only. Adds an immutable logical relationship ID
--              (deterministic, derived from rel_type/source/target -- see
--              database.relationship_logical_id), date-only half-open validity
--              (valid_from_date/valid_to_date) with explicit date provenance,
--              direct-vs-derived classification, supersession/quarantine
--              metadata, and a per-relationship-type source-priority registry
--              for conflict tie-breaks.
--
--              Every ALTER/CREATE is guarded (IF NOT EXISTS / column-existence
--              check) so this file is safe to re-run and preserves every
--              pre-migration mdm_relationship_instance row -- no row is
--              dropped, rewritten in place, or loses its original
--              source_system/source_accession provenance.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. New columns on mdm_relationship_instance (nullable/defaulted; additive)
-- ---------------------------------------------------------------------------
ALTER TABLE mdm_relationship_instance ADD COLUMN IF NOT EXISTS relationship_id UUID;
ALTER TABLE mdm_relationship_instance ADD COLUMN IF NOT EXISTS valid_from_date DATE;
ALTER TABLE mdm_relationship_instance ADD COLUMN IF NOT EXISTS valid_to_date DATE;
ALTER TABLE mdm_relationship_instance ADD COLUMN IF NOT EXISTS date_provenance TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE mdm_relationship_instance ADD COLUMN IF NOT EXISTS relationship_kind TEXT NOT NULL DEFAULT 'direct';
ALTER TABLE mdm_relationship_instance ADD COLUMN IF NOT EXISTS source_evidence JSONB;
ALTER TABLE mdm_relationship_instance ADD COLUMN IF NOT EXISTS superseded_by_version_id UUID
    REFERENCES mdm_relationship_instance(instance_id);
ALTER TABLE mdm_relationship_instance ADD COLUMN IF NOT EXISTS quarantined BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE mdm_relationship_instance ADD COLUMN IF NOT EXISTS quarantine_reason TEXT;


-- ---------------------------------------------------------------------------
-- 2. Backfill: deterministic logical relationship_id and best-effort dates
--    for every pre-migration row. relationship_id is a pure function of
--    (rel_type_id, source_entity_id, target_entity_id), so re-running this
--    UPDATE is a no-op once applied (idempotent).
--    valid_from_date/valid_to_date are copied from the existing
--    effective_from/effective_to columns as a starting point; date_provenance
--    stays 'unknown' for backfilled rows because pre-migration rows carry no
--    per-row marker distinguishing a reported date from an ingestion-time
--    proxy -- claiming 'reported' post hoc would be a silent, unverifiable
--    assumption. New writes (graph.py) set it explicitly going forward.
-- ---------------------------------------------------------------------------
-- md5() and gen_random_uuid() (pgcrypto) are the only extension-independent
-- primitives guaranteed available (see 001_initial_schema.sql); uuid-ossp is
-- not assumed enabled, so this hashes to a UUID-shaped value with md5 rather
-- than uuid_generate_v5. It is still a pure, deterministic function of
-- (rel_type_id, source_entity_id, target_entity_id) -- identical inputs
-- always produce the identical relationship_id, on this run and every rerun.
UPDATE mdm_relationship_instance
SET relationship_id = (
    substr(h, 1, 8) || '-' || substr(h, 9, 4) || '-' || substr(h, 13, 4) || '-'
    || substr(h, 17, 4) || '-' || substr(h, 21, 12)
)::uuid
FROM (
    SELECT instance_id,
           md5(rel_type_id::text || ':' || source_entity_id::text || ':' || target_entity_id::text) AS h
    FROM mdm_relationship_instance
    WHERE relationship_id IS NULL
) AS hashed
WHERE mdm_relationship_instance.instance_id = hashed.instance_id;

UPDATE mdm_relationship_instance
SET valid_from_date = effective_from
WHERE valid_from_date IS NULL AND effective_from IS NOT NULL;

UPDATE mdm_relationship_instance
SET valid_to_date = effective_to
WHERE valid_to_date IS NULL AND effective_to IS NOT NULL;

ALTER TABLE mdm_relationship_instance ALTER COLUMN relationship_id SET NOT NULL;


-- ---------------------------------------------------------------------------
-- 3. Constraints and index (guarded: drop-if-exists then add, for reruns)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_rel_instance_valid_interval'
    ) THEN
        ALTER TABLE mdm_relationship_instance ADD CONSTRAINT ck_rel_instance_valid_interval
            CHECK (valid_from_date IS NULL OR valid_to_date IS NULL OR valid_to_date > valid_from_date);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_rel_instance_date_provenance'
    ) THEN
        ALTER TABLE mdm_relationship_instance ADD CONSTRAINT ck_rel_instance_date_provenance
            CHECK (date_provenance IN ('reported','filing_date_proxy','unknown'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_rel_instance_relationship_kind'
    ) THEN
        ALTER TABLE mdm_relationship_instance ADD CONSTRAINT ck_rel_instance_relationship_kind
            CHECK (relationship_kind IN ('direct','derived'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_rel_instance_relationship_id ON mdm_relationship_instance(relationship_id);


-- ---------------------------------------------------------------------------
-- 4. New table: per-relationship-type source-priority registry
--    Lower priority wins (matches mdm_source_priority's "lowest-numbered is
--    highest-authority" convention already used for entity survivorship).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mdm_relationship_source_priority (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rel_type_id UUID NOT NULL REFERENCES mdm_relationship_type(rel_type_id),
    source_system TEXT NOT NULL,
    priority INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_rel_source_priority UNIQUE (rel_type_id, source_system)
);
