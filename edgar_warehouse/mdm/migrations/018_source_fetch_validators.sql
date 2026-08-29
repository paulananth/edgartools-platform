-- Ticket 28: store HTTP validators from the latest verified capture so a
-- later DUE_POLICY re-poll can send If-None-Match / If-Modified-Since.
-- Additive columns on source_fetch_work (013). No new table.
--
-- Worker has SELECT-only on source_fetch_work (013); CAPTURED writes go
-- through SECURITY DEFINER finalize_source_fetch. A sidecar UPDATE after
-- that function would permission-deny on real Postgres, so the 7-arg
-- function is replaced with a 9-arg version that writes the new columns
-- in the same fenced UPDATE. 013's CREATE OR REPLACE of the 7-arg
-- signature would otherwise come back as an overload on an owner-privileged
-- rerun -- this file always DROPs that signature so migrate() ends on the
-- 9-arg function.

ALTER TABLE source_fetch_work ADD COLUMN IF NOT EXISTS captured_etag TEXT;
ALTER TABLE source_fetch_work ADD COLUMN IF NOT EXISTS captured_last_modified TEXT;

DROP FUNCTION IF EXISTS finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TEXT, TEXT);

CREATE OR REPLACE FUNCTION finalize_source_fetch(
    requested_decision_id UUID,
    requested_worker_id TEXT,
    presented_fencing_token BIGINT,
    requested_final_state TEXT,
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    requested_artifact_reference TEXT DEFAULT NULL,
    requested_failure_detail TEXT DEFAULT NULL,
    requested_etag TEXT DEFAULT NULL,
    requested_last_modified TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    transition_reason TEXT;
BEGIN
    IF current_setting('role', TRUE) <> 'edgartools_acquisition_worker' THEN
        RAISE EXCEPTION 'active database role % cannot finalize source fetches',
            current_setting('role', TRUE);
    END IF;
    IF requested_final_state NOT IN ('CAPTURED','FAILED') THEN
        RAISE EXCEPTION 'invalid final source fetch state %', requested_final_state;
    END IF;
    IF requested_final_state = 'CAPTURED' AND
       NULLIF(BTRIM(requested_artifact_reference), '') IS NULL THEN
        RAISE EXCEPTION 'artifact reference is required to finalize decision % as CAPTURED',
            requested_decision_id;
    END IF;
    IF requested_final_state = 'CAPTURED' AND
       NULLIF(BTRIM(requested_failure_detail), '') IS NOT NULL THEN
        RAISE EXCEPTION 'failure detail must not be set to finalize decision % as CAPTURED',
            requested_decision_id;
    END IF;
    transition_reason := COALESCE(
        NULLIF(BTRIM(requested_failure_detail), ''),
        'FETCH_' || requested_final_state
    );
    UPDATE source_fetch_work
    SET fetch_state = requested_final_state,
        lease_owner = NULL,
        lease_expires_at = NULL,
        last_transition_role = 'ACQUISITION_WORKER',
        captured_artifact_reference = requested_artifact_reference,
        captured_etag = requested_etag,
        captured_last_modified = requested_last_modified,
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
        requested_worker_id, transition_reason
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT, TEXT)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT, TEXT)
    TO edgartools_acquisition_worker;
ALTER FUNCTION finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT, TEXT)
    OWNER TO edgartools_acquisition_owner;
