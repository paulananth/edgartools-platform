-- =============================================================================
-- Phase 7 Plan 03: Transactional MDM -> Graph Publication Queue
-- Migration: 008_publication_queue.sql
-- Description: Adds mdm_publication_request -- a transactional outbox row
--              created in the same commit as the relationship change it
--              accompanies, carrying a committed MDM watermark, lifecycle
--              state (mdm_committed -> graph_pending -> graph_building ->
--              graph_verified -> graph_active, or failed), claim/lease
--              metadata for safe concurrent claiming, retry count, and
--              optional bounded-backfill-window metadata. Additive-only.
-- =============================================================================

CREATE TABLE IF NOT EXISTS mdm_publication_request (
    request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lifecycle_state TEXT NOT NULL DEFAULT 'mdm_committed',
    committed_watermark TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_by TEXT,
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    is_backfill BOOLEAN NOT NULL DEFAULT FALSE,
    backfill_deadline TIMESTAMPTZ,
    generation_id TEXT,
    source_summary JSONB,
    activated_at TIMESTAMPTZ,
    CONSTRAINT ck_pub_request_lifecycle_state CHECK (
        lifecycle_state IN (
            'mdm_committed','graph_pending','graph_building',
            'graph_verified','graph_active','failed'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_pub_request_lifecycle_state
    ON mdm_publication_request(lifecycle_state);
