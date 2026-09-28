-- One append-only table. No control state, source rows or imported history.
CREATE SCHEMA journal;
REVOKE ALL ON SCHEMA journal FROM PUBLIC;
CREATE FUNCTION journal.canonical(p jsonb) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,journal AS $$
  SELECT CASE jsonb_typeof(p)
    WHEN 'object' THEN (SELECT '{'||coalesce(string_agg(to_jsonb(key)::text||':'||journal.canonical(value),',' ORDER BY key COLLATE "C"),'')||'}' FROM jsonb_each(p))
    WHEN 'array' THEN (SELECT '['||coalesce(string_agg(journal.canonical(value),',' ORDER BY ordinal),'')||']' FROM jsonb_array_elements(p) WITH ORDINALITY AS a(value,ordinal))
    ELSE p::text END
$$;
CREATE TABLE journal.event (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  producer text NOT NULL,
  event_key text NOT NULL,
  run_id uuid NOT NULL,
  source text NOT NULL,
  feed text NOT NULL,
  event_type text NOT NULL,
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  canonical_body text NOT NULL,
  canonical_hash text NOT NULL CHECK(canonical_hash ~ '^[0-9a-f]{64}$'),
  UNIQUE(producer,event_key),
  CHECK(canonical_hash=encode(sha256(convert_to(canonical_body,'UTF8')),'hex')),
  CHECK(canonical_body=journal.canonical(canonical_body::jsonb))
);
CREATE INDEX event_scope ON journal.event(source,feed,id);
CREATE INDEX event_run ON journal.event(run_id,id);

CREATE FUNCTION journal.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Change Journal is append-only'; END;
$$;
CREATE TRIGGER immutable_event BEFORE UPDATE OR DELETE OR TRUNCATE ON journal.event
FOR EACH STATEMENT EXECUTE FUNCTION journal.immutable();

CREATE FUNCTION journal.receipt(e journal.event) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,journal AS $$
  SELECT jsonb_build_object('id',e.id,'canonical_hash',e.canonical_hash,
    'recorded_at',to_char(e.recorded_at AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'event',e.canonical_body::jsonb)
$$;

CREATE FUNCTION journal.append(body text,h text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,journal AS $$
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
$$;

CREATE FUNCTION journal.get(p text,k text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER STABLE SET search_path=pg_catalog,journal AS $$
  SELECT journal.receipt(e) FROM journal.event e WHERE producer=p AND event_key=k
$$;
CREATE FUNCTION journal.list_events(s text,f text,r uuid,n integer,a bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER STABLE SET search_path=pg_catalog,journal AS $$
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
CREATE FUNCTION journal.status(s text,f text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER STABLE SET search_path=pg_catalog,journal AS $$
  SELECT jsonb_build_object('database',current_database(),'events',count(*),'last_id',max(id),
    'source',s,'feed',f) FROM journal.event WHERE (s IS NULL OR source=s) AND (f IS NULL OR feed=f)
$$;
REVOKE ALL ON ALL TABLES IN SCHEMA journal FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA journal FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA journal FROM PUBLIC;
