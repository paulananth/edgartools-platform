-- A link may start at another record than the reading that states it
-- (`source_subject`: a GLEIF relationship record starts at its child's Level 1
-- record; platform validation 06a). A match proposal's snapshot reads the
-- readings that name its keys at either end of a link, as the Merge Stage's
-- closure does, so a proposal goes stale when either end's links change.
-- Otherwise unchanged from 001_mdm.sql.

CREATE OR REPLACE FUNCTION mdm.match_proposal_snapshot(scope jsonb) RETURNS text
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'mdm'
    SET "TimeZone" TO 'UTC'
    AS $$
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
        SELECT assertion_id AS id,body FROM mdm.source_reading
        WHERE body->>'subject'=ANY(keys) OR EXISTS(
            SELECT 1 FROM jsonb_array_elements(body->'relationships') r
            WHERE r->>'target_subject'=ANY(keys) OR r->>'source_subject'=ANY(keys))
        LIMIT 10001
    ), decisions AS (
        SELECT decision_id AS id,body FROM mdm.decision
        WHERE decision_id=ANY(keys) OR body->>'subject'=ANY(keys) OR body->>'entity_id'=ANY(keys)
           OR body->>'left'=ANY(keys) OR body->>'right'=ANY(keys) OR body->>'target'=ANY(keys)
           OR (operation='retire_source' AND body->>'source_code'=ANY(sources))
        LIMIT 10001
    ), identities AS (
        SELECT entity_id::text AS id,to_jsonb(i) AS body FROM mdm.master_entity i
        WHERE entity_id::text=ANY(keys) LIMIT 10001
    ), projections AS (
        -- Entities are read from current_entity, which holds the
        -- Companies; relationships and reviews stay in current_record.
        SELECT id,body FROM (
            SELECT 'entity/'||object_id AS id,body FROM mdm.current_entity
            WHERE object_id=ANY(keys)
            UNION ALL
            SELECT object_type||'/'||object_id,body FROM mdm.current_record
            WHERE (object_type='relationship' AND (body->>'source_id'=ANY(keys) OR body->>'target_id'=ANY(keys)))
               OR (object_type='review' AND (body->>'entity_id'=ANY(keys) OR body->>'subject'=ANY(keys)
                   OR body->'affected_subjects' ?| keys))
        ) scoped LIMIT 10001
    ), all_rows AS (
        SELECT 'source_reading' AS kind,id,body FROM evidence UNION ALL
        SELECT 'decision',id,body FROM decisions UNION ALL
        SELECT 'master_entity',id,body FROM identities UNION ALL
        SELECT 'current_record',id,body FROM projections
    ) SELECT count(*),coalesce(jsonb_agg(to_jsonb(a) ORDER BY kind,id),'[]') INTO n,snapshot FROM all_rows a;
    IF n>30000 THEN RAISE EXCEPTION 'Assessment snapshot exceeds bounded budget'; END IF;
    -- Individual branches may not be silently truncated, even below total cap.
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot) r GROUP BY r->>'kind' HAVING count(*)>10000) THEN
        RAISE EXCEPTION 'Assessment snapshot exceeds bounded budget';
    END IF;
    snapshot := jsonb_build_object('rows',snapshot,'checkpoint',coalesce(
        (SELECT position FROM mdm.checkpoint WHERE consumer=scope->>'consumer'
            AND source_family=coalesce(scope->>'source_family','')
            AND publication_family=coalesce(scope->>'publication_family','')),0));
    RETURN encode(sha256(convert_to(snapshot::text,'UTF8')),'hex');
END;
$$;

COMMENT ON FUNCTION mdm.match_proposal_snapshot(jsonb) IS
    'The hash of everything a match proposal depends on (readings, decisions, entities and current records in its scope, and the reader''s checkpoint). If it changes, the proposal is stale.';
