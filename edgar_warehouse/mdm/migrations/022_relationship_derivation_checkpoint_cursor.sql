-- mdm-relationship-versioning-gap wayfinder map, Ticket 01: a persisted,
-- resumable CIK/CRD-range cursor for INSTITUTIONAL_HOLDS/MANAGES_FUND's
-- capped batch loops, decoupled from the stable watermark_value those
-- loops filter against.
--
-- Root cause this fix closes: _derive_institutional_holds/_derive_manages_fund
-- always restarted CIK/CRD-range iteration from the beginning on every
-- invocation. Every run is capped by --target-per-type, so once backlog
-- exceeds one run's budget, the watermark could only ever creep forward
-- through whatever slice of CIK/CRD space the first N batches before the
-- cap happened to cover -- confirmed live 2026-09-08: INSTITUTIONAL_HOLDS'
-- watermark sat 6+ weeks stale despite runs executing continuously.
--
-- cursor_value: resume position in CIK/CRD space for an in-progress sweep;
-- NULL means "no sweep in progress, start fresh from the beginning."
-- pending_watermark_value: the running max watermark value accumulated
-- across the CURRENT in-progress sweep, since a sweep may span many
-- separate process runs and this must survive between them.
--
-- watermark_value's NOT NULL constraint is relaxed: a checkpoint row can
-- now legitimately exist (holding real cursor_value/pending_watermark_value
-- progress) before any sweep has ever fully completed, in which case
-- watermark_value stays NULL -- "scan everything" semantics, identical to
-- no checkpoint row existing at all (get_relationship_watermark already
-- returns None for a NULL watermark_value the same way it does for no
-- row). Every other relationship type's checkpoint writes (via the
-- pre-existing, unchanged advance_relationship_watermark) never write a
-- NULL watermark_value, so this relaxation doesn't affect their behavior.
ALTER TABLE mdm_relationship_derivation_checkpoint
    ALTER COLUMN watermark_value DROP NOT NULL;

ALTER TABLE mdm_relationship_derivation_checkpoint
    ADD COLUMN IF NOT EXISTS cursor_value TEXT;

ALTER TABLE mdm_relationship_derivation_checkpoint
    ADD COLUMN IF NOT EXISTS pending_watermark_value TEXT;
