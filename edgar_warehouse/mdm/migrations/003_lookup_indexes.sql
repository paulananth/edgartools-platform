-- Every lookup a save repeats is served by an index (platform validation 05b,
-- part 2; research note `.scratch/platform-validation/research/
-- 05b-mdm-database-tuning.md`). The match proposal snapshot, the Merge Stage
-- closure and the retirement of old links and reviews used to read their
-- tables in full, so each save cost more than the one before.
--
-- Migrations run in one transaction, so these indexes are built without
-- CONCURRENTLY: each build blocks writes to its table (not reads) for as long
-- as it takes, seconds at tens of thousands of rows.
-- Otherwise unchanged from 002_link_start.sql.

-- The records a reading's links name: each link's end and, when the link
-- starts at another record, its start; an empty name is no record, as in
-- `merge.linked_subjects`. One definition for the index, the snapshot and the
-- closure. It sets search_path, so the planner never inlines
-- it and every caller matches the indexed expression.
CREATE FUNCTION mdm.reading_link_subjects(body jsonb) RETURNS text[]
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    SET search_path TO 'pg_catalog'
    AS $$
    SELECT coalesce(array_agg(DISTINCT subject ORDER BY subject), '{}')
    FROM jsonb_array_elements(
             CASE WHEN jsonb_typeof(body->'relationships') = 'array'
                  THEN body->'relationships' ELSE '[]'::jsonb END) AS link,
         LATERAL (VALUES (link->>'target_subject'), (link->>'source_subject')) AS ends(subject)
    WHERE subject <> ''
$$;

COMMENT ON FUNCTION mdm.reading_link_subjects(jsonb) IS
    'The records a source reading''s links name (each link''s end, and its start when it starts at another record). Indexed on source_reading, so the snapshot and the Merge Stage closure find the readings that link to a key without reading the table.';

CREATE INDEX source_reading_link_subjects ON mdm.source_reading USING gin (mdm.reading_link_subjects(body));
COMMENT ON INDEX mdm.source_reading_link_subjects IS
    'Finds the readings whose links name a record (with the subject index, the snapshot''s and the closure''s evidence lookup).';

CREATE INDEX master_entity_id_text ON mdm.master_entity USING btree (((entity_id)::text));
COMMENT ON INDEX mdm.master_entity_id_text IS
    'Finds an entity by its id written as text, as the snapshot and the closure compare it with their keys.';

CREATE INDEX decision_retired_source ON mdm.decision USING btree (((body ->> 'source_code'::text)))
    WHERE (operation = 'retire_source'::text);
COMMENT ON INDEX mdm.decision_retired_source IS
    'Finds the decisions that retire a source, so every part of the snapshot''s decision lookup has an index.';

CREATE INDEX current_record_link_start ON mdm.current_record USING btree (((body ->> 'source_id'::text)))
    WHERE (object_type = 'relationship'::text);
COMMENT ON INDEX mdm.current_record_link_start IS
    'Finds the current links that start at an entity.';

CREATE INDEX current_record_link_end ON mdm.current_record USING btree (((body ->> 'target_id'::text)))
    WHERE (object_type = 'relationship'::text);
COMMENT ON INDEX mdm.current_record_link_end IS
    'Finds the current links that end at an entity.';

CREATE INDEX current_record_review_entity ON mdm.current_record USING btree (((body ->> 'entity_id'::text)))
    WHERE (object_type = 'review'::text);
COMMENT ON INDEX mdm.current_record_review_entity IS
    'Finds the current reviews about an entity.';

CREATE INDEX current_record_review_subject ON mdm.current_record USING btree (((body ->> 'subject'::text)))
    WHERE (object_type = 'review'::text);
COMMENT ON INDEX mdm.current_record_review_subject IS
    'Finds the current reviews about a record.';

CREATE INDEX current_record_review_affected_subjects ON mdm.current_record USING gin (((body -> 'affected_subjects'::text)))
    WHERE (object_type = 'review'::text);
COMMENT ON INDEX mdm.current_record_review_affected_subjects IS
    'Finds the current reviews that name a record among the records they are about (05b part 1: only their own).';

-- The snapshot, as in 002, with each lookup written so its index serves it:
-- a reading's links through mdm.reading_link_subjects, and each current
-- record lookup as its own condition, with its type, under one OR. The rows,
-- their order and the hash are unchanged.
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
        WHERE body->>'subject'=ANY(keys) OR mdm.reading_link_subjects(body) && keys
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
            WHERE (object_type='relationship' AND body->>'source_id'=ANY(keys))
               OR (object_type='relationship' AND body->>'target_id'=ANY(keys))
               OR (object_type='review' AND body->>'entity_id'=ANY(keys))
               OR (object_type='review' AND body->>'subject'=ANY(keys))
               OR (object_type='review' AND body->'affected_subjects' ?| keys)
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
