DO $$ DECLARE c record; BEGIN
          FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='journal.event'::regclass
            AND pg_get_constraintdef(oid) LIKE '%journal.canonical%' LOOP
            EXECUTE format('ALTER TABLE journal.event DROP CONSTRAINT %I',c.conname);
          END LOOP;
        END $$
-- journal migration statement boundary --
DROP FUNCTION IF EXISTS journal.append(text,text)
-- journal migration statement boundary --
DROP FUNCTION IF EXISTS journal.get(text,text)
-- journal migration statement boundary --
DROP FUNCTION IF EXISTS journal.list_events(text,text,uuid,integer,bigint)
-- journal migration statement boundary --
DROP FUNCTION IF EXISTS journal.status(text,text)
-- journal migration statement boundary --
DROP FUNCTION IF EXISTS journal.found(text,text[])
-- journal migration statement boundary --
DROP FUNCTION IF EXISTS journal.receipt(journal.event)
-- journal migration statement boundary --
DROP FUNCTION IF EXISTS journal.canonical(jsonb)
-- journal migration statement boundary --
CREATE OR REPLACE FUNCTION journal.address_event_key(k text) RETURNS bytea
          LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS 'SELECT sha256(convert_to(k,''UTF8''))'
-- journal migration statement boundary --
ALTER TABLE journal.event ADD COLUMN IF NOT EXISTS key_hash bytea GENERATED ALWAYS AS (journal.address_event_key(event_key)) STORED
-- journal migration statement boundary --
ALTER TABLE journal.event DROP CONSTRAINT IF EXISTS event_producer_event_key_key
-- journal migration statement boundary --
CREATE UNIQUE INDEX IF NOT EXISTS event_key_unique ON journal.event(producer,key_hash)
-- journal migration statement boundary --
CREATE OR REPLACE VIEW journal.event_records AS
          SELECT id,producer,event_key,key_hash,run_id::text,source,feed,event_type,
            occurred_at::text,recorded_at,canonical_body,canonical_hash FROM journal.event
-- journal migration statement boundary --
CREATE OR REPLACE FUNCTION journal.record_event(body text,h text) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,journal AS $$
        DECLARE p jsonb:=body::jsonb; prior journal.event%ROWTYPE;
        BEGIN
          IF h IS NULL OR h !~ '^[0-9a-f]{64}$' OR octet_length(body)>1048576
            OR encode(sha256(convert_to(body,'UTF8')),'hex')<>h OR jsonb_typeof(p)<>'object'
            OR p->'version' IS DISTINCT FROM '1'::jsonb OR (SELECT count(*) FROM jsonb_object_keys(p))<>10
            OR NOT p ?& ARRAY['version','producer','event_key','run_id','source','feed','event_type','occurred_at','scope','evidence']
            OR length(p->>'event_key') NOT BETWEEN 1 AND 2048 THEN
            RAISE EXCEPTION 'Invalid prepared journal event';
          END IF;
          INSERT INTO journal.event(producer,event_key,run_id,source,feed,event_type,occurred_at,canonical_body,canonical_hash)
            VALUES(p->>'producer',p->>'event_key',(p->>'run_id')::uuid,p->>'source',p->>'feed',p->>'event_type',
              (p->>'occurred_at')::timestamptz,body,h) ON CONFLICT(producer,key_hash) DO NOTHING;
          SELECT * INTO STRICT prior FROM journal.event WHERE producer=p->>'producer' AND key_hash=journal.address_event_key(p->>'event_key');
          IF prior.event_key<>p->>'event_key' OR prior.canonical_body<>body OR prior.canonical_hash<>h THEN
            RAISE EXCEPTION 'journal_content_conflict' USING ERRCODE='23505';
          END IF;
        END $$
-- journal migration statement boundary --
REVOKE ALL ON FUNCTION journal.record_event(text,text) FROM PUBLIC