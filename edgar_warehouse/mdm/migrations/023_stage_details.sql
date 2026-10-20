-- A Stage record's snapshot carries the reading's detail lists (ticket 120), as it
-- carries its identifiers: the latest reading's, and absent when the reading has
-- none, as on the assertion and in survivorship.current_claims. Otherwise as in 001.
-- No Stage record before 022 carries details, so there is nothing to back-fill.

CREATE OR REPLACE FUNCTION mdm.stage_fold(previous jsonb, a jsonb) RETURNS jsonb
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
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
            claims := claims || jsonb_build_object(field.name, mdm.stage_claim(field.item, a));
        END IF;
    END LOOP;
    FOR profile IN SELECT value FROM jsonb_array_elements(coalesce(a->'profiles', '[]'::jsonb)) LOOP
        profile_id := mdm.stage_profile_key(profile);
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
                values_of := values_of || jsonb_build_object(field.name, mdm.stage_claim(item, a));
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
            'effective_at', a->'effective_at'))
        || CASE WHEN a ? 'details' THEN jsonb_build_object('details', a->'details') ELSE '{}'::jsonb END;
END;
$$;


COMMENT ON FUNCTION mdm.detail_rows(jsonb) IS
    'A master body''s detail rows, one per list and key: the list''s name, the row''s key and the row.';
