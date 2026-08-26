-- Ticket 25 bullet 1/2: different bytes under one immutable Bronze identity
-- are recorded (both retained -- the conflicting payload's own quarantine
-- object already exists in Bronze by the time this row is written, see
-- object_storage.ImmutableContentConflictError) rather than picked by
-- arrival order or silently overwritten. Repair (materializing a REPAIR
-- child source_revision, or closing the conflict in favor of what's already
-- there) is a processing-lifecycle action -- edgartools_acquisition_processor
-- gets the operational GRANTs, same as it already does for source_revision.
--
-- Ownership stays with edgartools_acquisition_owner (013's role), NOT
-- edgartools_acquisition_processor: `application` is a MEMBER of the five
-- *operational* roles from 013 (coordinator/worker/operator/processor/
-- silver_finalizer) but never of edgartools_acquisition_owner itself, and
-- CREATE on schema public was only ever granted to the owner role -- 013's
-- own source_revision table follows the identical shape (owned by
-- edgartools_acquisition_owner, GRANTed SELECT/INSERT to
-- edgartools_acquisition_processor, never owned by it). An earlier version
-- of this file tried transferring ownership to edgartools_acquisition_
-- processor directly and reproduced a live `permission denied for schema
-- public` running `application`'s own migration path -- processor was never
-- meant to CREATE tables, only read/write ones the owner already created.
-- This file's own wrapper (runtime.py's
-- _apply_source_evidence_conflict_migration) therefore mirrors
-- _apply_acquisition_ledger_migration's shape exactly: gated on
-- pg_has_role(current_user, 'edgartools_acquisition_owner', 'MEMBER'),
-- every statement below runs under `SET LOCAL ROLE edgartools_acquisition_owner`.

CREATE TABLE IF NOT EXISTS source_evidence_conflict (
    conflict_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_family TEXT,
    logical_source_key TEXT,
    relative_path TEXT NOT NULL,
    existing_content_hash TEXT NOT NULL,
    new_content_hash TEXT NOT NULL,
    quarantine_bronze_reference TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'PENDING',
    repair_revision_id UUID REFERENCES source_revision(revision_id),
    resolved_at TIMESTAMPTZ,
    operator_authorization_reference TEXT,
    resolution_reason TEXT,
    CONSTRAINT uq_source_evidence_conflict_quarantine UNIQUE (quarantine_bronze_reference),
    CONSTRAINT ck_source_evidence_conflict_status
        CHECK (status IN ('PENDING','REPAIRED')),
    CONSTRAINT ck_source_evidence_conflict_resolution_complete CHECK (
        (status = 'REPAIRED') = (
            repair_revision_id IS NOT NULL AND resolved_at IS NOT NULL AND
            operator_authorization_reference IS NOT NULL AND resolution_reason IS NOT NULL
        )
    )
);

-- Documents the intended read pattern (look up open conflicts for one
-- identity); not itself a uniqueness guard -- uq_source_evidence_conflict_
-- quarantine above is what prevents a duplicate row for a replayed
-- detection of the same conflict.
CREATE INDEX IF NOT EXISTS ix_source_evidence_conflict_relative_path_pending
    ON source_evidence_conflict (relative_path)
    WHERE status = 'PENDING';

GRANT SELECT, INSERT,
    UPDATE (status, repair_revision_id, resolved_at, operator_authorization_reference, resolution_reason)
    ON source_evidence_conflict TO edgartools_acquisition_processor;
GRANT SELECT ON source_evidence_conflict TO
    edgartools_acquisition_coordinator, edgartools_acquisition_worker,
    edgartools_acquisition_operator, edgartools_acquisition_silver_finalizer;

ALTER TABLE source_evidence_conflict OWNER TO edgartools_acquisition_owner;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'application') THEN
        REVOKE ALL PRIVILEGES ON source_evidence_conflict FROM application;
    END IF;
END;
$$;
