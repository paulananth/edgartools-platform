-- Only the run metadata for one configured document is read when choosing
-- its latest capture. The hash is a storage address, checked against the
-- original kind/name/target by the reader; it makes no control decision.
CREATE FUNCTION bookkeeping.document_lookup_key(s jsonb) RETURNS bytea
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog AS $$
  SELECT sha256(convert_to((s->>'kind')||':'||(s->>'name')||':'||(s->>'target'),'UTF8'))
$$;
REVOKE ALL ON FUNCTION bookkeeping.document_lookup_key(jsonb) FROM PUBLIC;
ALTER TABLE bookkeeping.pipeline_run ADD COLUMN document_hash bytea
  GENERATED ALWAYS AS (bookkeeping.document_lookup_key(submission)) STORED;
CREATE INDEX run_document_lookup ON bookkeeping.pipeline_run(document_hash,created_at,run_id);
