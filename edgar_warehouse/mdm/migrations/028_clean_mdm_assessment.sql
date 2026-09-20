-- Advisory identity proposals. Master state still changes only in commit_batch.
CREATE TABLE mdm_v2.assessment (
    assessment_id text PRIMARY KEY,
    body jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_xid xid8 NOT NULL DEFAULT pg_current_xact_id()
);
CREATE TABLE mdm_v2.assessment_event (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assessment_id text NOT NULL REFERENCES mdm_v2.assessment(assessment_id),
    run_id uuid NOT NULL,
    event text NOT NULL CHECK(event IN ('ready','rejected','observed','superseded','applied')),
    batch_id text REFERENCES mdm_v2.batch(batch_id),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(assessment_id,run_id,event)
);
CREATE INDEX ON mdm_v2.assessment_event(assessment_id,event_id DESC);
CREATE INDEX ON mdm_v2.assessment((body->'command'->>'batch_id'));
CREATE INDEX ON mdm_v2.assessment(created_at DESC,assessment_id);
CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON mdm_v2.assessment
    FOR EACH ROW EXECUTE FUNCTION mdm_v2.immutable_row();
CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON mdm_v2.assessment_event
    FOR EACH ROW EXECUTE FUNCTION mdm_v2.immutable_row();

-- Include newly arrived assertions, decisions and edges touching the assessed
-- closure. Unrelated generations do not invalidate a proposal. Every scan is
-- bounded; the same snapshot function fences preparation and application.
CREATE FUNCTION mdm_v2.assessment_snapshot(scope jsonb) RETURNS text
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,mdm_v2 SET timezone='UTC' AS $$
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
        SELECT object_type||'/'||object_id AS id,body FROM mdm_v2.projection
        WHERE (object_type='entity' AND object_id=ANY(keys))
           OR (object_type='relationship' AND (body->>'source_id'=ANY(keys) OR body->>'target_id'=ANY(keys)))
           OR (object_type='review' AND (body->>'entity_id'=ANY(keys) OR body->>'subject'=ANY(keys)
               OR body->'affected_subjects' ?| keys)) LIMIT 10001
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
        (SELECT position FROM mdm_v2.checkpoint WHERE consumer=scope->>'consumer'),0));
    RETURN encode(sha256(convert_to(snapshot::text,'UTF8')),'hex');
END;
$$;

CREATE FUNCTION mdm_v2.record_assessment(body_text text,root_run uuid) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE b jsonb := body_text::jsonb; key text := encode(sha256(convert_to(body_text,'UTF8')),'hex');
BEGIN
    IF root_run IS NULL OR octet_length(body_text)>16777216
       OR NOT (b ?& ARRAY['version','command','outcome','rule_version'])
       OR b->>'version' IS DISTINCT FROM '1'
       OR b->>'outcome' NOT IN ('ready','rejected') OR b->>'outcome' IS NULL
       OR jsonb_typeof(b->'command'->'decisions') IS DISTINCT FROM 'array'
       OR jsonb_array_length(b->'command'->'decisions') NOT BETWEEN 1 AND 1000
       OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(b->'command'->'decisions') d WHERE d->>'operation' IN ('bind','merge')) THEN
        RAISE EXCEPTION 'Invalid or unbounded identity assessment';
    END IF;
    IF b->>'outcome'='ready' AND (
        jsonb_typeof(b->'effects') IS DISTINCT FROM 'object' OR NOT (b ?& ARRAY['scope','snapshot'])
        OR b->'effects'->>'policy_digest' IS DISTINCT FROM b->'command'->>'policy_digest'
        OR b->'effects'->>'batch_id' IS DISTINCT FROM b->'command'->>'batch_id') THEN
        RAISE EXCEPTION 'Ready assessment requires proposed effects and dependency snapshot';
    END IF;
    INSERT INTO mdm_v2.assessment(assessment_id,body) VALUES(key,b) ON CONFLICT DO NOTHING;
    IF NOT EXISTS(SELECT 1 FROM mdm_v2.assessment WHERE assessment_id=key AND body=b) THEN
        RAISE EXCEPTION 'Assessment digest collision';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM mdm_v2.assessment_event WHERE assessment_id=key) THEN
        INSERT INTO mdm_v2.assessment_event(assessment_id,run_id,event)
            VALUES(key,root_run,b->>'outcome') ON CONFLICT DO NOTHING;
    END IF;
    INSERT INTO mdm_v2.assessment_event(assessment_id,run_id,event)
        VALUES(key,root_run,'observed') ON CONFLICT DO NOTHING;
    RETURN key;
END;
$$;

CREATE FUNCTION mdm_v2.supersede_assessment(key text,root_run uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE b jsonb;
BEGIN
    PERFORM pg_advisory_xact_lock(730234);
    SELECT body INTO b FROM mdm_v2.assessment WHERE assessment_id=key;
    IF root_run IS NULL OR b IS NULL THEN RAISE EXCEPTION 'Unknown assessment or run'; END IF;
    IF b->>'outcome'='ready'
       AND NOT EXISTS(SELECT 1 FROM mdm_v2.assessment_event WHERE assessment_id=key AND event IN ('applied','superseded'))
       AND b->>'snapshot' IS DISTINCT FROM mdm_v2.assessment_snapshot(b->'scope') THEN
        INSERT INTO mdm_v2.assessment_event(assessment_id,run_id,event) VALUES(key,root_run,'superseded');
    END IF;
END;
$$;

ALTER FUNCTION mdm_v2.commit_batch(text,uuid) RENAME TO commit_batch_evidence;

-- A preview capability cannot be used to commit master state. The deliberate
-- exception rolls back all inner writes even if the caller commits its txn.
CREATE FUNCTION mdm_v2.preview_batch(request_text text,root_run uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE result jsonb;
BEGIN
    BEGIN
        result := mdm_v2.commit_batch_evidence(request_text,root_run);
        RAISE EXCEPTION USING ERRCODE='P0P01', MESSAGE='preview rollback';
    EXCEPTION WHEN SQLSTATE 'P0P01' THEN
        RETURN result;
    END;
END;
$$;

CREATE FUNCTION mdm_v2.commit_batch(request_text text,root_run uuid) RETURNS jsonb
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
    ELSIF key IS NOT NULL THEN
        RAISE EXCEPTION 'Assessment supplied without an identity proposal';
    END IF;
    result := mdm_v2.commit_batch_evidence(request_text,root_run);
    IF key IS NOT NULL THEN
        INSERT INTO mdm_v2.assessment_event(assessment_id,run_id,event,batch_id)
            VALUES(key,root_run,'applied',r->>'batch_id');
    END IF;
    RETURN result;
END;
$$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mdm_v2 FROM PUBLIC;
