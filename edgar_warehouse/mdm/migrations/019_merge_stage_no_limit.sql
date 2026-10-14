-- The Merge Stage has no limit (rebuild-priorities ticket 74; operator,
-- 2026-10-14: "merge stage should have no limit"). A batch is replayed with
-- everything it is connected to, however large: the ownership feed's insider
-- network is one connected group past the old 10,000 cap. So the save request,
-- the match proposal and its snapshot refuse nothing by size any more:
--   write_batch: no 16 MiB request cap and no 10,000-projection cap;
--   record_match_proposal: no 64 MiB sent and no 16 MiB stored cap;
--   match_proposal_snapshot: no cap on its keys, sources or rows.
-- Kept: a batch's own records (at most 1,000 readings with set-aside records,
-- and 1,000 decisions), which is how mdm.prepare cuts a run's input, not a
-- refusal of work. Each body is its latest one (018, 013, 012) with only those
-- checks removed; CREATE OR REPLACE resets a function's settings, so the
-- snapshot restates its plan setting (it is in the copied header).

CREATE OR REPLACE FUNCTION mdm.write_batch(request_text text, root_run uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE r jsonb := request_text::jsonb; item jsonb; src mdm.dataset%ROWTYPE;
    result jsonb; old mdm.set_aside_record%ROWTYPE;
    h text := encode(sha256(convert_to(request_text,'UTF8')),'hex');
    prior mdm.batch%ROWTYPE;
    current_generation bigint;
    next_generation bigint;
    pos bigint;
    required jsonb;
    delivered jsonb;
    wrote boolean := false;  -- this batch changed something
    existed boolean;         -- the projected object was current before this batch
    n bigint := 0;           -- the projection's position in the batch, from 1
BEGIN
    IF coalesce(jsonb_array_length(r->'deferred'),0)>1000 OR
       coalesce(jsonb_array_length(r->'deferred'),0)+coalesce(jsonb_array_length(r->'assertions'),0)>1000 THEN
        RAISE EXCEPTION 'Unbounded source records';
    END IF;
    IF (r ? 'source_accounting' OR coalesce(jsonb_array_length(r->'deferred'),0)>0)
       AND r->'source_accounting' IS DISTINCT FROM jsonb_build_object(
           'normalized',coalesce(jsonb_array_length(r->'assertions'),0),
           'deferred',coalesce(jsonb_array_length(r->'deferred'),0),
           'total',coalesce(jsonb_array_length(r->'assertions'),0)+coalesce(jsonb_array_length(r->'deferred'),0)) THEN
        RAISE EXCEPTION 'Invalid source accounting';
    END IF;
    -- Save the batch itself: bounds, the batch row, source readings, master
    -- entities, decisions, current records, the checkpoint and the outbox.
    -- A batch saved before (same key, same content) is not written again.
    <<core>>
    BEGIN
        IF root_run IS NULL
           OR coalesce(jsonb_array_length(r->'assertions'),0) > 1000
           OR coalesce(jsonb_array_length(r->'decisions'),0) > 1000 THEN
            RAISE EXCEPTION 'Invalid or unbounded batch';
        END IF;
        IF coalesce(r->>'source_family','')<>'' AND NOT EXISTS(
            SELECT 1 FROM mdm.dataset WHERE body->>'family'=r->>'source_family'
              AND body->'publication_families' ? (r->>'publication_family')) THEN
            RAISE EXCEPTION 'Unknown publication family contract';
        END IF;
        PERFORM pg_advisory_xact_lock(730234);
        SELECT * INTO prior FROM mdm.batch WHERE batch_id = r->>'batch_id';
        IF FOUND THEN
            IF prior.request_hash <> h THEN RAISE EXCEPTION 'Batch key reused with different content'; END IF;
            INSERT INTO mdm.run_batch VALUES(root_run,prior.batch_id) ON CONFLICT DO NOTHING;
            -- Since 017 a batch has outbox rows only when it changed something
            -- (every policy requires a consumer); one saved before has them always.
            result := jsonb_build_object('batch_id',prior.batch_id,'generation',prior.generation,'duplicate',true,
                'changed',EXISTS(SELECT 1 FROM mdm.outbox WHERE batch_id=prior.batch_id));
            EXIT core;
        END IF;
        SELECT coalesce(max(generation),0) INTO current_generation FROM mdm.batch;
        IF (r->>'expected_generation')::bigint IS DISTINCT FROM current_generation THEN
            RAISE EXCEPTION 'Stale generation';
        END IF;
        SELECT coalesce((SELECT position FROM mdm.checkpoint WHERE consumer=r->>'consumer'
            AND source_family=coalesce(r->>'source_family','')
            AND publication_family=coalesce(r->>'publication_family','')),0) INTO pos;
        IF (r->>'expected_checkpoint')::bigint IS DISTINCT FROM pos
           OR (r->>'checkpoint')::bigint IS NULL OR (r->>'checkpoint')::bigint <= pos THEN
            RAISE EXCEPTION 'Stale or nonadvancing checkpoint';
        END IF;
        SELECT body->'required_consumers' INTO required FROM mdm.policy WHERE digest=r->>'policy_digest';
        IF required IS NULL OR jsonb_array_length(required)=0 THEN RAISE EXCEPTION 'Missing frozen consumer contract'; END IF;
        next_generation := current_generation+1;
        INSERT INTO mdm.batch VALUES(r->>'batch_id',h,root_run,r->>'policy_digest',next_generation,
            r->>'consumer',(r->>'checkpoint')::bigint,r,now());
        INSERT INTO mdm.run_batch VALUES(root_run,r->>'batch_id');
        FOR item IN SELECT value FROM jsonb_array_elements(r->'assertions') LOOP
            SELECT * INTO src FROM mdm.dataset WHERE source_code=item->>'source_code';
            IF NOT FOUND OR src.body->'registry_evidence'->>'status' IS DISTINCT FROM 'active'
               OR src.body->'registry_evidence'->>'version_id' IS DISTINCT FROM src.registry_version::text
               OR src.body->'registry_evidence'->>'source_family' IS DISTINCT FROM src.body->>'family' THEN
                RAISE EXCEPTION 'Dataset has no pinned registry authority';
            END IF;
            IF NOT EXISTS(SELECT 1 FROM mdm.dataset_mapping m
                WHERE m.source_code=item->>'source_code'
                  AND m.mapping_version=coalesce((item->>'mapping_version')::bigint,1)
                  AND m.body->>'schema_version' IS NOT DISTINCT FROM item->>'schema_version') THEN
                RAISE EXCEPTION 'Unsupported source schema';
            END IF;
            IF EXISTS(SELECT 1 FROM mdm.source_reading a WHERE a.assertion_id=item->>'assertion_id' AND a.body<>item) THEN
                RAISE EXCEPTION 'Assertion identity collision';
            END IF;
            INSERT INTO mdm.source_reading(assertion_id,source_code,record_key,publication_key,
              revision,effective_at,body,batch_id,mapping_version)
              VALUES(item->>'assertion_id',item->>'source_code',item->>'record_key',
              item->>'publication_key',(item->>'revision')::bigint,(item->>'effective_at')::timestamptz,item,r->>'batch_id',
              coalesce((item->>'mapping_version')::bigint,1))
              ON CONFLICT(assertion_id) DO NOTHING;
            IF FOUND THEN wrote := true; END IF;
        END LOOP;
        -- A deferred record is stored after this block; a new one is a change
        -- (the journal sends the whole batch, deferred records too).
        IF EXISTS(SELECT 1 FROM jsonb_array_elements(coalesce(r->'deferred','[]')) d
                  WHERE NOT EXISTS(SELECT 1 FROM mdm.set_aside_record s WHERE s.deferred_id=d->>'deferred_id')) THEN
            wrote := true;
        END IF;
        IF coalesce(jsonb_array_length(r->'identities'),0)>0
           OR coalesce(jsonb_array_length(r->'decisions'),0)>0 THEN
            wrote := true;
        END IF;
        FOR item IN SELECT value FROM jsonb_array_elements(r->'identities') LOOP
            INSERT INTO mdm.master_entity VALUES((item->>'entity_id')::uuid,item->>'kind',
              (item->>'published_at')::timestamptz,r->>'batch_id');
        END LOOP;
        FOR item IN SELECT value FROM jsonb_array_elements(r->'decisions') LOOP
            IF nullif(item->>'actor','') IS NULL OR nullif(item->>'reason','') IS NULL THEN
                RAISE EXCEPTION 'Decision requires actor and reason';
            END IF;
            INSERT INTO mdm.decision VALUES(item->>'decision_id',item->>'operation',item,r->>'batch_id');
        END LOOP;
        FOR item IN SELECT value FROM jsonb_array_elements(r->'projections') LOOP
            n := n+1;
            -- A Company is kept in the Company table only. The batch row
            -- above holds this commit's generation; now() is its created_at.
            IF item->>'object_type'='entity' AND item->'body'->>'kind'='company' THEN
                existed := EXISTS(SELECT 1 FROM mdm.company WHERE entity_id=(item->'body'->>'entity_id')::uuid AND valid_to IS NULL)
                        OR EXISTS(SELECT 1 FROM mdm.company_alias WHERE alias_id=(item->'body'->>'entity_id')::uuid AND valid_to IS NULL);
                IF mdm.record_company_version(item->'body',r->>'batch_id',now()) THEN
                    wrote := true;
                    INSERT INTO mdm.batch_change VALUES(r->>'batch_id',n,CASE WHEN existed THEN 'update' ELSE 'insert' END);
                END IF;
            ELSIF NOT EXISTS(SELECT 1 FROM mdm.current_record c WHERE c.object_type=item->>'object_type'
                    AND c.object_id=item->>'object_id' AND c.body=item->'body') THEN
                existed := EXISTS(SELECT 1 FROM mdm.current_record c WHERE c.object_type=item->>'object_type'
                    AND c.object_id=item->>'object_id');
                INSERT INTO mdm.current_record VALUES(item->>'object_type',item->>'object_id',item->'body',r->>'batch_id')
                ON CONFLICT(object_type,object_id) DO UPDATE SET body=excluded.body,batch_id=excluded.batch_id;
                wrote := true;
                INSERT INTO mdm.batch_change VALUES(r->>'batch_id',n,CASE WHEN existed THEN 'update' ELSE 'insert' END);
            END IF;
        END LOOP;
        INSERT INTO mdm.checkpoint(consumer,position,batch_id,source_family,publication_family,committed_publication,continuity_proof)
        VALUES(r->>'consumer',(r->>'checkpoint')::bigint,r->>'batch_id',coalesce(r->>'source_family',''),
            coalesce(r->>'publication_family',''),r->>'committed_publication',r->'continuity_proof')
        ON CONFLICT(consumer,source_family,publication_family) DO UPDATE SET position=excluded.position,
            batch_id=excluded.batch_id,committed_publication=excluded.committed_publication,continuity_proof=excluded.continuity_proof;
        -- An outbox row names its batch; what it sends is built from the batch row
        -- (outbox_delivery), and the row keeps the hash of that.
        -- Outbox rows: the journal's the whole batch, every other consumer's only
        -- its changed records (mdm.queue_outbox).
        PERFORM mdm.queue_outbox(r->>'batch_id',CASE WHEN wrote THEN required ELSE '[]'::jsonb END);
        result := jsonb_build_object('batch_id',r->>'batch_id','generation',next_generation,'duplicate',false,
                                     'changed',wrote);
    END core;
    FOR item IN SELECT value FROM jsonb_array_elements(coalesce(r->'deferred','[]')) LOOP
        IF NOT (item ?& ARRAY['deferred_id','source_code','publication_key','record_locator','schema_version','reason','raw_record','provenance'])
           OR item->>'deferred_id' IS NULL OR item->>'record_locator' IS NULL
           OR item->>'publication_key' IS NULL OR item->>'reason' IS NULL THEN
            RAISE EXCEPTION 'Invalid deferred source evidence';
        END IF;
        SELECT * INTO src FROM mdm.dataset WHERE source_code=item->>'source_code';
        IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM mdm.dataset_mapping m
            WHERE m.source_code=item->>'source_code'
              AND m.body->>'schema_version' IS NOT DISTINCT FROM item->>'schema_version') THEN
            RAISE EXCEPTION 'Unknown deferred dataset contract';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(coalesce(r->'projections','[]')) p
            WHERE p->>'object_type'='review' AND p->>'object_id'=item->>'deferred_id'
              AND p->'body'->>'deferred_id'=item->>'deferred_id'
              AND p->'body'->'open'='true'::jsonb
              AND p->'body'->'blocking'=to_jsonb(NOT (coalesce(src.body->'nonblocking_deferred_reasons','[]'::jsonb) ? (item->>'reason')))
              AND coalesce(p->'body'->'retired','false'::jsonb)='false'::jsonb
        ) THEN
            RAISE EXCEPTION 'Deferred evidence requires an open review with its registered blocking disposition';
        END IF;
        INSERT INTO mdm.set_aside_record VALUES(item->>'deferred_id',item->>'source_code',
            item->>'publication_key',item->>'record_locator',item,r->>'batch_id') ON CONFLICT DO NOTHING;
        SELECT * INTO old FROM mdm.set_aside_record WHERE source_code=item->>'source_code'
            AND publication_key=item->>'publication_key' AND record_locator=item->>'record_locator';
        IF NOT FOUND OR old.body IS DISTINCT FROM item THEN
            RAISE EXCEPTION 'Deferred source publication collision';
        END IF;
    END LOOP;
    -- Inspect only touched reviews. Untouched durable reviews were validated
    -- when committed; rescanning all retained source evidence is unbounded.
    -- No caller may close or reclassify a prior set-aside review.
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(coalesce(r->'projections','[]')) changed
        JOIN mdm.set_aside_record d ON changed->>'object_type'='review'
          AND changed->>'object_id'=d.deferred_id
        JOIN mdm.dataset ds ON ds.source_code=d.source_code
        LEFT JOIN mdm.current_record p ON p.object_type='review' AND p.object_id=d.deferred_id
        WHERE p.body->>'deferred_id' IS DISTINCT FROM d.deferred_id
           OR p.body->'open' IS DISTINCT FROM 'true'::jsonb
           OR p.body->'blocking' IS DISTINCT FROM to_jsonb(NOT (coalesce(ds.body->'nonblocking_deferred_reasons','[]'::jsonb) ? (d.body->>'reason')))
           OR coalesce(p.body->'retired','false'::jsonb) IS DISTINCT FROM 'false'::jsonb
    ) THEN
        RAISE EXCEPTION 'Deferred evidence requires its registered open review disposition';
    END IF;
    IF coalesce((result->>'duplicate')::boolean, false) IS FALSE THEN
        PERFORM mdm.keep_stage(r);
    END IF;
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


CREATE OR REPLACE FUNCTION mdm.match_proposal_snapshot(scope jsonb) RETURNS text
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'mdm'
    SET "TimeZone" TO 'UTC'
    SET plan_cache_mode TO force_custom_plan
    AS $$
DECLARE keys text[]; sources text[]; snapshot jsonb; n integer;
BEGIN
    IF jsonb_typeof(scope->'keys') IS DISTINCT FROM 'array'
       OR jsonb_typeof(scope->'sources') IS DISTINCT FROM 'array'
       THEN
        RAISE EXCEPTION 'Invalid assessment scope';
    END IF;
    SELECT array_agg(value) INTO keys FROM jsonb_array_elements_text(scope->'keys');
    SELECT array_agg(value) INTO sources FROM jsonb_array_elements_text(scope->'sources');
    WITH evidence AS (
        SELECT assertion_id AS id,body FROM mdm.source_reading
        WHERE assertion_id IN (SELECT id FROM mdm.readings_naming(keys) id)
    ), decisions AS (
        SELECT decision_id AS id,body FROM mdm.decision
        WHERE decision_id IN (SELECT id FROM mdm.decisions_naming(keys) id UNION ALL
            SELECT decision_id FROM mdm.decision WHERE operation='retire_source' AND body->>'source_code'=ANY(sources))
    ), identities AS (
        SELECT entity_id::text AS id,to_jsonb(i) AS body FROM mdm.master_entity i
        WHERE entity_id::text=ANY(keys)
    ), projections AS (
        -- Entities are read from current_entity, which holds the
        -- Companies; relationships and reviews stay in current_record.
        SELECT id,body FROM (
            SELECT 'entity/'||object_id AS id,body FROM mdm.current_entity
            WHERE object_id=ANY(keys)
            UNION ALL
            SELECT object_type||'/'||object_id,body FROM mdm.current_record
            WHERE (object_type,object_id) IN (
                SELECT c.object_type,c.object_id FROM unnest(keys) k(key) JOIN mdm.current_record c
                    ON c.object_type='relationship' AND c.body->>'source_id'=k.key
                UNION ALL SELECT c.object_type,c.object_id FROM unnest(keys) k(key) JOIN mdm.current_record c
                    ON c.object_type='relationship' AND c.body->>'target_id'=k.key
                UNION ALL SELECT c.object_type,c.object_id FROM unnest(keys) k(key) JOIN mdm.current_record c
                    ON c.object_type='review' AND c.body->>'entity_id'=k.key
                UNION ALL SELECT c.object_type,c.object_id FROM unnest(keys) k(key) JOIN mdm.current_record c
                    ON c.object_type='review' AND c.body->>'subject'=k.key
                UNION ALL SELECT c.object_type,c.object_id FROM unnest(keys) k(key) JOIN mdm.current_record c
                    ON c.object_type='review' AND c.body->'affected_subjects' ? k.key)
        ) scoped
    ), all_rows AS (
        SELECT 'source_reading' AS kind,id,body FROM evidence UNION ALL
        SELECT 'decision',id,body FROM decisions UNION ALL
        SELECT 'master_entity',id,body FROM identities UNION ALL
        SELECT 'current_record',id,body FROM projections
    ) SELECT count(*),coalesce(jsonb_agg(to_jsonb(a) ORDER BY kind,id),'[]') INTO n,snapshot FROM all_rows a;
    snapshot := jsonb_build_object('rows',snapshot,'checkpoint',coalesce(
        (SELECT position FROM mdm.checkpoint WHERE consumer=scope->>'consumer'
            AND source_family=coalesce(scope->>'source_family','')
            AND publication_family=coalesce(scope->>'publication_family','')),0));
    RETURN encode(sha256(convert_to(snapshot::text,'UTF8')),'hex');
END;
$$;


COMMENT ON FUNCTION mdm.write_batch(text, uuid) IS
    'The writes of save_batch, without its match-proposal check: refuses a batch of more than 1,000 readings (with set-aside records) or 1,000 decisions, as mdm.prepare cuts them (no cap on its size or its current records, 019), stale or from an unregistered source; then saves the batch, its readings, entities, decisions, current records, checkpoint, outbox rows, set-aside records and Stage. Called by save_batch and preview_batch only; not granted to the application login.';
COMMENT ON FUNCTION mdm.record_match_proposal(text, uuid) IS
    'Record a match proposal (proposed joins and merges) with its snapshot, as ready or rejected; its effects are kept as their sha256. Returns its id. No cap on its size (019).';
COMMENT ON FUNCTION mdm.match_proposal_snapshot(jsonb) IS
    'The hash of everything a match proposal depends on (readings, decisions, entities and current records in its scope, and the reader''s checkpoint). If it changes, the proposal is stale. No cap on how many (019).';
