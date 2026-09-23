-- A mapping may be corrected without re-binding every record of its source.
--
-- A Dataset Contract's mapping version is the platform's own reading number,
-- not the source's schema_version. It is hashed into the assertion body, so a
-- second reading of one publication is a distinct assertion, and is lifted
-- into a column here for indexing exactly as source_code, record_key,
-- publication_key and revision already are. source_code never changes, so no
-- subject moves and no Company is re-bound.
--
-- Nothing is deleted or rewritten: existing assertions take the default and
-- keep their ids, and every registered reading is retained. The store stays
-- append-only (company mastering ticket 01, amendments 7-9).
ALTER TABLE mdm_v2.assertion
    ADD COLUMN mapping_version bigint NOT NULL DEFAULT 1 CHECK (mapping_version >= 1);

-- A second reading of one publication is a second row, not a unique violation.
DO $$
DECLARE constraint_name text;
BEGIN
    SELECT conname INTO constraint_name FROM pg_constraint
    WHERE conrelid='mdm_v2.assertion'::regclass AND contype='u'
      AND (SELECT array_agg(attname::text ORDER BY attname::text) FROM pg_attribute
           WHERE attrelid=conrelid AND attnum=ANY(conkey))
          =ARRAY['publication_key','record_key','source_code'];
    IF constraint_name IS NULL THEN
        RAISE EXCEPTION 'Unexpected assertion publication uniqueness';
    END IF;
    EXECUTE format('ALTER TABLE mdm_v2.assertion DROP CONSTRAINT %I',constraint_name);
END;
$$;
ALTER TABLE mdm_v2.assertion
    ADD UNIQUE (source_code,record_key,publication_key,mapping_version);
CREATE INDEX ON mdm_v2.assertion(source_code,mapping_version);

-- Every registered reading of a source, version 1 included. The current
-- version is the highest row, never a stored pointer: mdm_v2.dataset carries
-- the append-only trigger installed in migration 023, so a mutable "current"
-- column on it could never be updated.
CREATE TABLE mdm_v2.dataset_mapping (
    source_code text NOT NULL REFERENCES mdm_v2.dataset(source_code),
    mapping_version bigint NOT NULL CHECK (mapping_version >= 1),
    body jsonb NOT NULL CHECK (jsonb_typeof(body) = 'object'),
    registry_version uuid NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_code,mapping_version)
);
CREATE TRIGGER immutable_row BEFORE UPDATE OR DELETE ON mdm_v2.dataset_mapping
    FOR EACH ROW EXECUTE FUNCTION mdm_v2.immutable_row();

-- Every contract registered before this migration is its source's reading 1.
INSERT INTO mdm_v2.dataset_mapping(source_code,mapping_version,body,registry_version)
SELECT source_code,1,body,registry_version FROM mdm_v2.dataset;

-- Amend only the assertion write and its schema check. Exact-fragment guards
-- fail the migration if that implementation has drifted, and every other
-- evidence/decision/publication check keeps its historical checksum.
DO $$
DECLARE definition text; old_fragment text; new_fragment text;
BEGIN
    SELECT pg_get_functiondef('mdm_v2.commit_batch_core(text,uuid)'::regprocedure) INTO definition;

    -- The reading a batch was produced under must itself be registered, and
    -- the source schema is checked against that reading's body rather than
    -- only the newest, so a batch from any registered reading still applies.
    old_fragment := $old$        IF item->>'schema_version' IS DISTINCT FROM src.body->>'schema_version' THEN
            RAISE EXCEPTION 'Unsupported source schema';
        END IF;$old$;
    new_fragment := $new$        IF NOT EXISTS(SELECT 1 FROM mdm_v2.dataset_mapping m
            WHERE m.source_code=item->>'source_code'
              AND m.mapping_version=coalesce((item->>'mapping_version')::bigint,1)
              AND m.body->>'schema_version' IS NOT DISTINCT FROM item->>'schema_version') THEN
            RAISE EXCEPTION 'Unsupported source schema';
        END IF;$new$;
    IF position(old_fragment IN definition)=0 THEN RAISE EXCEPTION 'Unexpected core schema check'; END IF;
    definition := replace(definition,old_fragment,new_fragment);

    -- Name the columns: a positional insert would silently write the default
    -- and drop the reading the body states.
    old_fragment := $old$        INSERT INTO mdm_v2.assertion VALUES(item->>'assertion_id',item->>'source_code',item->>'record_key',
          item->>'publication_key',(item->>'revision')::bigint,(item->>'effective_at')::timestamptz,item,r->>'batch_id')
          ON CONFLICT(assertion_id) DO NOTHING;$old$;
    new_fragment := $new$        INSERT INTO mdm_v2.assertion(assertion_id,source_code,record_key,publication_key,
          revision,effective_at,body,batch_id,mapping_version)
          VALUES(item->>'assertion_id',item->>'source_code',item->>'record_key',
          item->>'publication_key',(item->>'revision')::bigint,(item->>'effective_at')::timestamptz,item,r->>'batch_id',
          coalesce((item->>'mapping_version')::bigint,1))
          ON CONFLICT(assertion_id) DO NOTHING;$new$;
    IF position(old_fragment IN definition)=0 THEN RAISE EXCEPTION 'Unexpected core assertion write'; END IF;
    definition := replace(definition,old_fragment,new_fragment);
    EXECUTE definition;
END;
$$;
