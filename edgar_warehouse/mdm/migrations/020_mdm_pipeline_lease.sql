-- Ticket 50 (change-propagation map): exclusivity lease between ordinary
-- `mdm mastering` resolution and the monthly MDM Reconciliation Backstop.
-- Plain additive table, no owner-role/GRANT dance needed -- unlike the
-- acquisition-ledger/source-registry migrations, this is a new table in the
-- same schema every other mdm_* table already lives in, owned by whichever
-- role runs `mdm migrate` today.

CREATE TABLE IF NOT EXISTS mdm_pipeline_lease (
    lease_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    run_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL,
    released_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_pipeline_lease_status CHECK (status IN ('held', 'idle'))
);
