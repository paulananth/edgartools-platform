-- The Merge Stage's closure and the match proposal snapshot find the records
-- a list of keys names by joining the keys, not by comparing every row with
-- the whole list (profiling ticket 07, tuning; operator, 2026-10-09: "tune the
-- database before continueing with the batch test").
--
-- Each lookup was `field = ANY(keys)` six times under one OR. Postgres scanned
-- the table and compared each row's fields with every key, so a save cost
-- more as the store grew: at about 4,000 Form ADV filings the decision lookup
-- took 0.8 s (C collation) to 1.7 s (en_US), and the snapshot 0.2 s on the
-- first batch and 6 s by the eighth. Joined against the keys, the same lookup
-- took 68 ms (C) to 533 ms (en_US), and each branch can use its index.
--
-- The two lookups are written once, here, and both callers use them
-- (`merge.load_closure` and the snapshot), so they cannot drift. The rows they
-- return are unchanged, so a snapshot's hash is unchanged.
--
-- The two lookups set no search_path (every object they name is qualified):
-- a SQL function with a SET clause is never inlined, and inlined, each key
-- reaches its index in the caller's plan.

-- The source readings a list of keys names: a reading of one of the keys, or
-- one whose links name one. The links are found one key at a time through
-- their GIN index (`@> ARRAY[key]`): at 4,995 readings and 2,229 keys that
-- took 14 ms, where `&& keys` took 438 ms reading every row and 12 s through
-- the same index searched with the whole list at once.
CREATE FUNCTION mdm.readings_naming(keys text[]) RETURNS SETOF text
    LANGUAGE sql STABLE PARALLEL SAFE
    AS $$
    SELECT r.assertion_id FROM unnest(keys) k(key)
        JOIN mdm.source_reading r ON r.body->>'subject' = k.key
    UNION
    SELECT r.assertion_id FROM unnest(keys) k(key)
        JOIN mdm.source_reading r ON mdm.reading_link_subjects(r.body) @> ARRAY[k.key]
$$;

COMMENT ON FUNCTION mdm.readings_naming(text[]) IS
    'The source readings (their assertion ids) that a list of keys names: a reading of one of the keys, or one whose links name one. The one lookup the Merge Stage closure and the match proposal snapshot share; each key is joined to its index.';

-- The two GIN indexes, now probed one key at a time, keep no pending list. With
-- fastupdate on (the default), new entries wait in an unsorted list that
-- every search reads in full until a vacuum merges it: at 9,281 readings one
-- probe took 111 microseconds, against 3 with fastupdate off. A save writes a
-- little more; every search costs the same however many saves came before.
-- The entries already waiting are merged now.
ALTER INDEX mdm.source_reading_link_subjects SET (fastupdate = off);
ALTER INDEX mdm.current_record_review_affected_subjects SET (fastupdate = off);
SELECT gin_clean_pending_list('mdm.source_reading_link_subjects'::regclass);
SELECT gin_clean_pending_list('mdm.current_record_review_affected_subjects'::regclass);

-- The decisions a list of keys names: one of the keys is the decision, or its
-- subject, entity, either side of a merge, or its target.
CREATE FUNCTION mdm.decisions_naming(keys text[]) RETURNS SETOF text
    LANGUAGE sql STABLE PARALLEL SAFE
    AS $$
    SELECT d.decision_id FROM unnest(keys) k(key) JOIN mdm.decision d ON d.decision_id = k.key
    UNION SELECT d.decision_id FROM unnest(keys) k(key) JOIN mdm.decision d ON d.body->>'subject' = k.key
    UNION SELECT d.decision_id FROM unnest(keys) k(key) JOIN mdm.decision d ON d.body->>'entity_id' = k.key
    UNION SELECT d.decision_id FROM unnest(keys) k(key) JOIN mdm.decision d ON d.body->>'left' = k.key
    UNION SELECT d.decision_id FROM unnest(keys) k(key) JOIN mdm.decision d ON d.body->>'right' = k.key
    UNION SELECT d.decision_id FROM unnest(keys) k(key) JOIN mdm.decision d ON d.body->>'target' = k.key
$$;

COMMENT ON FUNCTION mdm.decisions_naming(text[]) IS
    'The decisions (their ids) that a list of keys names: the decision itself, or its subject, entity, either side of a merge, or its target. The one lookup the Merge Stage closure and the match proposal snapshot share; each key is joined to its index.';

-- The snapshot, as in 003 with 011's plan setting, reading its evidence and
-- decisions through the two lookups above; a retired source's decisions are
-- one more branch of the same IN, since an OR beside a subquery cannot use an
-- index and reads the table in full. Its current links and reviews are joined
-- the same way, each branch to its own index, the reviews that name a key
-- among their records one key at a time (`? key`, not `?| keys`). CREATE OR REPLACE resets a
-- function's settings, so the plan setting is restated here.
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
       OR jsonb_array_length(scope->'keys')>50000 OR jsonb_array_length(scope->'sources')>10000 THEN
        RAISE EXCEPTION 'Invalid assessment scope';
    END IF;
    SELECT array_agg(value) INTO keys FROM jsonb_array_elements_text(scope->'keys');
    SELECT array_agg(value) INTO sources FROM jsonb_array_elements_text(scope->'sources');
    WITH evidence AS (
        SELECT assertion_id AS id,body FROM mdm.source_reading
        WHERE assertion_id IN (SELECT id FROM mdm.readings_naming(keys) id)
        LIMIT 10001
    ), decisions AS (
        SELECT decision_id AS id,body FROM mdm.decision
        WHERE decision_id IN (SELECT id FROM mdm.decisions_naming(keys) id UNION ALL
            SELECT decision_id FROM mdm.decision WHERE operation='retire_source' AND body->>'source_code'=ANY(sources))
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
