-- Ticket 20: version and activate the Acquisition Universe.
-- A dedicated role, distinct from every fetch/processing role in 013 --
-- deciding what's in scope is governance over the acquisition universe
-- itself, not a step within it.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_registry_owner'
    ) THEN
        CREATE ROLE edgartools_acquisition_registry_owner NOLOGIN;
    END IF;
    IF current_user <> 'application' THEN
        EXECUTE format(
            'GRANT edgartools_acquisition_registry_owner TO %I WITH INHERIT FALSE, SET TRUE',
            current_user
        );
    END IF;
    GRANT USAGE, CREATE ON SCHEMA public TO edgartools_acquisition_registry_owner;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'application') THEN
        GRANT edgartools_acquisition_registry_owner TO application
            WITH INHERIT FALSE, SET TRUE;
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS source_registry_version (
    version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status TEXT NOT NULL DEFAULT 'draft',
    operator_authorization_reference TEXT NOT NULL,
    blocker TEXT,
    next_action TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    superseded_at TIMESTAMPTZ,
    CONSTRAINT ck_source_registry_version_status
        CHECK (status IN ('draft','activation_blocked','active','superseded')),
    -- activated_at is set once, on activation, and stays put as history
    -- through a later supersession -- 'active' requires it non-null, but a
    -- 'superseded' row legitimately keeps it non-null too.
    CONSTRAINT ck_source_registry_version_activated_at_shape
        CHECK (status <> 'active' OR activated_at IS NOT NULL),
    CONSTRAINT ck_source_registry_version_blocker_shape
        CHECK (status <> 'activation_blocked' OR (blocker IS NOT NULL AND next_action IS NOT NULL))
);

-- At most one row may ever be 'active' -- a partial unique index on a
-- constant expression is the standard Postgres idiom for "unique across
-- every row matching this predicate" (mirrors
-- uq_source_processing_decision_active_key in 013).
CREATE UNIQUE INDEX IF NOT EXISTS uq_source_registry_version_single_active
    ON source_registry_version ((1))
    WHERE status = 'active';

CREATE TABLE IF NOT EXISTS source_registry_coverage (
    coverage_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID NOT NULL REFERENCES source_registry_version(version_id),
    source_family TEXT NOT NULL,
    coverage_action TEXT NOT NULL,
    in_scope_forms JSONB NOT NULL DEFAULT '[]'::JSONB,
    acquisition_mode TEXT NOT NULL,
    completeness_policy TEXT NOT NULL,
    discovery_policy TEXT NOT NULL,
    required_producers JSONB NOT NULL DEFAULT '[]'::JSONB,
    coverage_start_date DATE NOT NULL,
    coverage_end_date DATE,
    catchup_required_through_date DATE,
    catchup_verified_through_date DATE,
    CONSTRAINT uq_source_registry_coverage_family UNIQUE (version_id, source_family),
    CONSTRAINT ck_source_registry_coverage_action
        CHECK (coverage_action IN ('add','remove','carry_forward')),
    CONSTRAINT ck_source_registry_coverage_remove_end_date
        CHECK (coverage_action <> 'remove' OR coverage_end_date IS NOT NULL),
    CONSTRAINT ck_source_registry_coverage_add_catchup_required
        CHECK (coverage_action <> 'add' OR catchup_required_through_date IS NOT NULL)
);

GRANT SELECT, INSERT, UPDATE ON source_registry_version, source_registry_coverage
    TO edgartools_acquisition_registry_owner;

ALTER TABLE source_registry_version OWNER TO edgartools_acquisition_registry_owner;
ALTER TABLE source_registry_coverage OWNER TO edgartools_acquisition_registry_owner;

-- Fenced the same way as every 013 table: runtime code must SET ROLE
-- edgartools_acquisition_registry_owner (registry_ledger.py does this
-- uniformly, reads included) rather than touching these tables via
-- application's own broad legacy grants.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'application') THEN
        REVOKE ALL PRIVILEGES ON source_registry_version, source_registry_coverage
        FROM application;
    END IF;
END;
$$;
