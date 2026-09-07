-- mdm-relationship-incremental-filters wayfinder map, Ticket 04: per-type
-- (or, for a type with more than one independent source table, per
-- sub-source) high-water-mark checkpoint for MDMPipeline.derive_relationships(),
-- so a steady-state run scans only rows new since the last successful
-- derivation instead of the full source table every time. Plain additive
-- table, no owner-role/GRANT dance needed -- same shape as
-- 020_mdm_pipeline_lease.sql (a new table in the same schema every other
-- mdm_* table already lives in, owned by whichever role runs `mdm migrate`
-- today).

CREATE TABLE IF NOT EXISTS mdm_relationship_derivation_checkpoint (
    checkpoint_key TEXT PRIMARY KEY,
    rel_type_name TEXT NOT NULL,
    watermark_column TEXT NOT NULL,
    watermark_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
