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
REASSIGN OWNED BY snowflake_admin TO application;

GRANT CONNECT ON DATABASE mdm TO application;
GRANT USAGE ON SCHEMA public TO application;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO application;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO application;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO application;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO application;

ANALYZE;
