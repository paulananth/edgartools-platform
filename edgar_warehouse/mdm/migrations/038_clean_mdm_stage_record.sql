-- The latest-only Stage, written beside the retained history (company
-- mastering ticket 10, slice 1).
--
-- One row per source record, keyed by the source and the source's own record
-- number. It holds the winning reading, the snapshot the readings it has
-- accepted resolve to, and the bronze object the winner was delivered in.
-- Nothing reads it yet and nothing stops being written: mdm_v2.assertion
-- stays append-only until the readers move (slices 2-4).
--
-- A reading wins when its (revision, mapping version) is higher than the
-- row's, and folds over the row's snapshot: an unknown field keeps its value,
-- a retract removes it, so a sparse patch erases nothing it does not name.
-- A duplicate, or an older reading delivered in a later batch, keeps the row
-- (the ticket's contract). Within one batch the readings are taken in
-- (revision, mapping version) order, never the batch's hash order. So when
-- each record's readings arrive in revision order, the snapshot equals what
-- survivorship.current_claims reads from the full history, in its shape; a
-- PostgreSQL 16 test holds the two equal.
--
-- Two different readings at one (revision, mapping version) are a source
-- defect, refused as current_claims refuses them. Only the row's own winner
-- can be compared: a clash with an older reading it replaced goes unseen,
-- which is what keeping only the latest row means.
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
-- form does not give, so the array is written element by element. A string
-- prints as Python prints it; anything but a string or null is refused
-- rather than hashed differently.
CREATE FUNCTION mdm_v2.stage_profile_key(profile jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,mdm_v2 AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM unnest(ARRAY['role','authority','registration','jurisdiction','valid_from']) part
               WHERE coalesce(jsonb_typeof(profile->part), 'null') NOT IN ('string', 'null')) THEN
        RAISE EXCEPTION 'Profile identifying values must be text';
    END IF;
    RETURN (SELECT encode(sha256(convert_to('[' || string_agg(
        coalesce((profile->part)::text, 'null'), ',' ORDER BY n) || ']', 'UTF8')), 'hex')
        FROM unnest(ARRAY['role','authority','registration','jurisdiction','valid_from'])
            WITH ORDINALITY AS parts(part, n));
END;
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

-- Keep the Stage row for one newly stored reading. `occurrence` is the bronze
-- object the batch names for it, or null.
CREATE FUNCTION mdm_v2.record_stage(a jsonb, source_batch text, occurrence jsonb)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE
    current_row mdm_v2.stage_record%ROWTYPE;
    reading bigint[] := ARRAY[(a->>'revision')::bigint,
                              coalesce((a->>'mapping_version')::bigint, 1)];
    bronze_of jsonb := CASE WHEN occurrence IS NULL THEN NULL ELSE jsonb_build_object(
        'object', occurrence->>'object', 'sha256', occurrence->>'sha256',
        'locator', occurrence->>'locator') END;
BEGIN
    SELECT * INTO current_row FROM mdm_v2.stage_record
      WHERE source_code = a->>'source_code' AND record_key = a->>'record_key'
      FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO mdm_v2.stage_record VALUES (
            a->>'source_code', a->>'record_key', a->>'subject', a->>'kind',
            reading[1], reading[2], a->>'publication_key', a->>'assertion_id',
            (a->>'effective_at')::timestamptz, mdm_v2.stage_fold(NULL, a), bronze_of,
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
        RETURN;  -- an older reading delivered later keeps the current row
    END IF;
    UPDATE mdm_v2.stage_record SET
        subject = a->>'subject', kind = a->>'kind',
        revision = reading[1], mapping_version = reading[2],
        publication_key = a->>'publication_key', assertion_id = a->>'assertion_id',
        effective_at = (a->>'effective_at')::timestamptz,
        snapshot = mdm_v2.stage_fold(current_row.snapshot, a),
        bronze = bronze_of, batch_id = source_batch
      WHERE source_code = current_row.source_code AND record_key = current_row.record_key;
END;
$$;

-- Backfill: each batch by generation, and within it in (revision, mapping
-- version) order, exactly as the evidence wrapper below keeps a live batch.
DO $$
DECLARE a record;
BEGIN
    FOR a IN
        SELECT s.body, s.batch_id
        FROM mdm_v2.assertion s JOIN mdm_v2.batch b USING (batch_id)
        ORDER BY b.generation, s.source_code, s.record_key, s.revision,
                 s.mapping_version, s.publication_key, s.assertion_id
    LOOP
        PERFORM mdm_v2.record_stage(a.body, a.batch_id, NULL);
    END LOOP;
    IF (SELECT count(*) FROM mdm_v2.stage_record)
       IS DISTINCT FROM (SELECT count(DISTINCT (source_code, record_key)) FROM mdm_v2.assertion) THEN
        RAISE EXCEPTION 'Stage backfill missed a stored source record';
    END IF;
END;
$$;

-- The evidence wrapper keeps the Stage once the core has stored the batch:
-- the readings this batch newly stored, in (revision, mapping version) order,
-- each with the bronze object the batch names for it. A redelivered batch
-- stores nothing and changes nothing. Exact-fragment guard, as 029, 031 and
-- 032 use; the next edit at this point must match this longer text.
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
        IF EXISTS (
            SELECT 1 FROM jsonb_array_elements(coalesce(r->'occurrences','[]')) o
            WHERE jsonb_typeof(o) IS DISTINCT FROM 'object'
               OR (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(o) k)
                  IS DISTINCT FROM ARRAY['assertion_id','locator','object','sha256']
               OR nullif(o->>'object','') IS NULL OR nullif(o->>'locator','') IS NULL
               OR coalesce(o->>'sha256','') !~ '^[0-9a-f]{64}$')
           OR EXISTS (
            SELECT o->>'assertion_id' FROM jsonb_array_elements(coalesce(r->'occurrences','[]')) o
            EXCEPT
            SELECT x->>'assertion_id' FROM jsonb_array_elements(coalesce(r->'assertions','[]')) x)
           OR (SELECT count(*) FROM jsonb_array_elements(coalesce(r->'occurrences','[]')))
              IS DISTINCT FROM (SELECT count(DISTINCT o->>'assertion_id')
                                FROM jsonb_array_elements(coalesce(r->'occurrences','[]')) o) THEN
            RAISE EXCEPTION 'Invalid bronze occurrence';
        END IF;
        -- item is [the stored reading, its occurrence or null]. Readings are
        -- found by id from the batch, never by scanning the assertion table.
        FOR item IN
            WITH named AS (
                SELECT coalesce(jsonb_object_agg(o->>'assertion_id', o), '{}'::jsonb) AS by_id
                FROM jsonb_array_elements(coalesce(r->'occurrences','[]')) o)
            SELECT jsonb_build_array(s.body, named.by_id->s.assertion_id)
            FROM jsonb_array_elements(coalesce(r->'assertions','[]')) x
            JOIN mdm_v2.assertion s
              ON s.assertion_id = x->>'assertion_id' AND s.batch_id = r->>'batch_id'
            CROSS JOIN named
            ORDER BY s.source_code, s.record_key, s.revision, s.mapping_version,
                     s.publication_key, s.assertion_id
        LOOP
            PERFORM mdm_v2.record_stage(item->0, r->>'batch_id',
                CASE WHEN jsonb_typeof(item->1) = 'object' THEN item->1 END);
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
