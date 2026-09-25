-- The latest-only Stage, written beside the retained history (company
-- mastering ticket 10, slice 1).
--
-- One row per source record, keyed by the source and the source's own record
-- number. It holds the winning reading, the snapshot every reading up to it
-- resolves to, and the bronze object that reading was delivered in. Nothing
-- reads it yet and nothing stops being written: mdm_v2.assertion stays
-- append-only until the readers move (slices 2-4).
--
-- A reading wins when its (revision, mapping version) is higher than the
-- row's. A duplicate or a late older delivery keeps the row. Two different
-- readings at one (revision, mapping version) are a source defect, refused as
-- survivorship.current_claims refuses them.
--
-- The snapshot has exactly the shape current_claims returns for the record,
-- so a PostgreSQL 16 test holds the two equal. A patch folds over the previous
-- snapshot: an unknown field keeps its value, a retract removes it, so a
-- sparse patch erases nothing it does not name.
CREATE TABLE mdm_v2.stage_record (
    source_code text NOT NULL REFERENCES mdm_v2.dataset(source_code),
    record_key text NOT NULL,
    subject text NOT NULL,
    kind text NOT NULL,
    revision bigint NOT NULL CHECK (revision >= 0),
    mapping_version bigint NOT NULL CHECK (mapping_version >= 1),
    publication_key text NOT NULL,
    assertion_id text NOT NULL REFERENCES mdm_v2.assertion(assertion_id),
    effective_at timestamptz,
    snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
    -- The bronze object the winning reading was delivered in: its object key,
    -- sha256 and the record's position inside it. Delivery details are not
    -- part of a source assertion (adapters.py), so they travel beside it in
    -- the batch. Null for readings stored before this migration and for a
    -- batch that names none; slice 4 makes it required.
    bronze jsonb CHECK (bronze IS NULL OR (jsonb_typeof(bronze) = 'object'
        AND bronze ?& ARRAY['object','sha256','locator'])),
    batch_id text NOT NULL REFERENCES mdm_v2.batch(batch_id),
    PRIMARY KEY (source_code, record_key),
    UNIQUE (subject)
);
CREATE INDEX stage_record_kind ON mdm_v2.stage_record(kind, source_code);

-- A field item as current_claims keeps it: the operation, plus the reading
-- that stated it.
CREATE FUNCTION mdm_v2.stage_claim(item jsonb, a jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,mdm_v2 AS $$
    SELECT item || jsonb_build_object(
        'assertion_id', a->'assertion_id', 'source_code', a->'source_code',
        'record_key', a->'record_key', 'effective_at', a->'effective_at')
$$;

-- survivorship.profile_key: sha256 of the canonical JSON array of a profile's
-- five identifying values. Canonical means no spaces, which jsonb's own text
-- form does not give, so the array is written element by element.
CREATE FUNCTION mdm_v2.stage_profile_key(profile jsonb) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,mdm_v2 AS $$
    SELECT encode(sha256(convert_to('[' || string_agg(
        CASE WHEN profile->part IS NULL OR jsonb_typeof(profile->part) = 'null'
             THEN 'null' ELSE (profile->part)::text END, ',' ORDER BY n) || ']',
        'UTF8')), 'hex')
    FROM unnest(ARRAY['role','authority','registration','jurisdiction','valid_from'])
        WITH ORDINALITY AS parts(part, n)
$$;

-- One reading folded over the record's previous snapshot, as current_claims
-- folds each version in order.
CREATE FUNCTION mdm_v2.stage_fold(previous jsonb, a jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE
    claims jsonb := coalesce(previous->'fields', '{}'::jsonb);
    before jsonb := coalesce(previous->'profile_fields', '{}'::jsonb);
    continuing jsonb := '{}'::jsonb;
    values_of jsonb;
    field record;
    profile jsonb;
    profile_id text;
    item jsonb;
BEGIN
    FOR field IN SELECT f.key AS name, f.value AS item
                 FROM jsonb_each(coalesce(a->'fields', '{}'::jsonb)) f LOOP
        IF field.item->>'op' = 'unknown' THEN
            CONTINUE;
        ELSIF field.item->>'op' = 'retract' THEN
            claims := claims - field.name;
        ELSE
            claims := claims || jsonb_build_object(field.name, mdm_v2.stage_claim(field.item, a));
        END IF;
    END LOOP;
    FOR profile IN SELECT value FROM jsonb_array_elements(coalesce(a->'profiles', '[]'::jsonb)) LOOP
        profile_id := mdm_v2.stage_profile_key(profile);
        values_of := coalesce(before->profile_id, '{}'::jsonb);
        FOR field IN SELECT f.key AS name, f.value AS item
                     FROM jsonb_each(coalesce(profile->'fields', '{}'::jsonb)) f LOOP
            item := CASE
                WHEN jsonb_typeof(field.item) = 'object' AND field.item ? 'op' THEN field.item
                WHEN jsonb_typeof(field.item) = 'null' THEN '{"op":"unknown"}'::jsonb
                ELSE jsonb_build_object('op', 'value', 'value', field.item) END;
            IF item->>'op' = 'unknown' THEN
                CONTINUE;
            ELSIF item->>'op' = 'retract' THEN
                values_of := values_of - field.name;
            ELSIF item->>'op' IN ('value', 'clear') THEN
                IF item->>'op' = 'value' AND (item->'value' IS NULL OR jsonb_typeof(item->'value') = 'null') THEN
                    RAISE EXCEPTION 'Use unknown for null profile evidence';
                END IF;
                values_of := values_of || jsonb_build_object(field.name, mdm_v2.stage_claim(item, a));
            ELSE
                RAISE EXCEPTION 'Unknown profile field operation';
            END IF;
        END LOOP;
        continuing := continuing || jsonb_build_object(profile_id, values_of);
    END LOOP;
    RETURN jsonb_build_object(
        'kind', a->'kind',
        'fields', claims,
        'identifiers', a->'identifiers',
        'profiles', a->'profiles',
        'profile_fields', continuing,
        'relationships', a->'relationships',
        'assertion_id', a->'assertion_id',
        'source_meta', jsonb_build_object(
            'source_code', a->'source_code', 'record_key', a->'record_key',
            'effective_at', a->'effective_at'));
END;
$$;

-- Keep the Stage row for one newly stored reading.
CREATE FUNCTION mdm_v2.record_stage(a jsonb, source_batch text) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE
    current_row mdm_v2.stage_record%ROWTYPE;
    reading bigint[] := ARRAY[(a->>'revision')::bigint,
                              coalesce((a->>'mapping_version')::bigint, 1)];
BEGIN
    SELECT * INTO current_row FROM mdm_v2.stage_record
      WHERE source_code = a->>'source_code' AND record_key = a->>'record_key'
      FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO mdm_v2.stage_record VALUES (
            a->>'source_code', a->>'record_key', a->>'subject', a->>'kind',
            reading[1], reading[2], a->>'publication_key', a->>'assertion_id',
            (a->>'effective_at')::timestamptz, mdm_v2.stage_fold(NULL, a), NULL,
            source_batch);
        RETURN;
    END IF;
    IF reading = ARRAY[current_row.revision, current_row.mapping_version] THEN
        IF current_row.assertion_id IS DISTINCT FROM a->>'assertion_id' THEN
            RAISE EXCEPTION 'Source native revision has contradictory publications';
        END IF;
        RETURN;
    END IF;
    IF reading < ARRAY[current_row.revision, current_row.mapping_version] THEN
        RETURN;  -- a late older delivery keeps the current row
    END IF;
    UPDATE mdm_v2.stage_record SET
        subject = a->>'subject', kind = a->>'kind',
        revision = reading[1], mapping_version = reading[2],
        publication_key = a->>'publication_key', assertion_id = a->>'assertion_id',
        effective_at = (a->>'effective_at')::timestamptz,
        snapshot = mdm_v2.stage_fold(current_row.snapshot, a),
        bronze = NULL, batch_id = source_batch
      WHERE source_code = current_row.source_code AND record_key = current_row.record_key;
END;
$$;

CREATE FUNCTION mdm_v2.stage_assertion() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,mdm_v2 AS $$
BEGIN
    PERFORM mdm_v2.record_stage(NEW.body, NEW.batch_id);
    RETURN NEW;
END;
$$;

-- Backfill in arrival order: each batch by generation, each reading in the
-- order its batch carried it, exactly as the trigger below would have kept it.
DO $$
DECLARE a record;
BEGIN
    FOR a IN
        SELECT s.body, s.batch_id
        FROM mdm_v2.batch b
        CROSS JOIN LATERAL jsonb_array_elements(coalesce(b.effects->'assertions', '[]'::jsonb))
            WITH ORDINALITY AS item(value, n)
        JOIN mdm_v2.assertion s
          ON s.assertion_id = item.value->>'assertion_id' AND s.batch_id = b.batch_id
        ORDER BY b.generation, item.n
    LOOP
        PERFORM mdm_v2.record_stage(a.body, a.batch_id);
    END LOOP;
    IF (SELECT count(*) FROM mdm_v2.stage_record)
       IS DISTINCT FROM (SELECT count(DISTINCT (source_code, record_key)) FROM mdm_v2.assertion) THEN
        RAISE EXCEPTION 'Stage backfill missed a stored source record';
    END IF;
END;
$$;

CREATE TRIGGER stage_assertion AFTER INSERT ON mdm_v2.assertion
    FOR EACH ROW EXECUTE FUNCTION mdm_v2.stage_assertion();

-- The batch names each reading's bronze object beside it. Set it on the
-- Stage row only while that reading is the row's winner, after the core has
-- stored the batch's readings. Exact-fragment guard, as 029 and 031 use.
DO $$
DECLARE definition text; old_fragment text; new_fragment text;
BEGIN
    SELECT pg_get_functiondef('mdm_v2.commit_batch_evidence(text,uuid)'::regprocedure) INTO definition;
    old_fragment := $old$        RAISE EXCEPTION 'Deferred evidence requires its registered open review disposition';
    END IF;
    RETURN result;$old$;
    new_fragment := $new$        RAISE EXCEPTION 'Deferred evidence requires its registered open review disposition';
    END IF;
    IF coalesce((result->>'duplicate')::boolean, false) IS FALSE THEN
        FOR item IN SELECT value FROM jsonb_array_elements(coalesce(r->'occurrences','[]')) LOOP
            IF jsonb_typeof(item) IS DISTINCT FROM 'object'
               OR NOT (item ?& ARRAY['assertion_id','object','sha256','locator'])
               OR nullif(item->>'object','') IS NULL OR nullif(item->>'locator','') IS NULL
               OR coalesce(item->>'sha256','') !~ '^[0-9a-f]{64}$'
               OR NOT EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(r->'assertions','[]')) x
                              WHERE x->>'assertion_id' = item->>'assertion_id') THEN
                RAISE EXCEPTION 'Invalid bronze occurrence';
            END IF;
            UPDATE mdm_v2.stage_record SET bronze = jsonb_build_object(
                    'object', item->>'object', 'sha256', item->>'sha256', 'locator', item->>'locator')
              WHERE assertion_id = item->>'assertion_id' AND bronze IS NULL;
        END LOOP;
    END IF;
    RETURN result;$new$;
    IF position(old_fragment IN definition) = 0 THEN
        RAISE EXCEPTION 'Unexpected evidence wrapper return';
    END IF;
    EXECUTE replace(definition, old_fragment, new_fragment);
END;
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA mdm_v2 FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mdm_v2 FROM PUBLIC;
