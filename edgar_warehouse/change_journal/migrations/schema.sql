-- The Change Journal's schema: one append-only event table and the function that records an event once.
-- `change-journal init` creates it in an empty database, then applies the engine's native storage
-- statements (native/); a later change is a numbered file beside this one.
SET LOCAL check_function_bodies = false;


CREATE SCHEMA journal;

CREATE FUNCTION journal.append(body text, h text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'journal'
    AS $_$
DECLARE p jsonb := body::jsonb; prior journal.event%ROWTYPE; ref jsonb;
BEGIN
  IF octet_length(body)>1048576 OR jsonb_typeof(p) IS DISTINCT FROM 'object' OR p->'version' IS DISTINCT FROM '1'::jsonb OR p->>'version'<>'1'
    OR (SELECT count(*) FROM jsonb_object_keys(p))<>10
    OR NOT p ?& ARRAY['version','producer','event_key','run_id','source','feed','event_type','occurred_at','scope','evidence']
    OR h IS NULL OR h !~ '^[0-9a-f]{64}$'
    OR encode(sha256(convert_to(body,'UTF8')),'hex')<>h THEN
    RAISE EXCEPTION 'Invalid Change Journal envelope';
  END IF;
  IF EXISTS(SELECT 1 FROM jsonb_each(p) WHERE key IN ('producer','event_key','run_id','source','feed','event_type','occurred_at')
      AND (jsonb_typeof(value)<>'string' OR value #>> '{}'=''))
    OR length(p->>'event_key')>2048
    OR (p->>'run_id')::uuid::text<>p->>'run_id'
    OR p->>'occurred_at' !~ '(Z|\+00:00)$'
    OR jsonb_typeof(p->'scope') IS DISTINCT FROM 'object'
    OR jsonb_typeof(p->'evidence') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'Invalid journal identity or scope';
  END IF;
  IF EXISTS(SELECT 1 FROM jsonb_each(p->'scope') WHERE key='' OR jsonb_typeof(value)<>'string' OR value #>> '{}'='')
    OR (SELECT count(*) FROM jsonb_object_keys(p->'scope'))>32
    OR jsonb_array_length(p->'evidence') NOT BETWEEN 1 AND 100 THEN
    RAISE EXCEPTION 'Invalid journal evidence';
  END IF;
  FOR ref IN SELECT value FROM jsonb_array_elements(p->'evidence') LOOP
    IF jsonb_typeof(ref) IS DISTINCT FROM 'object' OR NOT ref ?& ARRAY['uri','sha256']
      OR (SELECT count(*) FROM jsonb_object_keys(ref))<>2
      OR jsonb_typeof(ref->'uri') IS DISTINCT FROM 'string' OR ref->>'uri'=''
      OR jsonb_typeof(ref->'sha256') IS DISTINCT FROM 'string' OR ref->>'sha256' !~ '^[0-9a-f]{64}$' THEN
      RAISE EXCEPTION 'Invalid journal evidence reference';
    END IF;
  END LOOP;
  IF EXISTS(SELECT 1 FROM jsonb_each(p) WHERE key IN ('producer','source','feed','event_type')
    AND value #>> '{}' !~ '^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$')
    OR body<>journal.canonical(p) THEN
    RAISE EXCEPTION 'Journal requires canonical envelope content'; END IF;
  INSERT INTO journal.event(producer,event_key,run_id,source,feed,event_type,occurred_at,canonical_body,canonical_hash)
    VALUES(p->>'producer',p->>'event_key',(p->>'run_id')::uuid,p->>'source',p->>'feed',p->>'event_type',
      (p->>'occurred_at')::timestamptz,body,h) ON CONFLICT(producer,event_key) DO NOTHING;
  SELECT * INTO STRICT prior FROM journal.event WHERE producer=p->>'producer' AND event_key=p->>'event_key';
  IF prior.canonical_body<>body OR prior.canonical_hash<>h THEN
    RAISE EXCEPTION 'Conflicting producer event content' USING ERRCODE='23505';
  END IF;
  RETURN journal.receipt(prior);
END;
$_$;

CREATE FUNCTION journal.canonical(p jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog', 'journal'
    AS $$
  SELECT CASE jsonb_typeof(p)
    WHEN 'object' THEN (SELECT '{'||coalesce(string_agg(to_jsonb(key)::text||':'||journal.canonical(value),',' ORDER BY key COLLATE "C"),'')||'}' FROM jsonb_each(p))
    WHEN 'array' THEN (SELECT '['||coalesce(string_agg(journal.canonical(value),',' ORDER BY ordinal),'')||']' FROM jsonb_array_elements(p) WITH ORDINALITY AS a(value,ordinal))
    ELSE p::text END
$$;

CREATE FUNCTION journal.found(p text, k text[]) RETURNS text[]
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'journal'
    SET plan_cache_mode TO 'force_custom_plan'
    AS $$
DECLARE result text[];
BEGIN
  IF p IS NULL OR k IS NULL OR cardinality(k)>10000 THEN
    RAISE EXCEPTION 'Journal lookup requires a producer and at most 10000 keys'; END IF;
  SELECT coalesce(array_agg(e.event_key ORDER BY e.event_key),'{}') INTO result
    FROM (SELECT DISTINCT key FROM unnest(k) AS u(key)) u
    JOIN journal.event e ON e.producer=p AND e.event_key=u.key;
  RETURN result;
END;
$$;

CREATE FUNCTION journal.get(p text, k text) RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'journal'
    AS $$
  SELECT journal.receipt(e) FROM journal.event e WHERE producer=p AND event_key=k
$$;

CREATE FUNCTION journal.immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN RAISE EXCEPTION 'Change Journal is append-only'; END;
$$;

CREATE FUNCTION journal.list_events(s text, f text, r uuid, n integer, a bigint) RETURNS jsonb
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'journal'
    AS $$
DECLARE result jsonb;
BEGIN
  IF n IS NULL OR n NOT BETWEEN 1 AND 1000 OR a IS NULL OR a<0 THEN
    RAISE EXCEPTION 'Journal inspection requires bounded limit and cursor'; END IF;
  SELECT coalesce(jsonb_agg(journal.receipt(e) ORDER BY e.id),'[]') INTO result FROM (
    SELECT * FROM journal.event WHERE (s IS NULL OR source=s) AND (f IS NULL OR feed=f)
      AND (r IS NULL OR run_id=r) AND id>a ORDER BY id LIMIT n) e;
  RETURN result;
END;
$$;

CREATE TABLE journal.event (
    id bigint NOT NULL,
    producer text NOT NULL,
    event_key text NOT NULL,
    run_id uuid NOT NULL,
    source text NOT NULL,
    feed text NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    recorded_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    canonical_body text NOT NULL,
    canonical_hash text NOT NULL,
    CONSTRAINT event_canonical_body_check CHECK ((canonical_body = journal.canonical((canonical_body)::jsonb))),
    CONSTRAINT event_canonical_hash_check CHECK ((canonical_hash ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT event_check CHECK ((canonical_hash = encode(sha256(convert_to(canonical_body, 'UTF8'::name)), 'hex'::text)))
);

CREATE FUNCTION journal.receipt(e journal.event) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog', 'journal'
    AS $$
  SELECT jsonb_build_object('id',e.id,'canonical_hash',e.canonical_hash,
    'recorded_at',to_char(e.recorded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'event',e.canonical_body::jsonb)
$$;

CREATE FUNCTION journal.status(s text, f text) RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'journal'
    AS $$
  SELECT jsonb_build_object('database',current_database(),'events',count(*),'last_id',max(id),
    'source',s,'feed',f) FROM journal.event WHERE (s IS NULL OR source=s) AND (f IS NULL OR feed=f)
$$;

ALTER TABLE journal.event ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME journal.event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

ALTER TABLE ONLY journal.event
    ADD CONSTRAINT event_pkey PRIMARY KEY (id);

ALTER TABLE ONLY journal.event
    ADD CONSTRAINT event_producer_event_key_key UNIQUE (producer, event_key);

CREATE INDEX event_run ON journal.event USING btree (run_id, id);

CREATE INDEX event_scope ON journal.event USING btree (source, feed, id);

CREATE TRIGGER immutable_event BEFORE DELETE OR UPDATE OR TRUNCATE ON journal.event FOR EACH STATEMENT EXECUTE FUNCTION journal.immutable();

