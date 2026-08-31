-- Ticket 30: bind durable MDM commit evidence to its originating operation.
-- Historical evidence remains unknown; application write paths populate new rows.

ALTER TABLE mdm_change_log
    ADD COLUMN IF NOT EXISTS run_id TEXT;

ALTER TABLE mdm_relationship_instance
    ADD COLUMN IF NOT EXISTS run_id TEXT;

CREATE INDEX IF NOT EXISTS idx_change_log_run_id
    ON mdm_change_log (run_id)
    WHERE run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rel_instance_run_id
    ON mdm_relationship_instance (run_id)
    WHERE run_id IS NOT NULL;
