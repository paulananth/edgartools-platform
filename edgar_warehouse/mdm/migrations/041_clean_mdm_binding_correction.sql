-- Correcting a wrong link (company mastering ticket 13).
--
-- A wrong SEC-to-GLEIF link is a bind, and a bind never moves: 039 refuses
-- it on the Stage as identity.replay refuses it in the journal. The
-- correction is a revocation of that bind, in the journal, naming the bind,
-- its subject and entity (identity.replay checks both). Here the Stage
-- follows: the revoked record's entity_id is cleared, in the same
-- transaction, before the batch's binds, so the record waits or binds again.
--
-- A revocation of anything but a bind leaves the Stage alone. A bind is
-- revoked once only, and one whose record no longer holds that bind is
-- refused: the correction was made on a stale view. The same revocation
-- delivered again is a duplicate batch and changes nothing.

CREATE FUNCTION mdm_v2.release_binding(d jsonb)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE
    target jsonb;
    bound uuid;
BEGIN
    SELECT body INTO target FROM mdm_v2.decision WHERE decision_id = d->>'target';
    IF target IS NULL OR target->>'operation' IS DISTINCT FROM 'bind' THEN
        RETURN;
    END IF;
    -- Once only: a second revocation would unbind whatever the record was
    -- bound to since.
    IF EXISTS (SELECT 1 FROM mdm_v2.decision WHERE operation = 'revoke'
               AND body->>'target' = d->>'target' AND decision_id <> d->>'decision_id') THEN
        RAISE EXCEPTION 'This bind is already revoked';
    END IF;
    SELECT entity_id INTO bound FROM mdm_v2.stage_record
      WHERE subject = target->>'subject' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'A revocation names no Stage record';
    END IF;
    IF bound IS NULL THEN
        RETURN;
    END IF;
    IF bound IS DISTINCT FROM (target->>'entity_id')::uuid THEN
        RAISE EXCEPTION 'A revocation names a bind its record no longer holds';
    END IF;
    UPDATE mdm_v2.stage_record SET entity_id = NULL WHERE subject = target->>'subject';
END;
$$;

-- 039's function, replaced whole as it asks: revocations, then binds.
CREATE OR REPLACE FUNCTION mdm_v2.keep_stage(r jsonb)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE
    item jsonb;
BEGIN
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(coalesce(r->'occurrences','[]')) o
        WHERE jsonb_typeof(o) IS DISTINCT FROM 'object'
           OR (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(o) k)
              IS DISTINCT FROM ARRAY['assertion_id','locator','object','sha256']
           OR EXISTS (SELECT 1 FROM unnest(ARRAY['assertion_id','locator','object','sha256']) k
                      WHERE jsonb_typeof(o->k) IS DISTINCT FROM 'string')
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
    -- Revocations first (ticket 13): a record whose bind is revoked is
    -- unbound before this batch binds it again, to the same Company or
    -- another. A bind this same batch revokes is never kept.
    FOR item IN
        SELECT value FROM jsonb_array_elements(coalesce(r->'decisions','[]'))
        WHERE value->>'operation' = 'revoke'
    LOOP
        PERFORM mdm_v2.release_binding(item);
    END LOOP;
    FOR item IN
        SELECT b.value FROM jsonb_array_elements(coalesce(r->'decisions','[]')) b
        WHERE b.value->>'operation' = 'bind'
          AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(coalesce(r->'decisions','[]')) v
            WHERE v.value->>'operation' = 'revoke' AND v.value->>'target' = b.value->>'decision_id')
    LOOP
        PERFORM mdm_v2.record_binding(item);
    END LOOP;
END;
$$;
