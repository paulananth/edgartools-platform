-- Two ticket 04 safety items, in the one function that commits a new batch
-- (company mastering ticket 04, closed under ticket 15).
--
-- 1. A rule's new Company is never published at or before another of its
--    kind. The earliest-published Company survives a merge (identity.replay),
--    and a caller supplies a batch's as_of, so a late or backdated batch
--    could create the Company that later wins every merge. The Merge Stage
--    publishes a rule's new Company at the batch's as_of or just after the
--    newest identity of its kind already stored, whichever is later
--    (binding.publish_floor), and re-proposes under its lock when a newer one
--    has committed since. A late batch still creates its Company. This is the
--    last guard: a rule-created identity at or before the newest stored
--    identity of its kind is refused. A steward's identity states its own
--    time and is not checked. Technical decision, reversible (Claude,
--    2026-09-26).
--
-- 2. An orphaned assessment is closed when its batch commits. A crash
--    between an assessment and its apply leaves a `ready` assessment no one
--    applies; the next run proposes again with fresh ids and commits the
--    batch. Committing a batch now marks every other unapplied `ready`
--    assessment for that batch superseded, in the same transaction. An
--    orphan whose batch never commits stays open, and orphans of batches
--    committed before this migration are not backfilled (a backfill would
--    write run ids that never ran into an immutable log; no shared store has
--    been migrated).
--
-- 028's commit_batch is restated whole (not edited by text fragment); the
-- two additions are marked. CREATE OR REPLACE keeps its owner and grants.
CREATE OR REPLACE FUNCTION mdm_v2.commit_batch(request_text text,root_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE r jsonb := request_text::jsonb; b jsonb; result jsonb; key text := r->>'assessment_id';
BEGIN
    PERFORM pg_advisory_xact_lock(730234);
    -- Previously committed commands remain replayable, including pre-028 ones.
    IF EXISTS(SELECT 1 FROM mdm_v2.batch WHERE batch_id=r->>'batch_id') THEN
        RETURN mdm_v2.commit_batch_evidence(request_text,root_run);
    END IF;
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(r->'decisions') d WHERE d->>'operation' IN ('bind','merge')) THEN
        SELECT body INTO b FROM mdm_v2.assessment WHERE assessment_id=key;
        IF b IS NULL OR b->>'outcome' IS DISTINCT FROM 'ready'
           OR EXISTS(SELECT 1 FROM mdm_v2.assessment WHERE assessment_id=key AND created_xid=pg_current_xact_id())
           OR EXISTS(SELECT 1 FROM mdm_v2.assessment_event WHERE assessment_id=key AND event IN ('applied','superseded')) THEN
            RAISE EXCEPTION 'Identity decision requires a ready assessment';
        END IF;
        IF (r - 'assessment_id' - 'expected_generation') IS DISTINCT FROM b->'effects' THEN
            RAISE EXCEPTION 'Command differs from assessed effects';
        END IF;
        IF b->>'snapshot' IS DISTINCT FROM mdm_v2.assessment_snapshot(b->'scope') THEN
            RAISE EXCEPTION USING ERRCODE='P0A01', MESSAGE='Stale identity assessment';
        END IF;
        -- 040 (1): a rule's new Company is published after every stored
        -- identity of its kind.
        IF EXISTS(
            SELECT 1 FROM jsonb_array_elements(coalesce(b->'automatic'->'identities','[]')) i
            WHERE (i->>'published_at')::timestamptz
                  <= (SELECT max(published_at) FROM mdm_v2.identity WHERE kind=i->>'kind')) THEN
            RAISE EXCEPTION 'A new Company would be published at or before an identity of its kind already stored';
        END IF;
    ELSIF key IS NOT NULL THEN
        RAISE EXCEPTION 'Assessment supplied without an identity proposal';
    END IF;
    result := mdm_v2.commit_batch_evidence(request_text,root_run);
    IF key IS NOT NULL THEN
        INSERT INTO mdm_v2.assessment_event(assessment_id,run_id,event,batch_id)
            VALUES(key,root_run,'applied',r->>'batch_id');
    END IF;
    -- 040 (2): the batch is committed, so no other assessment of it can
    -- apply; close every one still open.
    INSERT INTO mdm_v2.assessment_event(assessment_id,run_id,event,batch_id)
    SELECT a.assessment_id, root_run, 'superseded', r->>'batch_id'
    FROM mdm_v2.assessment a
    WHERE a.body->'command'->>'batch_id' = r->>'batch_id'
      AND a.assessment_id IS DISTINCT FROM key
      AND a.body->>'outcome' = 'ready'
      AND NOT EXISTS(SELECT 1 FROM mdm_v2.assessment_event e
                     WHERE e.assessment_id = a.assessment_id
                       AND e.event IN ('applied','superseded'))
    ON CONFLICT DO NOTHING;
    RETURN result;
END;
$$;

-- The newest publish time of a kind is read when a rule proposes a new
-- Company and again under the Merge Stage lock.
CREATE INDEX clean_identity_kind_published_at ON mdm_v2.identity(kind, published_at);

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mdm_v2 FROM PUBLIC;
