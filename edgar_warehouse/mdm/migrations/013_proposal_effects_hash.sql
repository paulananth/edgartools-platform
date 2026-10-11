-- A match proposal stores the hash of its effects, not a second copy of them
-- (MDM batch size ticket, 2026-10-10).
--
-- A proposal held the save request twice: once as the caller's `command`, once
-- as `effects`. `effects` is read only to check that the batch saved equals the
-- batch assessed, so a SEC batch's 6.1 MB request made a 9.6 MB proposal, and a
-- GLEIF batch of 1,000 records a 19.7 MB one, over the 16 MB bound. The
-- proposal now keeps `effects_sha256`, the sha256 of the effects' jsonb text,
-- and save_batch compares the request's hash to it. A proposal stored before
-- this keeps its `effects` and is checked as before. The proposal as sent may
-- be up to 64 MB; as stored, 16 MB (`edgar_warehouse/mdm/clean/limits.py`).
--
-- The hash compares jsonb text, which is stricter than jsonb equality only for
-- numbers written two ways (1.0 and 1); the request and its effects are built
-- from one Python object, so such a pair is refused, never wrongly accepted.
-- A proposal recorded before this migration and recorded again after it (the
-- same text) is refused as a digest collision; it is assessed again instead.

CREATE OR REPLACE FUNCTION mdm.save_batch(request_text text, root_run uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE r jsonb := request_text::jsonb; b jsonb; result jsonb; key text := r->>'assessment_id';
BEGIN
    PERFORM pg_advisory_xact_lock(730234);
    -- A batch already saved stays replayable.
    IF EXISTS(SELECT 1 FROM mdm.batch WHERE batch_id=r->>'batch_id') THEN
        RETURN mdm.write_batch(request_text,root_run);
    END IF;
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(r->'decisions') d WHERE d->>'operation' IN ('bind','merge')) THEN
        SELECT body INTO b FROM mdm.match_proposal WHERE assessment_id=key;
        IF b IS NULL OR b->>'outcome' IS DISTINCT FROM 'ready'
           OR EXISTS(SELECT 1 FROM mdm.match_proposal WHERE assessment_id=key AND created_xid=pg_current_xact_id())
           OR EXISTS(SELECT 1 FROM mdm.match_proposal_event WHERE assessment_id=key AND event IN ('applied','superseded')) THEN
            RAISE EXCEPTION 'Identity decision requires a ready assessment';
        END IF;
        -- A proposal keeps the hash of its effects (013); one stored before keeps them whole.
        IF (b ? 'effects_sha256' AND
                encode(sha256(convert_to((r - 'assessment_id' - 'expected_generation')::text,'UTF8')),'hex')
                IS DISTINCT FROM b->>'effects_sha256')
           OR (NOT b ? 'effects_sha256' AND
                (r - 'assessment_id' - 'expected_generation') IS DISTINCT FROM b->'effects') THEN
            RAISE EXCEPTION 'Command differs from assessed effects';
        END IF;
        IF b->>'snapshot' IS DISTINCT FROM mdm.match_proposal_snapshot(b->'scope') THEN
            RAISE EXCEPTION USING ERRCODE='P0A01', MESSAGE='Stale identity assessment';
        END IF;
        -- A rule's new Company is published after every stored master
        -- entity of its kind.
        IF EXISTS(
            SELECT 1 FROM jsonb_array_elements(coalesce(b->'automatic'->'identities','[]')) i
            WHERE (i->>'published_at')::timestamptz
                  <= (SELECT max(published_at) FROM mdm.master_entity WHERE kind=i->>'kind')) THEN
            RAISE EXCEPTION 'A new Company would be published at or before an identity of its kind already stored';
        END IF;
    ELSIF key IS NOT NULL THEN
        RAISE EXCEPTION 'Assessment supplied without an identity proposal';
    END IF;
    result := mdm.write_batch(request_text,root_run);
    IF key IS NOT NULL THEN
        INSERT INTO mdm.match_proposal_event(assessment_id,run_id,event,batch_id)
            VALUES(key,root_run,'applied',r->>'batch_id');
    END IF;
    -- The batch is saved, so no other match proposal of it can
    -- apply; close every one still open.
    INSERT INTO mdm.match_proposal_event(assessment_id,run_id,event,batch_id)
    SELECT a.assessment_id, root_run, 'superseded', r->>'batch_id'
    FROM mdm.match_proposal a
    WHERE a.body->'command'->>'batch_id' = r->>'batch_id'
      AND a.assessment_id IS DISTINCT FROM key
      AND a.body->>'outcome' = 'ready'
      AND NOT EXISTS(SELECT 1 FROM mdm.match_proposal_event e
                     WHERE e.assessment_id = a.assessment_id
                       AND e.event IN ('applied','superseded'))
    ON CONFLICT DO NOTHING;
    RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION mdm.record_match_proposal(body_text text, root_run uuid) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE b jsonb := body_text::jsonb; key text := encode(sha256(convert_to(body_text,'UTF8')),'hex');
    caller jsonb := coalesce(b->'command'->'decisions','[]'::jsonb);
    automatic jsonb := coalesce(b->'automatic'->'decisions','[]'::jsonb);
BEGIN
    IF root_run IS NULL OR octet_length(body_text)>67108864
       OR NOT (b ?& ARRAY['version','command','outcome','rule_version'])
       OR b->>'version' IS DISTINCT FROM '1'
       OR b->>'outcome' NOT IN ('ready','rejected') OR b->>'outcome' IS NULL
       OR jsonb_typeof(caller) IS DISTINCT FROM 'array'
       OR jsonb_typeof(automatic) IS DISTINCT FROM 'array'
       OR jsonb_array_length(caller) > 1000
       OR jsonb_array_length(automatic) > 1000
       OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(caller || automatic) d WHERE d->>'operation' IN ('bind','merge')) THEN
        RAISE EXCEPTION 'Invalid or unbounded identity assessment';
    END IF;
    IF b->>'outcome'='ready' AND (
        jsonb_typeof(b->'effects') IS DISTINCT FROM 'object' OR NOT (b ?& ARRAY['scope','snapshot'])
        OR b->'effects'->>'policy_digest' IS DISTINCT FROM b->'command'->>'policy_digest'
        OR b->'effects'->>'batch_id' IS DISTINCT FROM b->'command'->>'batch_id') THEN
        RAISE EXCEPTION 'Ready assessment requires proposed effects and dependency snapshot';
    END IF;
    -- The effects are the save request itself, which save_batch checks by this
    -- hash; storing them whole doubled every proposal (013).
    IF b ? 'effects' THEN
        b := (b - 'effects') || jsonb_build_object('effects_sha256',
            encode(sha256(convert_to((b->'effects')::text,'UTF8')),'hex'));
    END IF;
    IF octet_length(b::text) > 16777216 THEN
        RAISE EXCEPTION 'Invalid or unbounded identity assessment: % bytes stored', octet_length(b::text);
    END IF;
    INSERT INTO mdm.match_proposal(assessment_id,body) VALUES(key,b) ON CONFLICT DO NOTHING;
    IF NOT EXISTS(SELECT 1 FROM mdm.match_proposal WHERE assessment_id=key AND body=b) THEN
        RAISE EXCEPTION 'Assessment digest collision';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM mdm.match_proposal_event WHERE assessment_id=key) THEN
        INSERT INTO mdm.match_proposal_event(assessment_id,run_id,event)
            VALUES(key,root_run,b->>'outcome') ON CONFLICT DO NOTHING;
    END IF;
    INSERT INTO mdm.match_proposal_event(assessment_id,run_id,event)
        VALUES(key,root_run,'observed') ON CONFLICT DO NOTHING;
    RETURN key;
END;
$$;

COMMENT ON FUNCTION mdm.record_match_proposal(text, uuid) IS
    'Record a match proposal (proposed joins and merges) with its snapshot, as ready or rejected; its effects are kept as their sha256. Returns its id.';
