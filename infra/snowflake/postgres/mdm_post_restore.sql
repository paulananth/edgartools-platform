-- Post-restore grants and statistics for the MDM Snowflake Postgres target.
--
-- Run against database mdm as snowflake_admin after pg_restore, for example:
--   psql "$SNOWFLAKE_ADMIN_DSN" \
--     --set=ON_ERROR_STOP=1 \
--     --file=infra/snowflake/postgres/mdm_post_restore.sql

-- Restored tables/indexes/sequences are owned by snowflake_admin (the role
-- that ran pg_restore). Ownership, not just DML grants, is required for DDL
-- the runtime re-issues idempotently (e.g. CREATE INDEX IF NOT EXISTS) --
-- Postgres gates that on table ownership regardless of IF NOT EXISTS.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_owner') THEN
        CREATE ROLE edgartools_acquisition_owner NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_coordinator') THEN
        CREATE ROLE edgartools_acquisition_coordinator NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_worker') THEN
        CREATE ROLE edgartools_acquisition_worker NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_operator') THEN
        CREATE ROLE edgartools_acquisition_operator NOLOGIN;
    END IF;
    GRANT edgartools_acquisition_owner TO snowflake_admin
      WITH INHERIT FALSE, SET TRUE;
    GRANT edgartools_acquisition_coordinator TO application
      WITH INHERIT FALSE, SET TRUE;
    GRANT edgartools_acquisition_worker TO application
      WITH INHERIT FALSE, SET TRUE;
    GRANT edgartools_acquisition_operator TO application
      WITH INHERIT FALSE, SET TRUE;
    GRANT USAGE, CREATE ON SCHEMA public TO edgartools_acquisition_owner;
END;
$$;

REASSIGN OWNED BY snowflake_admin TO application;

GRANT CONNECT ON DATABASE mdm TO application;
GRANT USAGE ON SCHEMA public TO application;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO application;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO application;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO application;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO application;

ALTER TABLE source_observation_cursor OWNER TO edgartools_acquisition_owner;
ALTER TABLE source_fetch_decision OWNER TO edgartools_acquisition_owner;
ALTER TABLE source_fetch_work OWNER TO edgartools_acquisition_owner;
ALTER TABLE source_fetch_transition OWNER TO edgartools_acquisition_owner;
ALTER FUNCTION reject_acquisition_history_mutation()
  OWNER TO edgartools_acquisition_owner;
ALTER FUNCTION enforce_acquisition_transition_role()
  OWNER TO edgartools_acquisition_owner;
ALTER FUNCTION enforce_acquisition_work_role()
  OWNER TO edgartools_acquisition_owner;
ALTER FUNCTION record_initial_source_fetch_transition(UUID, TEXT)
  OWNER TO edgartools_acquisition_owner;
ALTER FUNCTION claim_source_fetch(UUID, TEXT, INTEGER, TIMESTAMPTZ)
  OWNER TO edgartools_acquisition_owner;
ALTER FUNCTION finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ)
  OWNER TO edgartools_acquisition_owner;
ALTER VIEW source_change_status OWNER TO edgartools_acquisition_owner;

REVOKE ALL PRIVILEGES ON
  source_observation_cursor,
  source_fetch_decision,
  source_fetch_work,
  source_fetch_transition
FROM application;
REVOKE ALL PRIVILEGES ON source_change_status FROM application;

ANALYZE;
