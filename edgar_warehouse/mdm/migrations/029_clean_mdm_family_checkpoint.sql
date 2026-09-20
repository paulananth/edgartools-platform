-- Preserve historical unscoped cursors; never infer a family from consumer text.
ALTER TABLE mdm_v2.checkpoint
    ADD COLUMN source_family text NOT NULL DEFAULT '',
    ADD COLUMN publication_family text NOT NULL DEFAULT '',
    ADD COLUMN committed_publication text,
    ADD COLUMN continuity_proof jsonb,
    DROP CONSTRAINT checkpoint_pkey,
    ADD PRIMARY KEY(consumer,source_family,publication_family),
    ADD CONSTRAINT checkpoint_scope CHECK (
        (source_family='' AND publication_family='' AND committed_publication IS NULL AND continuity_proof IS NULL)
        OR (btrim(source_family)<>'' AND btrim(publication_family)<>'' AND nullif(btrim(committed_publication),'') IS NOT NULL
            AND continuity_proof IS NOT NULL AND jsonb_typeof(continuity_proof)='object' AND continuity_proof<>'{}'::jsonb)
    );

-- Amend only the checkpoint read/write statements of the installed capability.
-- Exact-fragment guards fail the migration if that implementation has drifted.
-- Keep every evidence/decision/publication check and its historical checksum.
DO $$
DECLARE definition text; old_fragment text; new_fragment text;
BEGIN
    SELECT pg_get_functiondef('mdm_v2.commit_batch_core(text,uuid)'::regprocedure) INTO definition;
    old_fragment := $old$PERFORM pg_advisory_xact_lock(730234);$old$;
    new_fragment := $new$IF coalesce(r->>'source_family','')<>'' AND NOT EXISTS(
        SELECT 1 FROM mdm_v2.dataset WHERE body->>'family'=r->>'source_family'
          AND body->'publication_families' ? (r->>'publication_family')) THEN
        RAISE EXCEPTION 'Unknown publication family contract';
    END IF;
    PERFORM pg_advisory_xact_lock(730234);$new$;
    IF position(old_fragment IN definition)=0 THEN RAISE EXCEPTION 'Unexpected core checkpoint lock'; END IF;
    definition := replace(definition,old_fragment,new_fragment);
    old_fragment := $old$WHERE consumer=r->>'consumer'),0) INTO pos;$old$;
    new_fragment := $new$WHERE consumer=r->>'consumer'
        AND source_family=coalesce(r->>'source_family','')
        AND publication_family=coalesce(r->>'publication_family','')),0) INTO pos;$new$;
    IF position(old_fragment IN definition)=0 THEN RAISE EXCEPTION 'Unexpected core checkpoint read'; END IF;
    definition := replace(definition,old_fragment,new_fragment);
    old_fragment := $old$INSERT INTO mdm_v2.checkpoint VALUES(r->>'consumer',(r->>'checkpoint')::bigint,r->>'batch_id')
    ON CONFLICT(consumer) DO UPDATE SET position=excluded.position,batch_id=excluded.batch_id;$old$;
    new_fragment := $new$INSERT INTO mdm_v2.checkpoint(consumer,position,batch_id,source_family,publication_family,committed_publication,continuity_proof)
    VALUES(r->>'consumer',(r->>'checkpoint')::bigint,r->>'batch_id',coalesce(r->>'source_family',''),
        coalesce(r->>'publication_family',''),r->>'committed_publication',r->'continuity_proof')
    ON CONFLICT(consumer,source_family,publication_family) DO UPDATE SET position=excluded.position,
        batch_id=excluded.batch_id,committed_publication=excluded.committed_publication,continuity_proof=excluded.continuity_proof;$new$;
    IF position(old_fragment IN definition)=0 THEN RAISE EXCEPTION 'Unexpected core checkpoint write'; END IF;
    definition := replace(definition,old_fragment,new_fragment);
    EXECUTE definition;

    SELECT pg_get_functiondef('mdm_v2.assessment_snapshot(jsonb)'::regprocedure) INTO definition;
    old_fragment := $old$WHERE consumer=scope->>'consumer'),0)$old$;
    new_fragment := $new$WHERE consumer=scope->>'consumer'
            AND source_family=coalesce(scope->>'source_family','')
            AND publication_family=coalesce(scope->>'publication_family','')),0)$new$;
    IF position(old_fragment IN definition)=0 THEN RAISE EXCEPTION 'Unexpected assessment checkpoint read'; END IF;
    EXECUTE replace(definition,old_fragment,new_fragment);
END;
$$;
