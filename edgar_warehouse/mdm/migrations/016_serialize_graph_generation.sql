-- =============================================================================
-- Migration: 016_serialize_graph_generation.sql
-- Ticket 40 (Incremental Change Propagation map): prevent two graph
-- generation-build pipeline executions from running concurrently. Additive-
-- only.
-- =============================================================================

-- At most one mdm_graph_generation row may be non-terminal ('building' or
-- 'verified') at a time -- a partial unique index on a constant expression is
-- the standard Postgres idiom for "unique across every row matching this
-- predicate" (mirrors uq_source_registry_version_single_active in 014, itself
-- mirroring uq_source_processing_decision_active_key in 013). A build
-- rejected by this index fails outright rather than queuing (Ticket 40's
-- Answer) -- the next natural trigger picks up current state once the
-- existing generation reaches a terminal status ('activated' or 'failed').
CREATE UNIQUE INDEX IF NOT EXISTS uq_graph_generation_single_non_terminal
    ON mdm_graph_generation ((1))
    WHERE status IN ('building', 'verified');
