-- Ticket 14: PostgreSQL source-acquisition authority and status spine.
-- Source Fetch Decisions and transitions are immutable audit records. Mutable
-- coordination is isolated in source_fetch_work and guarded by fenced leases.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_coordinator') THEN
        CREATE ROLE edgartools_acquisition_coordinator NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_worker') THEN
        CREATE ROLE edgartools_acquisition_worker NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edgartools_acquisition_operator') THEN
        CREATE ROLE edgartools_acquisition_operator NOLOGIN;
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS source_observation_cursor (
    source_family TEXT NOT NULL,
    logical_source_key TEXT NOT NULL,
    last_position BIGINT NOT NULL,
    PRIMARY KEY (source_family, logical_source_key),
    CONSTRAINT ck_source_observation_position_positive CHECK (last_position > 0)
);

CREATE TABLE IF NOT EXISTS source_fetch_decision (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id TEXT NOT NULL UNIQUE,
    source_family TEXT NOT NULL,
    logical_source_key TEXT NOT NULL,
    source_url TEXT NOT NULL,
    observation_position BIGINT NOT NULL,
    cause TEXT NOT NULL,
    cause_reference TEXT NOT NULL,
    owner_role TEXT NOT NULL,
    fetch_disposition TEXT NOT NULL,
    blocker TEXT,
    next_action TEXT NOT NULL,
    next_eligible_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_source_fetch_decision_observation
        UNIQUE (source_family, logical_source_key, observation_position),
    CONSTRAINT ck_source_fetch_decision_cause CHECK (
        cause IN ('CAPTURED_DISCOVERY','DUE_POLICY','OPERATOR_REQUEST')
    ),
    CONSTRAINT ck_source_fetch_decision_owner_role CHECK (
        owner_role IN ('ACQUISITION_COORDINATOR','ACQUISITION_OPERATOR')
    ),
    CONSTRAINT ck_source_fetch_decision_disposition CHECK (
        fetch_disposition IN (
            'FETCH_AUTHORIZED','DOWNLOAD_DEFERRED',
            'ALREADY_CAPTURED_VERIFIED','OUT_OF_SCOPE','OPERATOR_EXCLUDED'
        )
    ),
    CONSTRAINT ck_source_fetch_decision_cause_owner CHECK (
        (cause = 'OPERATOR_REQUEST' AND owner_role = 'ACQUISITION_OPERATOR') OR
        (cause IN ('CAPTURED_DISCOVERY','DUE_POLICY') AND
         owner_role = 'ACQUISITION_COORDINATOR')
    ),
    CONSTRAINT ck_source_fetch_decision_operator_exclusion CHECK (
        fetch_disposition <> 'OPERATOR_EXCLUDED' OR
        (cause = 'OPERATOR_REQUEST' AND owner_role = 'ACQUISITION_OPERATOR')
    ),
    CONSTRAINT ck_source_fetch_decision_deferred_open CHECK (
        fetch_disposition <> 'DOWNLOAD_DEFERRED' OR
        (blocker IS NOT NULL AND next_eligible_at IS NOT NULL AND
         next_action <> 'NONE')
    ),
    CONSTRAINT ck_source_fetch_decision_terminal_no_download CHECK (
        fetch_disposition NOT IN (
            'ALREADY_CAPTURED_VERIFIED','OUT_OF_SCOPE','OPERATOR_EXCLUDED'
        ) OR (next_action = 'NONE' AND next_eligible_at IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS source_fetch_work (
    decision_id UUID PRIMARY KEY REFERENCES source_fetch_decision(decision_id),
    source_family TEXT NOT NULL,
    logical_source_key TEXT NOT NULL,
    fetch_state TEXT NOT NULL,
    fencing_token BIGINT NOT NULL DEFAULT 0,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    last_transition_role TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_source_fetch_work_state CHECK (
        fetch_state IN ('READY','LEASED','CAPTURED','FAILED')
    ),
    CONSTRAINT ck_source_fetch_work_fencing_token CHECK (fencing_token >= 0),
    CONSTRAINT ck_source_fetch_work_transition_role CHECK (
        last_transition_role IN ('ACQUISITION_COORDINATOR','ACQUISITION_WORKER')
    ),
    CONSTRAINT ck_source_fetch_work_state_shape CHECK (
        (fetch_state = 'READY' AND fencing_token = 0 AND lease_owner IS NULL AND
         lease_expires_at IS NULL AND
         last_transition_role = 'ACQUISITION_COORDINATOR') OR
        (fetch_state = 'LEASED' AND fencing_token > 0 AND lease_owner IS NOT NULL AND
         lease_expires_at IS NOT NULL AND
         last_transition_role = 'ACQUISITION_WORKER') OR
        (fetch_state IN ('CAPTURED','FAILED') AND fencing_token > 0 AND
         lease_owner IS NULL AND lease_expires_at IS NULL AND
         last_transition_role = 'ACQUISITION_WORKER')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_source_fetch_work_active_key
    ON source_fetch_work(source_family, logical_source_key)
    WHERE fetch_state IN ('READY','LEASED');

CREATE TABLE IF NOT EXISTS source_fetch_transition (
    transition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES source_fetch_decision(decision_id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    owner_role TEXT NOT NULL,
    fencing_token BIGINT NOT NULL,
    worker_id TEXT,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_source_fetch_transition_state CHECK (
        to_state IN ('READY','LEASED','CAPTURED','FAILED')
    ),
    CONSTRAINT ck_source_fetch_transition_owner CHECK (
        (from_state IS NULL AND to_state = 'READY' AND
         owner_role = 'ACQUISITION_COORDINATOR' AND fencing_token = 0) OR
        (to_state IN ('LEASED','CAPTURED','FAILED') AND
         owner_role = 'ACQUISITION_WORKER' AND fencing_token > 0)
    )
);

CREATE OR REPLACE FUNCTION reject_acquisition_history_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS source_fetch_decision_immutable ON source_fetch_decision;
CREATE TRIGGER source_fetch_decision_immutable
BEFORE UPDATE OR DELETE ON source_fetch_decision
FOR EACH ROW EXECUTE FUNCTION reject_acquisition_history_mutation();

DROP TRIGGER IF EXISTS source_fetch_transition_immutable ON source_fetch_transition;
CREATE TRIGGER source_fetch_transition_immutable
BEFORE UPDATE OR DELETE ON source_fetch_transition
FOR EACH ROW EXECUTE FUNCTION reject_acquisition_history_mutation();

CREATE OR REPLACE FUNCTION enforce_acquisition_transition_role()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    required_role TEXT;
BEGIN
    required_role := CASE NEW.owner_role
        WHEN 'ACQUISITION_COORDINATOR' THEN 'edgartools_acquisition_coordinator'
        WHEN 'ACQUISITION_OPERATOR' THEN 'edgartools_acquisition_operator'
        WHEN 'ACQUISITION_WORKER' THEN 'edgartools_acquisition_worker'
        ELSE NULL
    END;
    IF required_role IS NULL OR
       NOT pg_has_role(session_user, required_role, 'MEMBER') THEN
        RAISE EXCEPTION 'database role % does not own % transition',
            session_user, NEW.owner_role;
    END IF;
    RETURN NEW;
EXCEPTION WHEN undefined_object THEN
    RAISE EXCEPTION 'required acquisition database role % is not provisioned',
        required_role;
END;
$$;

DROP TRIGGER IF EXISTS source_fetch_decision_role_owner ON source_fetch_decision;
CREATE TRIGGER source_fetch_decision_role_owner
BEFORE INSERT ON source_fetch_decision
FOR EACH ROW EXECUTE FUNCTION enforce_acquisition_transition_role();

DROP TRIGGER IF EXISTS source_fetch_transition_role_owner ON source_fetch_transition;
CREATE TRIGGER source_fetch_transition_role_owner
BEFORE INSERT ON source_fetch_transition
FOR EACH ROW EXECUTE FUNCTION enforce_acquisition_transition_role();

CREATE OR REPLACE FUNCTION enforce_acquisition_work_role()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    required_role TEXT;
BEGIN
    required_role := CASE NEW.last_transition_role
        WHEN 'ACQUISITION_COORDINATOR' THEN 'edgartools_acquisition_coordinator'
        WHEN 'ACQUISITION_WORKER' THEN 'edgartools_acquisition_worker'
        ELSE NULL
    END;
    IF required_role IS NULL OR
       NOT pg_has_role(session_user, required_role, 'MEMBER') THEN
        RAISE EXCEPTION 'database role % does not own % transition',
            session_user, NEW.last_transition_role;
    END IF;
    RETURN NEW;
EXCEPTION WHEN undefined_object THEN
    RAISE EXCEPTION 'required acquisition database role % is not provisioned',
        required_role;
END;
$$;

DROP TRIGGER IF EXISTS source_fetch_work_role_owner ON source_fetch_work;
CREATE TRIGGER source_fetch_work_role_owner
BEFORE INSERT OR UPDATE ON source_fetch_work
FOR EACH ROW EXECUTE FUNCTION enforce_acquisition_work_role();

CREATE OR REPLACE FUNCTION claim_source_fetch(
    requested_decision_id UUID,
    requested_worker_id TEXT,
    requested_lease_seconds INTEGER,
    requested_at TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE(fencing_token BIGINT, lease_expires_at TIMESTAMPTZ)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    previous_state TEXT;
    claimed_token BIGINT;
    claimed_until TIMESTAMPTZ;
BEGIN
    IF NOT pg_has_role(session_user, 'edgartools_acquisition_worker', 'MEMBER') THEN
        RAISE EXCEPTION 'database role % cannot claim source fetches', session_user;
    END IF;
    IF requested_lease_seconds <= 0 THEN
        RAISE EXCEPTION 'lease seconds must be positive';
    END IF;

    SELECT work.fetch_state
    INTO previous_state
    FROM source_fetch_work AS work
    WHERE work.decision_id = requested_decision_id
    FOR UPDATE;

    UPDATE source_fetch_work AS work
    SET fetch_state = 'LEASED',
        fencing_token = work.fencing_token + 1,
        lease_owner = requested_worker_id,
        lease_expires_at = requested_at + make_interval(secs => requested_lease_seconds),
        last_transition_role = 'ACQUISITION_WORKER',
        updated_at = requested_at
    WHERE work.decision_id = requested_decision_id
      AND (
          work.fetch_state = 'READY' OR
          (work.fetch_state = 'LEASED' AND work.lease_expires_at <= requested_at)
      )
    RETURNING work.fencing_token, work.lease_expires_at
    INTO claimed_token, claimed_until;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'source fetch work is not claimable for decision %',
            requested_decision_id;
    END IF;

    INSERT INTO source_fetch_transition (
        decision_id, from_state, to_state, owner_role,
        fencing_token, worker_id, reason
    ) VALUES (
        requested_decision_id, previous_state, 'LEASED', 'ACQUISITION_WORKER',
        claimed_token, requested_worker_id, 'LEASE_ACQUIRED'
    );

    RETURN QUERY SELECT claimed_token, claimed_until;
END;
$$;

CREATE OR REPLACE FUNCTION finalize_source_fetch(
    requested_decision_id UUID,
    requested_worker_id TEXT,
    presented_fencing_token BIGINT,
    requested_final_state TEXT,
    requested_at TIMESTAMPTZ DEFAULT NOW()
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF NOT pg_has_role(session_user, 'edgartools_acquisition_worker', 'MEMBER') THEN
        RAISE EXCEPTION 'database role % cannot finalize source fetches', session_user;
    END IF;
    IF requested_final_state NOT IN ('CAPTURED','FAILED') THEN
        RAISE EXCEPTION 'invalid final source fetch state %', requested_final_state;
    END IF;
    UPDATE source_fetch_work
    SET fetch_state = requested_final_state,
        lease_owner = NULL,
        lease_expires_at = NULL,
        last_transition_role = 'ACQUISITION_WORKER',
        updated_at = requested_at
    WHERE decision_id = requested_decision_id
      AND fetch_state = 'LEASED'
      AND lease_owner = requested_worker_id
      AND fencing_token = presented_fencing_token
      AND lease_expires_at > requested_at;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'stale fencing token for Source Fetch Decision %',
            requested_decision_id;
    END IF;
    INSERT INTO source_fetch_transition (
        decision_id, from_state, to_state, owner_role,
        fencing_token, worker_id, reason
    ) VALUES (
        requested_decision_id, 'LEASED', requested_final_state,
        'ACQUISITION_WORKER', presented_fencing_token,
        requested_worker_id, 'FETCH_' || requested_final_state
    );
END;
$$;

-- source_fetch_decision is immutable; source_fetch_transition is immutable.
REVOKE INSERT, UPDATE, DELETE ON source_observation_cursor FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE ON source_fetch_decision FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE ON source_fetch_work FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE ON source_fetch_transition FROM PUBLIC;

GRANT SELECT, INSERT, UPDATE ON source_observation_cursor
    TO edgartools_acquisition_coordinator;
GRANT SELECT, INSERT ON source_fetch_decision
    TO edgartools_acquisition_coordinator, edgartools_acquisition_operator;
GRANT SELECT, INSERT ON source_fetch_work
    TO edgartools_acquisition_coordinator;
GRANT SELECT, INSERT ON source_fetch_transition
    TO edgartools_acquisition_coordinator;
GRANT SELECT ON source_fetch_decision, source_fetch_work, source_fetch_transition
    TO edgartools_acquisition_worker;
GRANT INSERT ON source_fetch_transition TO edgartools_acquisition_worker;
REVOKE EXECUTE ON FUNCTION claim_source_fetch(UUID, TEXT, INTEGER, TIMESTAMPTZ)
    FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_source_fetch(UUID, TEXT, INTEGER, TIMESTAMPTZ)
    TO edgartools_acquisition_worker;
GRANT EXECUTE ON FUNCTION finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ)
    TO edgartools_acquisition_worker;

CREATE OR REPLACE VIEW source_change_status AS
SELECT
    decision.decision_id,
    decision.candidate_id,
    decision.source_family,
    decision.logical_source_key,
    decision.observation_position,
    decision.cause,
    decision.fetch_disposition,
    work.fetch_state,
    decision.blocker,
    CASE work.fetch_state
        WHEN 'LEASED' THEN 'FETCH_SOURCE'
        WHEN 'CAPTURED' THEN 'MATERIALIZE_SOURCE_REVISION'
        WHEN 'FAILED' THEN 'RETRY_FETCH'
        ELSE decision.next_action
    END AS next_action,
    decision.next_eligible_at,
    decision.created_at
FROM source_fetch_decision AS decision
LEFT JOIN source_fetch_work AS work
  ON work.decision_id = decision.decision_id;

GRANT SELECT ON source_change_status TO
    edgartools_acquisition_coordinator,
    edgartools_acquisition_worker,
    edgartools_acquisition_operator;
