-- An outbox row names its batch instead of holding a copy of it (MDM write
-- duplication ticket, 2026-10-11).
--
-- write_batch stored, for each consumer the policy requires, the batch's
-- golden records (and for `journal` the whole batch request as well) in
-- `outbox.payload`, though `batch.effects` already holds the same request: one
-- 919-Company batch wrote 15 MB of outbox payloads beside its 6 MB batch row.
-- What a consumer is sent is a function of its batch row (generation, run,
-- policy digest, `effects`), so a new outbox row keeps only the hash of it;
-- `outbox_delivery` builds it when a publisher claims, delivers or verifies the
-- row. A row stored before this keeps its own payload, which is sent as stored.
-- Built by the same expression the old write used, a new row's hash equals the
-- hash its stored payload would have had.

ALTER TABLE mdm.outbox ALTER COLUMN payload DROP NOT NULL;
COMMENT ON COLUMN mdm.outbox.payload IS
    'What to send, for a row saved before migration 014; NULL for a later row, whose payload is built from its batch (outbox_delivery).';

-- What each outbox row sends: its stored payload (a row saved before 014), else
-- the payload built from its batch row. A view, so any login that may read the
-- schema (a publisher's verifier holds SELECT only) reads it, and write_batch
-- hashes the same expression.
CREATE OR REPLACE VIEW mdm.outbox_delivery AS
 SELECT o.batch_id,
    o.consumer,
    COALESCE(o.payload,
        jsonb_build_object('contract_version', 2, 'generation', b.generation, 'run_id', b.run_id,
                           'policy_digest', b.effects ->> 'policy_digest', 'objects', b.effects -> 'projections')
        || CASE WHEN o.consumer = 'journal' THEN jsonb_build_object('effects', b.effects) ELSE '{}'::jsonb END)
        AS payload
   FROM mdm.outbox o
     JOIN mdm.batch b USING (batch_id);
COMMENT ON VIEW mdm.outbox_delivery IS
    'What each outbox row sends: its stored payload (a row saved before migration 014), else built from its batch: generation, run, policy digest and current records, and for journal the whole batch. Read by claim_outbox and the publishers; write_batch keeps its hash.';
COMMENT ON COLUMN mdm.outbox_delivery.payload IS 'What to send.';
COMMENT ON COLUMN mdm.outbox_delivery.batch_id IS 'The saved batch that wrote this row (batch.batch_id).';
COMMENT ON COLUMN mdm.outbox_delivery.consumer IS 'The reader the work is for, e.g. journal.';

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
            result := jsonb_build_object('batch_id',prior.batch_id,'generation',prior.generation,'duplicate',true);
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
        END LOOP;
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
            -- A Company is kept in the Company table only. The batch row
            -- above holds this commit's generation; now() is its created_at.
            IF item->>'object_type'='entity' AND item->'body'->>'kind'='company' THEN
                PERFORM mdm.record_company_version(item->'body',r->>'batch_id',now());
            ELSE
                INSERT INTO mdm.current_record VALUES(item->>'object_type',item->>'object_id',item->'body',r->>'batch_id')
                ON CONFLICT(object_type,object_id) DO UPDATE SET body=excluded.body,batch_id=excluded.batch_id;
            END IF;
        END LOOP;
        INSERT INTO mdm.checkpoint(consumer,position,batch_id,source_family,publication_family,committed_publication,continuity_proof)
        VALUES(r->>'consumer',(r->>'checkpoint')::bigint,r->>'batch_id',coalesce(r->>'source_family',''),
            coalesce(r->>'publication_family',''),r->>'committed_publication',r->'continuity_proof')
        ON CONFLICT(consumer,source_family,publication_family) DO UPDATE SET position=excluded.position,
            batch_id=excluded.batch_id,committed_publication=excluded.committed_publication,continuity_proof=excluded.continuity_proof;
        -- An outbox row names its batch; what it sends is built from the batch row
        -- (outbox_delivery), and the row keeps the hash of that.
        FOR item IN SELECT value FROM jsonb_array_elements(required) LOOP
            INSERT INTO mdm.outbox(batch_id,consumer,payload,payload_hash)
            VALUES(r->>'batch_id',item#>>'{}',NULL,'');
            SELECT d.payload INTO delivered FROM mdm.outbox_delivery d
              WHERE d.batch_id=r->>'batch_id' AND d.consumer=item#>>'{}';
            UPDATE mdm.outbox SET payload_hash=encode(sha256(convert_to(delivered::text,'UTF8')),'hex')
              WHERE batch_id=r->>'batch_id' AND consumer=item#>>'{}';
        END LOOP;
        result := jsonb_build_object('batch_id',r->>'batch_id','generation',next_generation,'duplicate',false);
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

CREATE OR REPLACE FUNCTION mdm.claim_outbox(destination text, owner_name text, lease_seconds integer) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE p mdm.outbox%ROWTYPE;
BEGIN
    IF lease_seconds NOT BETWEEN 1 AND 3600 OR nullif(owner_name,'') IS NULL THEN RAISE EXCEPTION 'Invalid lease'; END IF;
    -- Preserve generation order per consumer; an unexpired earlier claim blocks later delivery.
    SELECT q.* INTO p FROM mdm.outbox q JOIN mdm.batch b USING(batch_id)
      WHERE q.consumer=destination AND q.verified_at IS NULL ORDER BY b.generation LIMIT 1 FOR UPDATE OF q;
    IF NOT FOUND OR p.lease_until > clock_timestamp() THEN RETURN NULL; END IF;
    UPDATE mdm.outbox SET fence=fence+1,worker=owner_name,
      lease_until=clock_timestamp()+make_interval(secs=>lease_seconds)
      WHERE batch_id=p.batch_id AND consumer=p.consumer RETURNING * INTO p;
    INSERT INTO mdm.outbox_event(batch_id,consumer,fence,event,detail)
      VALUES(p.batch_id,p.consumer,p.fence,'claimed',jsonb_build_object('worker',owner_name));
    RETURN to_jsonb(p) || jsonb_build_object('payload',
        (SELECT d.payload FROM mdm.outbox_delivery d WHERE d.batch_id=p.batch_id AND d.consumer=p.consumer));
END;
$$;
