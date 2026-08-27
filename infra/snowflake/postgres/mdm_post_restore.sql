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
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_processor') THEN
        CREATE ROLE edgartools_acquisition_processor NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_silver_finalizer') THEN
        CREATE ROLE edgartools_acquisition_silver_finalizer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_registry_owner') THEN
        CREATE ROLE edgartools_acquisition_registry_owner NOLOGIN;
    END IF;
    GRANT edgartools_acquisition_owner TO snowflake_admin
      WITH INHERIT FALSE, SET TRUE;
    GRANT edgartools_acquisition_registry_owner TO snowflake_admin
      WITH INHERIT FALSE, SET TRUE;
    GRANT application TO snowflake_admin;
    GRANT edgartools_acquisition_coordinator TO application
      WITH INHERIT FALSE, SET TRUE;
    GRANT edgartools_acquisition_worker TO application
      WITH INHERIT FALSE, SET TRUE;
    GRANT edgartools_acquisition_operator TO application
      WITH INHERIT FALSE, SET TRUE;
    GRANT edgartools_acquisition_processor TO application
      WITH INHERIT FALSE, SET TRUE;
    GRANT edgartools_acquisition_silver_finalizer TO application
      WITH INHERIT FALSE, SET TRUE;
    GRANT edgartools_acquisition_registry_owner TO application
      WITH INHERIT FALSE, SET TRUE;
    GRANT USAGE, CREATE ON SCHEMA public TO edgartools_acquisition_owner;
    GRANT USAGE, CREATE ON SCHEMA public TO edgartools_acquisition_registry_owner;
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

DO $$
BEGIN
  -- A restore from a pre-Ticket14 backup has no acquisition objects yet; the
  -- following privileged migration will create them under the dedicated owner.
  IF to_regclass('public.source_fetch_decision') IS NOT NULL THEN
    GRANT SELECT, INSERT, UPDATE ON source_observation_cursor
      TO edgartools_acquisition_coordinator, edgartools_acquisition_operator;
    GRANT SELECT, INSERT ON source_fetch_decision
      TO edgartools_acquisition_coordinator, edgartools_acquisition_operator;
    GRANT SELECT, INSERT ON source_fetch_work
      TO edgartools_acquisition_coordinator, edgartools_acquisition_operator;
    GRANT SELECT ON source_fetch_transition
      TO edgartools_acquisition_coordinator, edgartools_acquisition_operator;
    GRANT SELECT ON source_fetch_decision, source_fetch_work, source_fetch_transition
      TO edgartools_acquisition_worker, edgartools_acquisition_processor;
    REVOKE EXECUTE ON FUNCTION
      record_initial_source_fetch_transition(UUID, TEXT),
      claim_source_fetch(UUID, TEXT, INTEGER, TIMESTAMPTZ),
      finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TEXT, TEXT)
    FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION record_initial_source_fetch_transition(UUID, TEXT)
      TO edgartools_acquisition_coordinator, edgartools_acquisition_operator;
    GRANT EXECUTE ON FUNCTION claim_source_fetch(UUID, TEXT, INTEGER, TIMESTAMPTZ)
      TO edgartools_acquisition_worker;
    GRANT EXECUTE ON FUNCTION finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TEXT, TEXT)
      TO edgartools_acquisition_worker;
    GRANT SELECT ON source_change_status TO
      edgartools_acquisition_coordinator,
      edgartools_acquisition_worker,
      edgartools_acquisition_operator;
    REVOKE ALL PRIVILEGES ON
      source_observation_cursor,
      source_fetch_decision,
      source_fetch_work,
      source_fetch_transition
    FROM application;
    REVOKE ALL PRIVILEGES ON source_change_status FROM application;
    EXECUTE 'ALTER TABLE source_observation_cursor OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER TABLE source_fetch_decision OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER TABLE source_fetch_work OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER TABLE source_fetch_transition OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER FUNCTION reject_acquisition_history_mutation() OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER FUNCTION enforce_acquisition_transition_role() OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER FUNCTION enforce_acquisition_work_role() OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER FUNCTION record_initial_source_fetch_transition(UUID, TEXT) OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER FUNCTION claim_source_fetch(UUID, TEXT, INTEGER, TIMESTAMPTZ) OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER FUNCTION finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TEXT, TEXT) OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER VIEW source_change_status OWNER TO edgartools_acquisition_owner';
  END IF;
  -- Ticket 18: a restore predating source_revision has none yet either --
  -- the privileged migration creates it under the same dedicated owner.
  IF to_regclass('public.source_revision') IS NOT NULL THEN
    GRANT SELECT ON source_revision
      TO edgartools_acquisition_coordinator, edgartools_acquisition_worker,
         edgartools_acquisition_operator, edgartools_acquisition_silver_finalizer;
    GRANT SELECT, INSERT ON source_revision TO edgartools_acquisition_processor;
    REVOKE ALL PRIVILEGES ON source_revision FROM application;
    EXECUTE 'ALTER TABLE source_revision OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER FUNCTION enforce_acquisition_revision_role() OWNER TO edgartools_acquisition_owner';
  END IF;
  -- Ticket 19: a restore predating source_processing_decision/
  -- source_expected_producer has neither yet -- the privileged migration
  -- creates both under the same dedicated owner.
  IF to_regclass('public.source_processing_decision') IS NOT NULL THEN
    GRANT SELECT ON source_processing_decision, source_expected_producer
      TO edgartools_acquisition_coordinator, edgartools_acquisition_worker,
         edgartools_acquisition_operator;
    GRANT SELECT, INSERT ON source_processing_decision, source_expected_producer
      TO edgartools_acquisition_processor;
    GRANT SELECT ON source_processing_decision, source_expected_producer
      TO edgartools_acquisition_silver_finalizer;
    GRANT UPDATE (silver_outcome, settled_at) ON source_processing_decision
      TO edgartools_acquisition_silver_finalizer;
    GRANT UPDATE (outcome, verified_reference, failure_detail, updated_at)
      ON source_expected_producer TO edgartools_acquisition_silver_finalizer;
    GRANT SELECT ON source_change_status_detail TO
      edgartools_acquisition_coordinator,
      edgartools_acquisition_worker,
      edgartools_acquisition_operator,
      edgartools_acquisition_processor,
      edgartools_acquisition_silver_finalizer;
    REVOKE ALL PRIVILEGES ON source_processing_decision, source_expected_producer
      FROM application;
    REVOKE ALL PRIVILEGES ON source_change_status_detail FROM application;
    EXECUTE 'ALTER TABLE source_processing_decision OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER TABLE source_expected_producer OWNER TO edgartools_acquisition_owner';
    EXECUTE 'ALTER VIEW source_change_status_detail OWNER TO edgartools_acquisition_owner';
  END IF;
  -- Ticket 20: a restore predating source_registry_version/
  -- source_registry_coverage has neither yet -- the privileged migration
  -- creates both under their own dedicated owner (a distinct governance
  -- responsibility from every fetch/processing role above).
  IF to_regclass('public.source_registry_version') IS NOT NULL THEN
    GRANT SELECT, INSERT, UPDATE ON source_registry_version, source_registry_coverage
      TO edgartools_acquisition_registry_owner;
    REVOKE ALL PRIVILEGES ON source_registry_version, source_registry_coverage
      FROM application;
    EXECUTE 'ALTER TABLE source_registry_version OWNER TO edgartools_acquisition_registry_owner';
    EXECUTE 'ALTER TABLE source_registry_coverage OWNER TO edgartools_acquisition_registry_owner';
  END IF;
  -- Ticket 25: a restore predating source_evidence_conflict has none yet --
  -- the privileged migration creates it, owned by edgartools_acquisition_owner
  -- (no new dedicated owner role -- same owner as source_revision; only
  -- CREATE on schema public was ever granted to the owner role, not to any
  -- operational role such as edgartools_acquisition_processor, which gets
  -- scoped operational GRANTs below instead).
  IF to_regclass('public.source_evidence_conflict') IS NOT NULL THEN
    GRANT SELECT, INSERT,
      UPDATE (status, repair_revision_id, resolved_at, operator_authorization_reference, resolution_reason)
      ON source_evidence_conflict TO edgartools_acquisition_processor;
    GRANT SELECT ON source_evidence_conflict TO
      edgartools_acquisition_coordinator, edgartools_acquisition_worker,
      edgartools_acquisition_operator, edgartools_acquisition_silver_finalizer;
    REVOKE ALL PRIVILEGES ON source_evidence_conflict FROM application;
    EXECUTE 'ALTER TABLE source_evidence_conflict OWNER TO edgartools_acquisition_owner';
  END IF;
  -- Ticket 34: a restore predating source_evidence_import has none yet --
  -- the privileged migration creates it, owned by edgartools_acquisition_owner
  -- (no new dedicated role -- import_evidence runs as the existing
  -- edgartools_acquisition_operator role, the same one OPERATOR_REQUEST/
  -- OPERATOR_EXCLUDED fetch decisions already require). exclusion_reason
  -- (a plain column added to the already-restored source_fetch_decision)
  -- needs no entry here -- it's covered by that table's existing table-level
  -- REVOKE/GRANT, which a new column automatically inherits.
  IF to_regclass('public.source_evidence_import') IS NOT NULL THEN
    GRANT SELECT, INSERT ON source_evidence_import TO edgartools_acquisition_operator;
    GRANT SELECT ON source_evidence_import TO
      edgartools_acquisition_coordinator, edgartools_acquisition_worker,
      edgartools_acquisition_processor, edgartools_acquisition_silver_finalizer;
    REVOKE ALL PRIVILEGES ON source_evidence_import FROM application;
    EXECUTE 'ALTER TABLE source_evidence_import OWNER TO edgartools_acquisition_owner';
  END IF;
END;
$$;

ANALYZE;
