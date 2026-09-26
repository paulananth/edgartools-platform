-- Who each Stage record is bound to, and its winning reading whole (company
-- mastering ticket 10, slice 2a).
--
-- entity_id is the Company (or other identity) the record's bind decision
-- names: that entity itself, never its survivor. A binding never moves
-- (identity.replay refuses it), so this is set once, when the bind commits,
-- and a bind naming another entity is refused. Readers still resolve a
-- merged-away entity to its survivor. It is empty while the record waits.
--
-- reading is the winning reading's full body. The matching rules read parts
-- of it the snapshot does not keep (its provenance), and slice 4 stops
-- storing it anywhere else. It changes exactly when the winner changes.
--
-- The readers of who holds an identifier, and of which records are bound,
-- move here from the full history. A record's latest reading is its highest
-- (revision, mapping version) in both places, so they read the same.
ALTER TABLE mdm_v2.stage_record
    ADD COLUMN reading jsonb,
    ADD COLUMN entity_id uuid REFERENCES mdm_v2.identity(entity_id);

UPDATE mdm_v2.stage_record s SET reading = a.body
FROM mdm_v2.assertion a WHERE a.assertion_id = s.assertion_id;

ALTER TABLE mdm_v2.stage_record
    ALTER COLUMN reading SET NOT NULL,
    ADD CONSTRAINT stage_record_reading_is_winner
        CHECK (reading->>'assertion_id' = assertion_id);

-- The lookups the readers run: who holds a CIK or an LEI, the Name Census's
-- LEI for a GLEIF record, and the records bound to one entity.
CREATE INDEX stage_record_cik ON mdm_v2.stage_record ((reading->'identifiers'->>'cik'));
CREATE INDEX stage_record_lei ON mdm_v2.stage_record ((reading->'identifiers'->>'lei'));
CREATE INDEX stage_record_census_lei ON mdm_v2.stage_record
    ((reading->'provenance'->'matching'->'name_census'->'leis'->0->>0));
CREATE INDEX stage_record_entity ON mdm_v2.stage_record (entity_id)
    WHERE entity_id IS NOT NULL;

-- 038's function, now also keeping the winner whole. Its local rank was
-- named `reading`; it is renamed so it cannot be read as the new column.
CREATE OR REPLACE FUNCTION mdm_v2.record_stage(a jsonb, source_batch text, occurrence jsonb)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE
    current_row mdm_v2.stage_record%ROWTYPE;
    ordering bigint[] := ARRAY[(a->>'revision')::bigint,
                               coalesce((a->>'mapping_version')::bigint, 1)];
    bronze_of jsonb := CASE WHEN occurrence IS NULL THEN NULL ELSE jsonb_build_object(
        'object', occurrence->>'object', 'sha256', occurrence->>'sha256',
        'locator', occurrence->>'locator') END;
BEGIN
    SELECT * INTO current_row FROM mdm_v2.stage_record
      WHERE source_code = a->>'source_code' AND record_key = a->>'record_key'
      FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO mdm_v2.stage_record (
            source_code, record_key, subject, kind, revision, mapping_version,
            publication_key, assertion_id, effective_at, snapshot, bronze,
            batch_id, reading
        ) VALUES (
            a->>'source_code', a->>'record_key', a->>'subject', a->>'kind',
            ordering[1], ordering[2], a->>'publication_key', a->>'assertion_id',
            (a->>'effective_at')::timestamptz, mdm_v2.stage_fold(NULL, a), bronze_of,
            source_batch, a);
        RETURN;
    END IF;
    IF ordering = ARRAY[current_row.revision, current_row.mapping_version] THEN
        IF current_row.assertion_id IS DISTINCT FROM a->>'assertion_id' THEN
            RAISE EXCEPTION 'Source native revision has contradictory publications';
        END IF;
        RETURN;
    END IF;
    IF ordering < ARRAY[current_row.revision, current_row.mapping_version] THEN
        RETURN;  -- an older reading delivered later keeps the current row
    END IF;
    UPDATE mdm_v2.stage_record SET
        subject = a->>'subject', kind = a->>'kind',
        revision = ordering[1], mapping_version = ordering[2],
        publication_key = a->>'publication_key', assertion_id = a->>'assertion_id',
        effective_at = (a->>'effective_at')::timestamptz,
        snapshot = mdm_v2.stage_fold(current_row.snapshot, a),
        bronze = bronze_of, batch_id = source_batch, reading = a
      WHERE source_code = current_row.source_code AND record_key = current_row.record_key;
END;
$$;

-- Keep one committed bind decision on its record's Stage row.
CREATE FUNCTION mdm_v2.record_binding(d jsonb)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,mdm_v2 AS $$
DECLARE
    bound uuid;
BEGIN
    SELECT entity_id INTO bound FROM mdm_v2.stage_record
      WHERE subject = d->>'subject' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'A binding names no Stage record';
    END IF;
    IF bound IS NOT NULL AND bound <> (d->>'entity_id')::uuid THEN
        RAISE EXCEPTION 'Moving an established source binding requires a correction contract';
    END IF;
    UPDATE mdm_v2.stage_record SET entity_id = (d->>'entity_id')::uuid
      WHERE subject = d->>'subject';
END;
$$;

-- Backfill from every committed bind, in commit order, as a live batch keeps it.
DO $$
DECLARE d record;
BEGIN
    FOR d IN
        SELECT x.body FROM mdm_v2.decision x JOIN mdm_v2.batch b USING (batch_id)
        WHERE x.operation = 'bind'
        ORDER BY b.generation, x.decision_id
    LOOP
        PERFORM mdm_v2.record_binding(d.body);
    END LOOP;
    IF (SELECT count(*) FROM mdm_v2.stage_record WHERE entity_id IS NOT NULL)
       IS DISTINCT FROM (SELECT count(DISTINCT body->>'subject') FROM mdm_v2.decision
                         WHERE operation = 'bind') THEN
        RAISE EXCEPTION 'Stage binding backfill missed a bound record';
    END IF;
END;
$$;

-- The evidence wrapper keeps each bind this batch commits, after the batch's
-- readings are on the Stage, so a bind citing a reading of this batch finds
-- its row. Exact-fragment guard on 038's text; the next edit at this point
-- must match this longer text.
DO $$
DECLARE definition text; old_fragment text; new_fragment text;
BEGIN
    SELECT pg_get_functiondef('mdm_v2.commit_batch_evidence(text,uuid)'::regprocedure) INTO definition;
    old_fragment := $old$            PERFORM mdm_v2.record_stage(item->0, r->>'batch_id',
                CASE WHEN jsonb_typeof(item->1) = 'object' THEN item->1 END);
        END LOOP;
    END IF;
    RETURN result;$old$;
    new_fragment := $new$            PERFORM mdm_v2.record_stage(item->0, r->>'batch_id',
                CASE WHEN jsonb_typeof(item->1) = 'object' THEN item->1 END);
        END LOOP;
        FOR item IN
            SELECT value FROM jsonb_array_elements(coalesce(r->'decisions','[]'))
            WHERE value->>'operation' = 'bind'
            ORDER BY value->>'at', value->>'decision_id'
        LOOP
            PERFORM mdm_v2.record_binding(item);
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
