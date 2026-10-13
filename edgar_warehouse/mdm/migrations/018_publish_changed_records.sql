-- mdm.publish as change data capture, and force publish (ticket 22; operator,
-- 2026-10-13: "MDM publish can implement cdc aka change data capture only
-- publish what truly changed", "There has to be a force publish to publish all
-- records"; force publish sends the current snapshot, operator 2026-10-13).
--
-- write_batch already decides, per projected record, whether it wrote: a new
-- Company version or alias (record_company_version), or a current record whose
-- body differs. It now keeps that decision, with the record's position in the
-- batch, in batch_change ('insert' when the record was not current before,
-- else 'update'). MDM keeps no deletes: a record that ends (an alias, a
-- retired review) is an update whose body says so.
--
-- An outbox row now says its payload contract. 2 (every row before this file,
-- and the journal's from now on): the whole batch. 3 (every other consumer
-- from now on): only the batch's changed records, each with its `change`; a
-- consumer has no row for a batch that changed none of its records. Only
-- outbox_delivery builds a contract 3 payload, and outbox_input sends its
-- text, so the hash write_batch keeps and the text a publisher sends are the
-- same.
--
-- force_publish writes one page of the current snapshot (every current
-- record, Company and alias) as a forced batch: no MDM state changes, one
-- outbox row for the one consumer, every record's change 'snapshot', the
-- payload's `forced` true. Pages go in object order; the result names where
-- the next page starts.

CREATE TABLE mdm.batch_change (
    batch_id text NOT NULL REFERENCES mdm.batch(batch_id),
    position bigint NOT NULL CHECK (position >= 1),
    change text NOT NULL CHECK (change IN ('insert','update','snapshot')),
    PRIMARY KEY (batch_id, position)
);
COMMENT ON TABLE mdm.batch_change IS
    'Which projected records of a batch were inserted or changed (or, for a forced batch, sent as the snapshot); position is the record''s place in batch.effects->projections, from 1. Read by outbox_delivery for change data capture.';
COMMENT ON COLUMN mdm.batch_change.batch_id IS 'The batch (batch.batch_id).';
COMMENT ON COLUMN mdm.batch_change.position IS 'Position of the record in the batch''s projections, from 1.';
COMMENT ON COLUMN mdm.batch_change.change IS 'insert (not current before), update (current before, now different) or snapshot (a forced page).';

ALTER TABLE mdm.outbox ADD COLUMN contract_version integer NOT NULL DEFAULT 2
    CHECK (contract_version IN (2,3));
COMMENT ON COLUMN mdm.outbox.contract_version IS
    'Payload contract: 2 sends the whole batch (rows before migration 018, and the journal); 3 sends only the changed records (change data capture) or a forced snapshot page.';

-- A contract 3 payload: the batch's changed records, in batch order, each with
-- its change. Each record is read by its position (batch_change's primary
-- key), never by searching the batch. Built here only: outbox_input reads it.
CREATE OR REPLACE VIEW mdm.outbox_delivery AS
 SELECT o.batch_id,
    o.consumer,
    COALESCE(o.payload,
        CASE WHEN o.contract_version = 3 THEN
        jsonb_build_object('contract_version', 3, 'generation', b.generation, 'run_id', b.run_id,
            'policy_digest', b.effects ->> 'policy_digest',
            'forced', coalesce((b.effects ->> 'forced')::boolean, false),
            'objects', coalesce((SELECT jsonb_agg((b.effects -> 'projections' -> (c.position::int - 1))
                                                  || jsonb_build_object('change', c.change) ORDER BY c.position)
                                 FROM mdm.batch_change c WHERE c.batch_id = b.batch_id), '[]'::jsonb))
        ELSE
        jsonb_build_object('contract_version', 2, 'generation', b.generation, 'run_id', b.run_id,
                           'policy_digest', b.effects ->> 'policy_digest', 'objects', b.effects -> 'projections')
        || CASE WHEN o.consumer = 'journal' THEN jsonb_build_object('effects', b.effects) ELSE '{}'::jsonb END
        END) AS payload
   FROM mdm.outbox o
     JOIN mdm.batch b USING (batch_id);
COMMENT ON VIEW mdm.outbox_delivery IS
    'What each outbox row sends: its stored payload (a row saved before migration 014); else, for contract 3, only the batch''s changed records, each with its change (insert, update or snapshot), and whether it is forced; else built from its batch: generation, run, policy digest and current records, and for journal the whole batch. Read by claim_outbox, outbox_input and the publishers; write_batch keeps its hash.';

-- Contract 3 rows are sent as the text the database built (payload_text), so a
-- publisher needs no second builder; contract 2 rows are as before.
CREATE OR REPLACE VIEW mdm.outbox_input AS
 SELECT o.batch_id, o.consumer, o.payload_hash, b.created_at,
        CASE WHEN o.payload IS NOT NULL THEN o.payload::text
             WHEN o.contract_version = 3 THEN (SELECT d.payload::text FROM mdm.outbox_delivery d
                 WHERE d.batch_id = o.batch_id AND d.consumer = o.consumer) END AS payload_text,
        b.generation, b.run_id::text AS run_id,
        CASE WHEN o.payload IS NULL AND o.contract_version = 2 THEN b.effects->>'policy_digest' END AS policy_digest,
        CASE WHEN o.payload IS NULL AND o.contract_version = 2 THEN (b.effects->'projections')::text END AS projections_text,
        CASE WHEN o.payload IS NULL AND o.contract_version = 2 AND o.consumer='journal' THEN b.effects::text END AS effects_text
 FROM mdm.outbox o JOIN mdm.batch b USING(batch_id);
COMMENT ON COLUMN mdm.outbox_input.payload_text IS 'Publication JSONB text sent as is: a stored pre-014 payload, or a contract 3 payload (outbox_delivery); NULL for contract 2 intent prepared from the fields below.';

-- The outbox rows of a batch: one a consumer, each keeping the hash of what
-- outbox_delivery sends. The journal keeps the whole batch (contract 2: the
-- history of what was decided). Every other consumer gets change data capture
-- (contract 3): only the records the batch inserted or changed, and no row at
-- all when it changed none of them (a decision or set-aside record alone).
-- Called by write_batch and force_publish; not granted to any login.
CREATE FUNCTION mdm.queue_outbox(key text, consumers jsonb) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE item jsonb; delivered jsonb;
BEGIN
    FOR item IN SELECT value FROM jsonb_array_elements(consumers) LOOP
        CONTINUE WHEN item#>>'{}'<>'journal' AND NOT EXISTS(SELECT 1 FROM mdm.batch_change WHERE batch_id=key);
        INSERT INTO mdm.outbox(batch_id,consumer,payload,payload_hash,contract_version)
        VALUES(key,item#>>'{}',NULL,'',CASE WHEN item#>>'{}'='journal' THEN 2 ELSE 3 END);
        SELECT d.payload INTO delivered FROM mdm.outbox_delivery d WHERE d.batch_id=key AND d.consumer=item#>>'{}';
        UPDATE mdm.outbox SET payload_hash=encode(sha256(convert_to(delivered::text,'UTF8')),'hex')
          WHERE batch_id=key AND consumer=item#>>'{}';
    END LOOP;
END;
$$;

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
        IF root_run IS NULL OR octet_length(request_text) > 16777216
           OR coalesce(jsonb_array_length(r->'assertions'),0) > 1000
           OR coalesce(jsonb_array_length(r->'decisions'),0) > 1000
           OR coalesce(jsonb_array_length(r->'projections'),0) > 10000 THEN
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

-- One page of the current snapshot for one consumer, as a forced batch. The
-- page holds at most page_size records after (after_type, after_id), in
-- (object_type, object_id) order: current records, current Companies and
-- current Company aliases (an alias as the Merge Stage projects it). The same
-- run and page number give the same batch: a retry returns it unchanged.
CREATE FUNCTION mdm.force_publish(target text, root_run uuid, page bigint, after_type text, after_id text, page_size integer)
    RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE key text := format('forced:%s:%s:%s', target, root_run, page);
    found_batch mdm.batch%ROWTYPE; required jsonb; policy text; objects jsonb; effects jsonb;
    next_generation bigint; last jsonb; total bigint; more boolean;
    -- Companies and aliases are all object_type 'entity': read by their id's index.
    entity_after text := CASE WHEN after_type = 'entity' THEN after_id ELSE '' END;
BEGIN
    IF target IS NULL OR root_run IS NULL OR page IS NULL OR page < 1 OR after_type IS NULL OR after_id IS NULL
       OR page_size IS NULL OR page_size < 1 OR page_size > 10000 THEN
        RAISE EXCEPTION 'Force publish needs a consumer, a run, a page from 1, a start and at most 10000 records a page';
    END IF;
    IF target='journal' THEN
        RAISE EXCEPTION 'The journal holds the history of every batch; force publish is for change data capture consumers';
    END IF;
    PERFORM pg_advisory_xact_lock(730234);
    SELECT * INTO found_batch FROM mdm.batch WHERE batch_id=key;
    IF FOUND THEN
        RETURN jsonb_build_object('batch_id',key,'generation',found_batch.generation,'duplicate',true,
            'records',jsonb_array_length(found_batch.effects->'projections'),'next',found_batch.effects->'next');
    END IF;
    SELECT b.policy_digest INTO policy FROM mdm.batch b ORDER BY generation DESC LIMIT 1;
    SELECT p.body->'required_consumers' INTO required FROM mdm.policy p WHERE p.digest=policy;
    IF required IS NULL OR NOT required ? target THEN
        RAISE EXCEPTION 'Force publish names a consumer the current policy does not require';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('object_type',s.object_type,'object_id',s.object_id,'body',s.body)
                              ORDER BY s.object_type,s.object_id),'[]'::jsonb), count(*)
      INTO objects, total FROM (
        (SELECT c.object_type,c.object_id,c.body FROM mdm.current_record c
          WHERE (c.object_type,c.object_id) > (after_type,after_id)
          ORDER BY c.object_type,c.object_id LIMIT page_size+1)
        UNION ALL
        (SELECT 'entity',c.entity_id::text,c.body FROM mdm.company c
          WHERE c.valid_to IS NULL AND after_type <= 'entity' AND c.entity_id::text > entity_after
          ORDER BY c.entity_id::text LIMIT page_size+1)
        UNION ALL
        (SELECT 'entity',a.alias_id::text,jsonb_build_object('entity_id',a.alias_id::text,'kind','company',
                 'canonical_id',a.canonical_id::text,'status','alias')
          FROM mdm.company_alias a
          WHERE a.valid_to IS NULL AND after_type <= 'entity' AND a.alias_id::text > entity_after
          ORDER BY a.alias_id::text LIMIT page_size+1)
        ORDER BY 1,2 LIMIT page_size+1) s;
    -- One record more than the page says whether another page follows; it is not sent.
    more := total > page_size;
    IF more THEN objects := objects - page_size; total := page_size; END IF;
    last := objects->(jsonb_array_length(objects)-1);
    effects := jsonb_build_object('forced',true,'consumer',target,'policy_digest',policy,'page',page,
        'after',jsonb_build_object('object_type',after_type,'object_id',after_id),
        'next',CASE WHEN more THEN jsonb_build_object('object_type',last->>'object_type','object_id',last->>'object_id') END,
        'projections',objects);
    SELECT coalesce(max(generation),0)+1 INTO next_generation FROM mdm.batch;
    INSERT INTO mdm.run(run_id,scope) VALUES(root_run,jsonb_build_object('forced_publish',target)) ON CONFLICT DO NOTHING;
    INSERT INTO mdm.batch VALUES(key,encode(sha256(convert_to(effects::text,'UTF8')),'hex'),root_run,policy,
        next_generation,'forced:'||target,page,effects,now());
    INSERT INTO mdm.run_batch VALUES(root_run,key);
    INSERT INTO mdm.batch_change SELECT key,i,'snapshot' FROM generate_series(1,total) i;
    PERFORM mdm.queue_outbox(key,jsonb_build_array(target));
    RETURN jsonb_build_object('batch_id',key,'generation',next_generation,'duplicate',false,
        'records',total,'next',effects->'next');
END;
$$;
COMMENT ON FUNCTION mdm.force_publish(text, uuid, bigint, text, text, integer) IS
    'Force publish (ticket 22): one page of the current snapshot for one consumer, as a forced batch with one contract 3 outbox row; changes no master data. Start with after (,) and page 1; pass the result''s next until it is null.';
