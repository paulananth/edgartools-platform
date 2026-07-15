-- =============================================================================
-- Phase 7 Plan 02: Exhaustive Relationship Coverage And Exclusion Policy
-- Migration: 007_relationship_coverage.sql
-- Description: Adds mdm_relationship_coverage -- one machine-readable record
--              per (generation, relationship type) classifying every active
--              relationship type as populated/valid_zero/excluded, replacing
--              prose-only coverage claims (EDGE-05..11) with a fingerprinted,
--              queryable ledger. Additive-only; creates no new relationship
--              or graph edge data.
-- =============================================================================

CREATE TABLE IF NOT EXISTS mdm_relationship_coverage (
    coverage_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id TEXT NOT NULL,
    rel_type_id UUID NOT NULL REFERENCES mdm_relationship_type(rel_type_id),
    status TEXT NOT NULL,
    expected_edge_count INTEGER NOT NULL,
    evidence_category TEXT,
    evidence_query_version TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    population_fingerprint TEXT NOT NULL,
    review_trigger TEXT,
    CONSTRAINT uq_rel_coverage_generation_type UNIQUE (generation_id, rel_type_id),
    CONSTRAINT ck_rel_coverage_status
        CHECK (status IN ('populated','valid_zero','excluded')),
    CONSTRAINT ck_rel_coverage_evidence_category
        CHECK (
            evidence_category IS NULL OR evidence_category IN (
                'source_unavailable','capability_not_implemented','scoped_zero_overlap',
                'structural_api_limitation','root_caused_fix_deferred'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_rel_coverage_generation ON mdm_relationship_coverage(generation_id);
