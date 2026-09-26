-- Keep each Company in one place (company mastering ticket 17).
--
-- The operator chose, on 2026-09-26 at 13:03 ET, to remove the Company copy
-- steps rather than tune them: "lean, clean, KISS". Before this migration a
-- commit wrote one Company three times:
-- - to mdm_v2.projection;
-- - by trigger to mdm_v2.company (037);
-- - back into each publication by a second trigger, which replaced each
--   Company object with the bytes it already held. That step took 91% of the
--   Merge Stage's database time in ticket 05's Proving Run.
--
-- After this migration:
-- - commit_batch_core writes a Company entity to mdm_v2.company, or to
--   mdm_v2.company_alias for a merged-away ID, through
--   record_company_projection (037). Every other object goes to
--   projection as before. A publication carries the objects the Merge Stage
--   computed, unchanged.
-- - mdm_v2.current_entity is the one read of a current entity. It is made of
--   projection's entities (every other kind), the open Company rows, and the
--   open alias rows in the object the Merge Stage writes for an alias. Its
--   rows equal what projection held, so an assessment snapshot taken before
--   this migration still matches.
-- - On a populated store, each Company row in projection is checked against
--   the Company table, then removed.
--
-- commit_batch_core and assessment_snapshot are restated whole from the live
-- catalog, because 029, 031, 038 and 039 edited them as text. Each change is
-- marked "042".

DROP TRIGGER project_company_version ON mdm_v2.projection;
DROP TRIGGER publish_company_authority ON mdm_v2.publication;
DROP FUNCTION mdm_v2.project_company_version();
DROP FUNCTION mdm_v2.publish_company_authority();
DROP FUNCTION mdm_v2.company_payload_from_table(jsonb);

-- OR REPLACE: a migration test fills a store built before 042 with today's
-- code, so it gives that store a stand-in current_entity over projection,
-- with these same columns. A real store has no such view.
CREATE OR REPLACE VIEW mdm_v2.current_entity AS
SELECT p.object_id,
       p.body->>'kind' AS kind,
       p.body->>'status' AS status,
       p.body->>'canonical_id' AS canonical_id,
       p.body
FROM mdm_v2.projection p
WHERE p.object_type = 'entity'
UNION ALL
SELECT c.entity_id::text, 'company', c.status, c.body->>'canonical_id', c.body
FROM mdm_v2.company c
WHERE c.valid_to IS NULL
UNION ALL
SELECT a.alias_id::text, 'company', 'alias', a.canonical_id::text,
       jsonb_build_object('entity_id', a.alias_id::text, 'kind', 'company',
                          'canonical_id', a.canonical_id::text, 'status', 'alias')
FROM mdm_v2.company_alias a
WHERE a.valid_to IS NULL;

-- Readers look an entity up by its text id; these let the view use an index
-- for the Company rows instead of scanning the table.
CREATE INDEX company_current_entity_text ON mdm_v2.company ((entity_id::text))
    WHERE valid_to IS NULL;
CREATE INDEX company_alias_current_text ON mdm_v2.company_alias ((alias_id::text))
    WHERE valid_to IS NULL;

DO $$
BEGIN
    -- Each Company row in projection must read back unchanged from the
    -- Company table: an open row with the same body, or an open alias whose
    -- routing object is the same body.
    IF EXISTS (
        SELECT 1 FROM mdm_v2.projection p
        WHERE p.object_type = 'entity' AND p.body->>'kind' = 'company'
          AND NOT EXISTS (
              SELECT 1 FROM mdm_v2.company c
              WHERE c.valid_to IS NULL AND c.entity_id::text = p.object_id
                AND c.body = p.body)
          AND NOT EXISTS (
              SELECT 1 FROM mdm_v2.company_alias a
              WHERE a.valid_to IS NULL AND a.alias_id::text = p.object_id
                AND p.body = jsonb_build_object(
                    'entity_id', a.alias_id::text, 'kind', 'company',
                    'canonical_id', a.canonical_id::text, 'status', 'alias'))
    ) THEN
        RAISE EXCEPTION 'A Company in projection differs from the Company table';
    END IF;
    DELETE FROM mdm_v2.projection
    WHERE object_type = 'entity' AND body->>'kind' = 'company';
END;
$$;

CREATE OR REPLACE FUNCTION mdm_v2.commit_batch_core(request_text text, root_run uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'mdm_v2'
AS $function$
DECLARE
    r jsonb := request_text::jsonb;
    h text := encode(sha256(convert_to(request_text,'UTF8')),'hex');
    old mdm_v2.batch%ROWTYPE;
    item jsonb;
    src mdm_v2.dataset%ROWTYPE;
    current_generation bigint;
    next_generation bigint;
    pos bigint;
    outputs jsonb;
    required jsonb;
    delivered jsonb;
BEGIN
    IF root_run IS NULL OR octet_length(request_text) > 16777216
       OR coalesce(jsonb_array_length(r->'assertions'),0) > 1000
       OR coalesce(jsonb_array_length(r->'decisions'),0) > 1000
       OR coalesce(jsonb_array_length(r->'projections'),0) > 10000 THEN
        RAISE EXCEPTION 'Invalid or unbounded batch';
    END IF;
    IF coalesce(r->>'source_family','')<>'' AND NOT EXISTS(
        SELECT 1 FROM mdm_v2.dataset WHERE body->>'family'=r->>'source_family'
          AND body->'publication_families' ? (r->>'publication_family')) THEN
        RAISE EXCEPTION 'Unknown publication family contract';
    END IF;
    PERFORM pg_advisory_xact_lock(730234);
    SELECT * INTO old FROM mdm_v2.batch WHERE batch_id = r->>'batch_id';
    IF FOUND THEN
        IF old.request_hash <> h THEN RAISE EXCEPTION 'Batch key reused with different content'; END IF;
        INSERT INTO mdm_v2.observation VALUES(root_run,old.batch_id) ON CONFLICT DO NOTHING;
        RETURN jsonb_build_object('batch_id',old.batch_id,'generation',old.generation,'duplicate',true);
    END IF;
    SELECT coalesce(max(generation),0) INTO current_generation FROM mdm_v2.batch;
    IF (r->>'expected_generation')::bigint IS DISTINCT FROM current_generation THEN
        RAISE EXCEPTION 'Stale generation';
    END IF;
    SELECT coalesce((SELECT position FROM mdm_v2.checkpoint WHERE consumer=r->>'consumer'
        AND source_family=coalesce(r->>'source_family','')
        AND publication_family=coalesce(r->>'publication_family','')),0) INTO pos;
    IF (r->>'expected_checkpoint')::bigint IS DISTINCT FROM pos
       OR (r->>'checkpoint')::bigint IS NULL OR (r->>'checkpoint')::bigint <= pos THEN
        RAISE EXCEPTION 'Stale or nonadvancing checkpoint';
    END IF;
    SELECT body->'required_consumers' INTO required FROM mdm_v2.policy WHERE digest=r->>'policy_digest';
    IF required IS NULL OR jsonb_array_length(required)=0 THEN RAISE EXCEPTION 'Missing frozen consumer contract'; END IF;
    next_generation := current_generation+1;
    INSERT INTO mdm_v2.batch VALUES(r->>'batch_id',h,root_run,r->>'policy_digest',next_generation,
        r->>'consumer',(r->>'checkpoint')::bigint,r,now());
    INSERT INTO mdm_v2.observation VALUES(root_run,r->>'batch_id');
    FOR item IN SELECT value FROM jsonb_array_elements(r->'assertions') LOOP
        SELECT * INTO src FROM mdm_v2.dataset WHERE source_code=item->>'source_code';
        IF NOT FOUND OR src.body->'registry_evidence'->>'status' IS DISTINCT FROM 'active'
           OR src.body->'registry_evidence'->>'version_id' IS DISTINCT FROM src.registry_version::text
           OR src.body->'registry_evidence'->>'source_family' IS DISTINCT FROM src.body->>'family' THEN
            RAISE EXCEPTION 'Dataset has no pinned registry authority';
        END IF;
        IF NOT EXISTS(SELECT 1 FROM mdm_v2.dataset_mapping m
            WHERE m.source_code=item->>'source_code'
              AND m.mapping_version=coalesce((item->>'mapping_version')::bigint,1)
              AND m.body->>'schema_version' IS NOT DISTINCT FROM item->>'schema_version') THEN
            RAISE EXCEPTION 'Unsupported source schema';
        END IF;
        IF EXISTS(SELECT 1 FROM mdm_v2.assertion a WHERE a.assertion_id=item->>'assertion_id' AND a.body<>item) THEN
            RAISE EXCEPTION 'Assertion identity collision';
        END IF;
        INSERT INTO mdm_v2.assertion(assertion_id,source_code,record_key,publication_key,
          revision,effective_at,body,batch_id,mapping_version)
          VALUES(item->>'assertion_id',item->>'source_code',item->>'record_key',
          item->>'publication_key',(item->>'revision')::bigint,(item->>'effective_at')::timestamptz,item,r->>'batch_id',
          coalesce((item->>'mapping_version')::bigint,1))
          ON CONFLICT(assertion_id) DO NOTHING;
    END LOOP;
    FOR item IN SELECT value FROM jsonb_array_elements(r->'identities') LOOP
        INSERT INTO mdm_v2.identity VALUES((item->>'entity_id')::uuid,item->>'kind',
          (item->>'published_at')::timestamptz,r->>'batch_id');
    END LOOP;
    FOR item IN SELECT value FROM jsonb_array_elements(r->'decisions') LOOP
        IF nullif(item->>'actor','') IS NULL OR nullif(item->>'reason','') IS NULL THEN
            RAISE EXCEPTION 'Decision requires actor and reason';
        END IF;
        INSERT INTO mdm_v2.decision VALUES(item->>'decision_id',item->>'operation',item,r->>'batch_id');
    END LOOP;
    FOR item IN SELECT value FROM jsonb_array_elements(r->'projections') LOOP
        -- 042: a Company is kept in the Company table only. The batch row
        -- above holds this commit's generation; now() is its created_at.
        IF item->>'object_type'='entity' AND item->'body'->>'kind'='company' THEN
            PERFORM mdm_v2.record_company_projection(item->'body',r->>'batch_id',now());
        ELSE
            INSERT INTO mdm_v2.projection VALUES(item->>'object_type',item->>'object_id',item->'body',r->>'batch_id')
            ON CONFLICT(object_type,object_id) DO UPDATE SET body=excluded.body,batch_id=excluded.batch_id;
        END IF;
    END LOOP;
    INSERT INTO mdm_v2.checkpoint(consumer,position,batch_id,source_family,publication_family,committed_publication,continuity_proof)
    VALUES(r->>'consumer',(r->>'checkpoint')::bigint,r->>'batch_id',coalesce(r->>'source_family',''),
        coalesce(r->>'publication_family',''),r->>'committed_publication',r->'continuity_proof')
    ON CONFLICT(consumer,source_family,publication_family) DO UPDATE SET position=excluded.position,
        batch_id=excluded.batch_id,committed_publication=excluded.committed_publication,continuity_proof=excluded.continuity_proof;
    outputs := jsonb_build_object('contract_version',2,'generation',next_generation,'run_id',root_run,
       'policy_digest',r->>'policy_digest','objects',r->'projections');
    FOR item IN SELECT value FROM jsonb_array_elements(required) LOOP
        delivered := CASE WHEN item#>>'{}'='journal' THEN outputs || jsonb_build_object('effects',r) ELSE outputs END;
        INSERT INTO mdm_v2.publication(batch_id,consumer,payload,payload_hash)
        VALUES(r->>'batch_id',item#>>'{}',delivered,encode(sha256(convert_to(delivered::text,'UTF8')),'hex'));
    END LOOP;
    RETURN jsonb_build_object('batch_id',r->>'batch_id','generation',next_generation,'duplicate',false);
END;
$function$;

CREATE OR REPLACE FUNCTION mdm_v2.assessment_snapshot(scope jsonb)
 RETURNS text
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog', 'mdm_v2'
 SET "TimeZone" TO 'UTC'
AS $function$
DECLARE keys text[]; sources text[]; snapshot jsonb; n integer;
BEGIN
    IF jsonb_typeof(scope->'keys') IS DISTINCT FROM 'array'
       OR jsonb_typeof(scope->'sources') IS DISTINCT FROM 'array'
       OR jsonb_array_length(scope->'keys')>50000 OR jsonb_array_length(scope->'sources')>10000 THEN
        RAISE EXCEPTION 'Invalid assessment scope';
    END IF;
    SELECT array_agg(value) INTO keys FROM jsonb_array_elements_text(scope->'keys');
    SELECT array_agg(value) INTO sources FROM jsonb_array_elements_text(scope->'sources');
    WITH evidence AS (
        SELECT assertion_id AS id,body FROM mdm_v2.assertion
        WHERE body->>'subject'=ANY(keys) OR EXISTS(
            SELECT 1 FROM jsonb_array_elements(body->'relationships') r WHERE r->>'target_subject'=ANY(keys))
        LIMIT 10001
    ), decisions AS (
        SELECT decision_id AS id,body FROM mdm_v2.decision
        WHERE decision_id=ANY(keys) OR body->>'subject'=ANY(keys) OR body->>'entity_id'=ANY(keys)
           OR body->>'left'=ANY(keys) OR body->>'right'=ANY(keys) OR body->>'target'=ANY(keys)
           OR (operation='retire_source' AND body->>'source_code'=ANY(sources))
        LIMIT 10001
    ), identities AS (
        SELECT entity_id::text AS id,to_jsonb(i) AS body FROM mdm_v2.identity i
        WHERE entity_id::text=ANY(keys) LIMIT 10001
    ), projections AS (
        -- 042: entities are read from current_entity, which holds the
        -- Companies; relationships and reviews stay in projection.
        SELECT id,body FROM (
            SELECT 'entity/'||object_id AS id,body FROM mdm_v2.current_entity
            WHERE object_id=ANY(keys)
            UNION ALL
            SELECT object_type||'/'||object_id,body FROM mdm_v2.projection
            WHERE (object_type='relationship' AND (body->>'source_id'=ANY(keys) OR body->>'target_id'=ANY(keys)))
               OR (object_type='review' AND (body->>'entity_id'=ANY(keys) OR body->>'subject'=ANY(keys)
                   OR body->'affected_subjects' ?| keys))
        ) scoped LIMIT 10001
    ), all_rows AS (
        SELECT 'assertion' AS kind,id,body FROM evidence UNION ALL
        SELECT 'decision',id,body FROM decisions UNION ALL
        SELECT 'identity',id,body FROM identities UNION ALL
        SELECT 'projection',id,body FROM projections
    ) SELECT count(*),coalesce(jsonb_agg(to_jsonb(a) ORDER BY kind,id),'[]') INTO n,snapshot FROM all_rows a;
    IF n>30000 THEN RAISE EXCEPTION 'Assessment snapshot exceeds bounded budget'; END IF;
    -- Individual branches may not be silently truncated, even below total cap.
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot) r GROUP BY r->>'kind' HAVING count(*)>10000) THEN
        RAISE EXCEPTION 'Assessment snapshot exceeds bounded budget';
    END IF;
    snapshot := jsonb_build_object('rows',snapshot,'checkpoint',coalesce(
        (SELECT position FROM mdm_v2.checkpoint WHERE consumer=scope->>'consumer'
            AND source_family=coalesce(scope->>'source_family','')
            AND publication_family=coalesce(scope->>'publication_family','')),0));
    RETURN encode(sha256(convert_to(snapshot::text,'UTF8')),'hex');
END;
$function$;

REVOKE ALL ON ALL TABLES IN SCHEMA mdm_v2 FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mdm_v2 FROM PUBLIC;
