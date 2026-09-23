-- A deferred record and an assertion from one read must agree.
--
-- Migration 031 moved the assertion's schema check onto the reading that
-- produced it. The deferred check still read mdm_v2.dataset, which migration
-- 023 makes append-only, so it stayed at the first registration: under a
-- corrected mapping the assertions of a read were accepted and the deferred
-- records of the same read were refused.
--
-- A deferred record states no reading, and does not gain one here. Its natural
-- key is (source_code, publication_key, record_locator) (migration 027), which
-- a re-read reuses, so a second body carrying a reading would collide with the
-- first under the read-back comparison below rather than sit beside it. It is
-- evidence that a record could not be interpreted; the schema it was read
-- under is what identifies its contract. So the check accepts the schema of
-- any registered reading of that source.
DO $$
DECLARE definition text; old_fragment text; new_fragment text;
BEGIN
    SELECT pg_get_functiondef('mdm_v2.commit_batch_evidence(text,uuid)'::regprocedure) INTO definition;
    -- The SELECT INTO src above this fragment stays: the blocking disposition
    -- further down still reads that row's nonblocking_deferred_reasons.
    old_fragment := $old$        IF NOT FOUND OR src.body->>'schema_version' IS DISTINCT FROM item->>'schema_version' THEN
            RAISE EXCEPTION 'Unknown deferred dataset contract';
        END IF;$old$;
    new_fragment := $new$        IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM mdm_v2.dataset_mapping m
            WHERE m.source_code=item->>'source_code'
              AND m.body->>'schema_version' IS NOT DISTINCT FROM item->>'schema_version') THEN
            RAISE EXCEPTION 'Unknown deferred dataset contract';
        END IF;$new$;
    IF position(old_fragment IN definition)=0 THEN RAISE EXCEPTION 'Unexpected deferred schema check'; END IF;
    EXECUTE replace(definition,old_fragment,new_fragment);
END;
$$;
