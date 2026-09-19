-- Clean MDM v1. Explicit opt-in migration; the legacy MDM remains untouched.
-- No parallel root-run table: run_id refers to the existing Bookkeeping owner.
CREATE SCHEMA mdm_v2;
REVOKE ALL ON SCHEMA mdm_v2 FROM PUBLIC;
CREATE TABLE mdm_v2.migration (
    name text PRIMARY KEY,
    checksum text NOT NULL,
    installed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE mdm_v2.policy (
    digest text PRIMARY KEY,
    body jsonb NOT NULL CHECK (jsonb_typeof(body) = 'object')
);
-- Metadata extends the existing registry's authority, not its activation state.
CREATE TABLE mdm_v2.dataset (
    source_code text PRIMARY KEY,
    registry_version uuid NOT NULL,
    body jsonb NOT NULL CHECK (body ?& ARRAY['provider','family','schema_version','record_key','publication_key','effective_time','semantics','registry_evidence'])
);
CREATE TABLE mdm_v2.batch (
    batch_id text PRIMARY KEY,
    request_hash text NOT NULL,
    run_id uuid NOT NULL,
    policy_digest text NOT NULL REFERENCES mdm_v2.policy(digest),
    generation bigint UNIQUE NOT NULL,
    consumer text NOT NULL,
    checkpoint bigint NOT NULL,
    effects jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE mdm_v2.observation (
    run_id uuid NOT NULL,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id),
    PRIMARY KEY (run_id,batch_id)
);
CREATE TABLE mdm_v2.checkpoint (
    consumer text PRIMARY KEY,
    position bigint NOT NULL,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id)
);
CREATE TABLE mdm_v2.assertion (
    assertion_id text PRIMARY KEY,
    source_code text NOT NULL REFERENCES mdm_v2.dataset(source_code),
    record_key text NOT NULL,
    publication_key text NOT NULL,
    revision bigint NOT NULL CHECK (revision >= 0),
    effective_at timestamptz,
    body jsonb NOT NULL,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id),
    UNIQUE(source_code,record_key,publication_key)
);
CREATE INDEX ON mdm_v2.assertion(source_code,record_key,revision);
CREATE TABLE mdm_v2.identity (
    entity_id uuid PRIMARY KEY,
    kind text NOT NULL CHECK(kind IN ('company','person','security','fund_structure','branch','government','international_organization','venue')),
    published_at timestamptz NOT NULL,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id)
);
CREATE TABLE mdm_v2.decision (
    decision_id text PRIMARY KEY,
    operation text NOT NULL CHECK(operation IN ('bind','merge','reverse','override','revoke','exclude','retire_source')),
    body jsonb NOT NULL,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id)
);
-- Current documents are disposable projections. Immutable effects hold history.
CREATE TABLE mdm_v2.projection (
    object_type text NOT NULL CHECK(object_type IN ('entity','relationship','review')),
    object_id text NOT NULL,
    body jsonb NOT NULL,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id),
    PRIMARY KEY(object_type,object_id)
);
CREATE TABLE mdm_v2.publication (
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id),
    consumer text NOT NULL,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    fence bigint NOT NULL DEFAULT 0,
    lease_until timestamptz,
    worker text,
    verified_at timestamptz,
    PRIMARY KEY(batch_id,consumer)
);
CREATE TABLE mdm_v2.publication_event (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id text NOT NULL,
    consumer text NOT NULL,
    fence bigint NOT NULL,
    event text NOT NULL CHECK(event IN ('claimed','verified','failed')),
    detail jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY(batch_id,consumer) REFERENCES mdm_v2.publication(batch_id,consumer)
);

-- Immutable history, even if future privilege grants drift.
CREATE FUNCTION mdm_v2.immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Clean MDM evidence and decisions are append-only'; END;
$$;
DO $$
DECLARE n text;
BEGIN
    FOREACH n IN ARRAY ARRAY['assertion','identity','decision','batch','observation','policy','dataset','publication_event','migration'] LOOP
        EXECUTE format('CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON mdm_v2.%I FOR EACH ROW EXECUTE FUNCTION mdm_v2.immutable_row()',n);
    END LOOP;
END;
$$;

-- A single capability commits bounded effects, checkpoint, history, and intent.
-- The application has no direct write privileges on any table in this schema.
CREATE FUNCTION mdm_v2.commit_batch(request_text text, root_run uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, mdm_v2 AS $$
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
    SELECT coalesce((SELECT position FROM mdm_v2.checkpoint WHERE consumer=r->>'consumer'),0) INTO pos;
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
        IF item->>'schema_version' IS DISTINCT FROM src.body->>'schema_version' THEN
            RAISE EXCEPTION 'Unsupported source schema';
        END IF;
        IF EXISTS(SELECT 1 FROM mdm_v2.assertion a WHERE a.assertion_id=item->>'assertion_id' AND a.body<>item) THEN
            RAISE EXCEPTION 'Assertion identity collision';
        END IF;
        INSERT INTO mdm_v2.assertion VALUES(item->>'assertion_id',item->>'source_code',item->>'record_key',
          item->>'publication_key',(item->>'revision')::bigint,(item->>'effective_at')::timestamptz,item,r->>'batch_id')
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
        INSERT INTO mdm_v2.projection VALUES(item->>'object_type',item->>'object_id',item->'body',r->>'batch_id')
        ON CONFLICT(object_type,object_id) DO UPDATE SET body=excluded.body,batch_id=excluded.batch_id;
    END LOOP;
    INSERT INTO mdm_v2.checkpoint VALUES(r->>'consumer',(r->>'checkpoint')::bigint,r->>'batch_id')
    ON CONFLICT(consumer) DO UPDATE SET position=excluded.position,batch_id=excluded.batch_id;
    outputs := jsonb_build_object('contract_version',2,'generation',next_generation,'run_id',root_run,
       'policy_digest',r->>'policy_digest','objects',r->'projections');
    FOR item IN SELECT value FROM jsonb_array_elements(required) LOOP
        delivered := CASE WHEN item#>>'{}'='journal' THEN outputs || jsonb_build_object('effects',r) ELSE outputs END;
        INSERT INTO mdm_v2.publication(batch_id,consumer,payload,payload_hash)
        VALUES(r->>'batch_id',item#>>'{}',delivered,encode(sha256(convert_to(delivered::text,'UTF8')),'hex'));
    END LOOP;
    RETURN jsonb_build_object('batch_id',r->>'batch_id','generation',next_generation,'duplicate',false);
END;
$$;

CREATE FUNCTION mdm_v2.claim_publication(destination text, owner_name text, lease_seconds integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE p mdm_v2.publication%ROWTYPE;
BEGIN
    IF lease_seconds NOT BETWEEN 1 AND 3600 OR nullif(owner_name,'') IS NULL THEN RAISE EXCEPTION 'Invalid lease'; END IF;
    -- Preserve generation order per consumer; an unexpired earlier claim blocks later delivery.
    SELECT q.* INTO p FROM mdm_v2.publication q JOIN mdm_v2.batch b USING(batch_id)
      WHERE q.consumer=destination AND q.verified_at IS NULL ORDER BY b.generation LIMIT 1 FOR UPDATE OF q;
    IF NOT FOUND OR p.lease_until > clock_timestamp() THEN RETURN NULL; END IF;
    UPDATE mdm_v2.publication SET fence=fence+1,worker=owner_name,
      lease_until=clock_timestamp()+make_interval(secs=>lease_seconds)
      WHERE batch_id=p.batch_id AND consumer=p.consumer RETURNING * INTO p;
    INSERT INTO mdm_v2.publication_event(batch_id,consumer,fence,event,detail)
      VALUES(p.batch_id,p.consumer,p.fence,'claimed',jsonb_build_object('worker',owner_name));
    RETURN to_jsonb(p);
END;
$$;
CREATE FUNCTION mdm_v2.finish_publication(batch_key text,destination text,token bigint,verified_hash text,failure text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE p mdm_v2.publication%ROWTYPE;
BEGIN
    SELECT * INTO p FROM mdm_v2.publication WHERE batch_id=batch_key AND consumer=destination FOR UPDATE;
    IF NOT FOUND OR p.verified_at IS NOT NULL OR p.fence<>token OR p.lease_until<=clock_timestamp() OR p.lease_until IS NULL THEN
        RAISE EXCEPTION 'Stale publication fence';
    END IF;
    IF failure IS NULL AND verified_hash IS DISTINCT FROM p.payload_hash THEN RAISE EXCEPTION 'Unverified publication'; END IF;
    INSERT INTO mdm_v2.publication_event(batch_id,consumer,fence,event,detail)
      VALUES(batch_key,destination,token,CASE WHEN failure IS NULL THEN 'verified' ELSE 'failed' END,
        jsonb_build_object('hash',verified_hash,'error',failure));
    UPDATE mdm_v2.publication SET verified_at=CASE WHEN failure IS NULL THEN clock_timestamp() ELSE NULL END,
      lease_until=NULL,worker=NULL WHERE batch_id=batch_key AND consumer=destination;
END;
$$;
REVOKE ALL ON ALL TABLES IN SCHEMA mdm_v2 FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mdm_v2 FROM PUBLIC;
