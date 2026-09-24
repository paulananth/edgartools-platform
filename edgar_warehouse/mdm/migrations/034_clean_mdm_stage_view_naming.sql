-- Rename the per-kind evidence views to the Stage vocabulary.
--
-- 033 named these <kind>_evidence. The operator's word for this shelf is
-- "stage", and it is the better one: the shelf holds the authoritative picture
-- of an entity per source, one row per source record per field, which is what
-- the legacy design called mdm_entity_attribute_stage and what the wider
-- practice calls a staging table. The master views keep their own names.
--
--   <kind>_evidence        ->  <kind>_stage
--   <kind>_evidence_field  ->  <kind>_stage_field
--
-- Note for anyone reading 033: its generator still spells these `_evidence`
-- and cannot be corrected, because an applied migration is checksummed and a
-- changed file is refused outright (store.py:114). Every migration in this
-- directory has exactly one commit; they are append-only by convention as well
-- as by that check. **This file is the current truth for these two names.**
--
-- The kinds are read from mdm_v2.identity's own constraint rather than listed
-- again. 033 already refuses to install unless its array equals that
-- constraint, so deriving here is exact, and it is one fewer copy of a list
-- that already lives in two places it cannot be removed from.
DO $$
DECLARE
    k text;
    expected int;
    renamed int := 0;
BEGIN
    SELECT count(*) INTO expected
    FROM pg_constraint c,
    LATERAL regexp_matches(
        substring(pg_get_constraintdef(c.oid)
                  from 'kind[^=]*= ANY \(ARRAY\[(.*?)\]\)'),
        '''([a-z_]+)''', 'g') m
    WHERE c.conrelid = 'mdm_v2.identity'::regclass
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%kind%';
    IF expected = 0 THEN
        RAISE EXCEPTION 'Cannot read the permitted kinds out of mdm_v2.identity';
    END IF;

    FOR k IN
        SELECT m[1]
        FROM pg_constraint c,
        LATERAL regexp_matches(
            substring(pg_get_constraintdef(c.oid)
                      from 'kind[^=]*= ANY \(ARRAY\[(.*?)\]\)'),
            '''([a-z_]+)''', 'g') m
        WHERE c.conrelid = 'mdm_v2.identity'::regclass
          AND c.contype = 'c'
          AND pg_get_constraintdef(c.oid) LIKE '%kind%'
    LOOP
        EXECUTE format('ALTER VIEW mdm_v2.%I RENAME TO %I',
                       k || '_evidence', k || '_stage');
        EXECUTE format('ALTER VIEW mdm_v2.%I RENAME TO %I',
                       k || '_evidence_field', k || '_stage_field');
        renamed := renamed + 1;
    END LOOP;

    -- ALTER VIEW raises on a missing source, so this catches the other
    -- direction: a kind the constraint permits whose views 033 never made.
    IF renamed <> expected THEN
        RAISE EXCEPTION
            'Renamed % kinds'' views but mdm_v2.identity permits %',
            renamed, expected;
    END IF;
END;
$$;
