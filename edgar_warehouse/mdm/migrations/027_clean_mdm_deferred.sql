-- Unsupported records remain durable evidence and block required completeness.
CREATE TABLE mdm_v2.deferred_record (
    deferred_id text PRIMARY KEY,
    source_code text NOT NULL REFERENCES mdm_v2.dataset(source_code),
    publication_key text NOT NULL,
    record_locator text NOT NULL,
    body jsonb NOT NULL,
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id),
    UNIQUE(source_code,publication_key,record_locator)
);
CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON mdm_v2.deferred_record
    FOR EACH ROW EXECUTE FUNCTION mdm_v2.immutable_row();

-- Preserve the installed 023 implementation/checksum and its single transaction.
ALTER FUNCTION mdm_v2.commit_batch(text,uuid) RENAME TO commit_batch_core;
CREATE FUNCTION mdm_v2.commit_batch(request_text text, root_run uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE r jsonb := request_text::jsonb; item jsonb; src mdm_v2.dataset%ROWTYPE;
    result jsonb; old mdm_v2.deferred_record%ROWTYPE;
BEGIN
    IF coalesce(jsonb_array_length(r->'deferred'),0)>1000 OR
       coalesce(jsonb_array_length(r->'deferred'),0)+coalesce(jsonb_array_length(r->'assertions'),0)>1000 THEN
        RAISE EXCEPTION 'Unbounded source records';
    END IF;
    IF (r ? 'source_accounting' OR coalesce(jsonb_array_length(r->'deferred'),0)>0)
       AND r->'source_accounting' IS DISTINCT FROM jsonb_build_object(
           'normalized',coalesce(jsonb_array_length(r->'assertions'),0),
           'deferred',coalesce(jsonb_array_length(r->'deferred'),0),
           'total',coalesce(jsonb_array_length(r->'assertions'),0)+coalesce(jsonb_array_length(r->'deferred'),0)) THEN
        RAISE EXCEPTION 'Invalid source accounting';
    END IF;
    result := mdm_v2.commit_batch_core(request_text,root_run);
    FOR item IN SELECT value FROM jsonb_array_elements(coalesce(r->'deferred','[]')) LOOP
        IF NOT (item ?& ARRAY['deferred_id','source_code','publication_key','record_locator','schema_version','reason','raw_record','provenance'])
           OR item->>'deferred_id' IS NULL OR item->>'record_locator' IS NULL
           OR item->>'publication_key' IS NULL OR item->>'reason' IS NULL THEN
            RAISE EXCEPTION 'Invalid deferred source evidence';
        END IF;
        SELECT * INTO src FROM mdm_v2.dataset WHERE source_code=item->>'source_code';
        IF NOT FOUND OR src.body->>'schema_version' IS DISTINCT FROM item->>'schema_version' THEN
            RAISE EXCEPTION 'Unknown deferred dataset contract';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(coalesce(r->'projections','[]')) p
            WHERE p->>'object_type'='review' AND p->>'object_id'=item->>'deferred_id'
              AND p->'body'->>'deferred_id'=item->>'deferred_id'
              AND p->'body'->'open'='true'::jsonb
              AND p->'body'->'blocking'='true'::jsonb
              AND coalesce(p->'body'->'retired','false'::jsonb)='false'::jsonb
        ) THEN
            RAISE EXCEPTION 'Deferred evidence requires an open blocking review in its batch';
        END IF;
        INSERT INTO mdm_v2.deferred_record VALUES(item->>'deferred_id',item->>'source_code',
            item->>'publication_key',item->>'record_locator',item,r->>'batch_id') ON CONFLICT DO NOTHING;
        SELECT * INTO old FROM mdm_v2.deferred_record WHERE source_code=item->>'source_code'
            AND publication_key=item->>'publication_key' AND record_locator=item->>'record_locator';
        IF NOT FOUND OR old.body IS DISTINCT FROM item THEN
            RAISE EXCEPTION 'Deferred source publication collision';
        END IF;
    END LOOP;
    -- Check durable state after the core write, including attempts to close a
    -- prior deferred review. A future resolution capability needs its own
    -- audited disposition contract before this invariant can be relaxed.
    IF EXISTS (
        SELECT 1 FROM mdm_v2.deferred_record d
        LEFT JOIN mdm_v2.projection p ON p.object_type='review' AND p.object_id=d.deferred_id
        WHERE p.body->>'deferred_id' IS DISTINCT FROM d.deferred_id
           OR p.body->'open' IS DISTINCT FROM 'true'::jsonb
           OR p.body->'blocking' IS DISTINCT FROM 'true'::jsonb
           OR coalesce(p.body->'retired','false'::jsonb) IS DISTINCT FROM 'false'::jsonb
    ) THEN
        RAISE EXCEPTION 'Deferred evidence requires an open blocking review';
    END IF;
    RETURN result;
END;
$$;
REVOKE ALL ON FUNCTION mdm_v2.commit_batch(text,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION mdm_v2.commit_batch_core(text,uuid) FROM PUBLIC;
