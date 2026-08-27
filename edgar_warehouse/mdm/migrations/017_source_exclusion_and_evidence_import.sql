-- Ticket 34 (change-propagation map): exclusion reason + evidence import.
--
-- Two independent, unrelated mechanisms bundled into one migration file
-- purely because both need owner-gated DDL against the same
-- edgartools_acquisition_owner-owned schema (013's role, not a new one --
-- see 015_source_evidence_conflict.sql's own comment for why CREATE/ALTER
-- on schema public was only ever granted to the owner role):
--
-- 1. exclusion_reason on source_fetch_decision -- OPERATOR_EXCLUDED already
--    required operator_authorization_reference (proof of *who* authorized
--    an exclusion); this adds the human-readable *why*, so an exclusion is
--    reasoned, not just authorized. Scope is already fully captured by the
--    row's own existing source_family/logical_source_key/candidate_id
--    columns -- no new scope concept or table needed, since an exclusion is
--    a one-shot terminal classification of a single immutable Fetch
--    Decision, not an entity with its own independent lifecycle the way
--    source_evidence_conflict's PENDING/REPAIRED state machine is.
--
-- 2. source_evidence_import -- checksum-verified Bronze evidence imported
--    from another environment/account, with preserved source lineage.
--    Unlike a conflict (detected passively, may predate ledger context),
--    an import is a deliberate operator action with full context up front,
--    so source_family/logical_source_key are NOT NULL here.

ALTER TABLE source_fetch_decision ADD COLUMN IF NOT EXISTS exclusion_reason TEXT;

-- 013's own source_change_status view (the real "Source Change Status"
-- bullet 1 names -- ad-hoc operator SQL access, per that view's own
-- comment) already exposes operator_authorization_reference; without this,
-- an operator querying it directly could see *that* something was
-- excluded but never *why*. CREATE OR REPLACE preserves the view's
-- existing owner/GRANTs (Postgres re-checks and re-approves an
-- OR REPLACE against the original privileges, so no new GRANT statement is
-- needed here) -- but Postgres also requires every pre-existing column to
-- keep its exact name AND position; a new column may only be appended at
-- the end (reproduced live: putting it mid-list raised "cannot change name
-- of view column 'next_action' to 'exclusion_reason'", since Postgres reads
-- a mid-list insertion as a rename of whatever was at that position).
-- source_change_status_detail is deliberately left alone -- it never
-- carried operator_authorization_reference either; its own scope is
-- revision/processing/expected-producer pipeline state, not decision-level
-- authorization metadata.
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
    decision.verified_evidence_reference,
    decision.scope_proof_reference,
    decision.operator_authorization_reference,
    CASE work.fetch_state
        WHEN 'LEASED' THEN 'FETCH_SOURCE'
        WHEN 'CAPTURED' THEN 'MATERIALIZE_SOURCE_REVISION'
        WHEN 'FAILED' THEN 'RETRY_FETCH'
        ELSE decision.next_action
    END AS next_action,
    decision.next_eligible_at,
    decision.created_at,
    decision.exclusion_reason
FROM source_fetch_decision AS decision
LEFT JOIN source_fetch_work AS work
  ON work.decision_id = decision.decision_id;

-- Postgres has no `ADD CONSTRAINT IF NOT EXISTS` for CHECK constraints --
-- guard via pg_constraint so a rerun by a role with real owner membership
-- (unlike `application`, which never reaches this file at all -- see the
-- self-managing wrapper's own rerun-skip gate) doesn't hit a bare
-- "constraint already exists" error.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_source_fetch_decision_exclusion_reason'
    ) THEN
        ALTER TABLE source_fetch_decision
            ADD CONSTRAINT ck_source_fetch_decision_exclusion_reason
            CHECK (fetch_disposition <> 'OPERATOR_EXCLUDED' OR exclusion_reason IS NOT NULL);
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS source_evidence_import (
    import_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_family TEXT NOT NULL,
    logical_source_key TEXT NOT NULL,
    source_environment TEXT NOT NULL,
    source_bronze_reference TEXT NOT NULL,
    expected_checksum TEXT NOT NULL,
    raw_evidence_hash TEXT NOT NULL,
    local_bronze_reference TEXT NOT NULL,
    operator_authorization_reference TEXT NOT NULL,
    reason TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_source_evidence_import_source_reference
        UNIQUE (source_environment, source_bronze_reference)
);

-- import_evidence (evidence_import.py) runs as DecisionOwnerRole.
-- ACQUISITION_OPERATOR -- the same role OPERATOR_REQUEST/OPERATOR_EXCLUDED
-- fetch decisions already require -- not a new role: an import is a
-- deliberate, explicit operator action, same class of responsibility.
GRANT SELECT, INSERT ON source_evidence_import TO edgartools_acquisition_operator;
GRANT SELECT ON source_evidence_import TO
    edgartools_acquisition_coordinator, edgartools_acquisition_worker,
    edgartools_acquisition_processor, edgartools_acquisition_silver_finalizer;

ALTER TABLE source_evidence_import OWNER TO edgartools_acquisition_owner;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'application') THEN
        REVOKE ALL PRIVILEGES ON source_evidence_import FROM application;
    END IF;
END;
$$;

-- Ticket 30/44 sibling gap (see 015_source_evidence_conflict.sql's own
-- identical block): application also carries an ambient, platform-managed
-- snowflake_write membership that independently grants full DML, never
-- revoked by the block above alone.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'snowflake_write') THEN
        REVOKE ALL PRIVILEGES ON source_evidence_import FROM snowflake_write;
    END IF;
END;
$$;
