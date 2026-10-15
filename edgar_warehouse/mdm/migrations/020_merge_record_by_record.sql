-- The Merge Stage merges record by record (rebuild-priorities ticket 77;
-- operator, 2026-10-14: "Approve" and "Same transaction"). A batch reads only
-- the masters its records and decisions touch, and their links, so a match
-- proposal no longer needs a snapshot of everything it read: the proposal is
-- recorded and its batch saved in one transaction, under the Merge Stage lock,
-- and nothing can change in between. A proposal recorded earlier and applied
-- later (`apply_assessment`) is computed again under the lock, and the save
-- refuses it unless it writes exactly the proposal's effects.
--   save_batch: no refusal of a proposal recorded in the same transaction, no
--     snapshot check; the effects check stays.
--   record_match_proposal: a ready proposal needs its effects, not a scope or
--     a snapshot.
--   supersede_match_proposal: a ready proposal not yet applied is superseded
--     when its caller found it stale (its effects no longer match), with no
--     snapshot to compare.
--   outbox_delivery: a changed record's body is taken from the batch's
--     projections expanded once, not read out of the whole batch document once
--     per record (each read decompressed the document again: 81 of 88 seconds
--     of a 1,000-record ownership save). The payload, and so its hash, is the
--     same.
--   match_proposal_snapshot: dropped.

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
    IF root_run IS NULL
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
        jsonb_typeof(b->'effects') IS DISTINCT FROM 'object'
        OR b->'effects'->>'policy_digest' IS DISTINCT FROM b->'command'->>'policy_digest'
        OR b->'effects'->>'batch_id' IS DISTINCT FROM b->'command'->>'batch_id') THEN
        RAISE EXCEPTION 'Ready assessment requires proposed effects';
    END IF;
    -- The effects are the save request itself, which save_batch checks by this
    -- hash; storing them whole doubled every proposal (013).
    IF b ? 'effects' THEN
        b := (b - 'effects') || jsonb_build_object('effects_sha256',
            encode(sha256(convert_to((b->'effects')::text,'UTF8')),'hex'));
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

CREATE OR REPLACE FUNCTION mdm.supersede_match_proposal(key text, root_run uuid) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE b jsonb;
BEGIN
    PERFORM pg_advisory_xact_lock(730234);
    SELECT body INTO b FROM mdm.match_proposal WHERE assessment_id=key;
    IF root_run IS NULL OR b IS NULL THEN RAISE EXCEPTION 'Unknown assessment or run'; END IF;
    IF b->>'outcome'='ready'
       AND NOT EXISTS(SELECT 1 FROM mdm.match_proposal_event WHERE assessment_id=key AND event IN ('applied','superseded')) THEN
        INSERT INTO mdm.match_proposal_event(assessment_id,run_id,event) VALUES(key,root_run,'superseded');
    END IF;
END;
$$;

CREATE OR REPLACE VIEW mdm.outbox_delivery AS
 SELECT o.batch_id,
    o.consumer,
    COALESCE(o.payload,
        CASE WHEN o.contract_version = 3 THEN
        jsonb_build_object('contract_version', 3, 'generation', b.generation, 'run_id', b.run_id,
            'policy_digest', b.effects ->> 'policy_digest',
            'forced', coalesce((b.effects ->> 'forced')::boolean, false),
            'objects', coalesce((SELECT jsonb_agg(p.value || jsonb_build_object('change', c.change) ORDER BY c.position)
                                 FROM jsonb_array_elements(b.effects -> 'projections') WITH ORDINALITY p(value, position)
                                 JOIN mdm.batch_change c ON c.batch_id = b.batch_id AND c.position = p.position),
                                '[]'::jsonb))
        ELSE
        jsonb_build_object('contract_version', 2, 'generation', b.generation, 'run_id', b.run_id,
                           'policy_digest', b.effects ->> 'policy_digest', 'objects', b.effects -> 'projections')
        || CASE WHEN o.consumer = 'journal' THEN jsonb_build_object('effects', b.effects) ELSE '{}'::jsonb END
        END) AS payload
   FROM mdm.outbox o
     JOIN mdm.batch b USING (batch_id);


DROP FUNCTION mdm.match_proposal_snapshot(jsonb);

COMMENT ON FUNCTION mdm.save_batch(text, uuid) IS
    'Save a batch: a batch with a join or merge needs a ready match proposal, not yet applied, whose effects are exactly this batch (recorded earlier, or first in the same transaction, 020); then write_batch, and the proposal marked applied. Every other open proposal of the batch is superseded.';
COMMENT ON FUNCTION mdm.record_match_proposal(text, uuid) IS
    'Record a match proposal (proposed joins and merges), as ready or rejected; its effects are kept as their sha256. Returns its id. No cap on its size (019); no snapshot (020).';
COMMENT ON FUNCTION mdm.supersede_match_proposal(text, uuid) IS
    'Mark a ready match proposal, not yet applied, superseded: its batch, computed again, no longer writes its effects (020).';
