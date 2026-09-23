-- Per-kind read views. Shape only: no new storage and no second authority.
--
-- Evidence and master records stay in one table each, with the kind as a value
-- inside them. These views present that one table as if it were split per kind,
-- so a reader asks for Company evidence without repeating the filter and
-- without a second copy of the data to keep in step.
--
-- Two shapes per base, because they answer different questions:
--   <kind>_evidence        one row per source record, the whole claim
--   <kind>_evidence_field  one row per (source record, field) -- the stage shape
--   <kind>_master          one row per entity, the master record
--   <kind>_master_field    one row per (entity, field), with the source that won
--
-- Adding a field to a policy costs nothing here: a field is a key inside the
-- jsonb body, so it arrives as a new row in the exploded shapes and a new key
-- in the whole-record shapes. Only a new *kind* costs anything, and the loop
-- below is what keeps that to one word.
--
-- The columns are listed rather than SELECT *, because a view freezes its
-- column list at creation: SELECT * would silently keep showing the old set
-- after a structural column is added to the base table. Listing them means a
-- future structural column is a deliberate edit here, and
-- tests/integration/test_clean_per_kind_views.py fails loudly until it is made.
DO $$
DECLARE
    -- The kinds these views cover. Checked against mdm_v2.identity's own
    -- constraint below rather than trusted, so the two cannot drift apart.
    kinds text[] := ARRAY[
        'company','person','security','fund_structure',
        'branch','government','international_organization','venue'
    ];
    declared text;
    permitted text[];
    k text;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO declared
    FROM pg_constraint
    WHERE conrelid = 'mdm_v2.identity'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%kind%';
    IF declared IS NULL THEN
        RAISE EXCEPTION 'No entity kind constraint on mdm_v2.identity to check against';
    END IF;
    SELECT array_agg(m[1] ORDER BY m[1]) INTO permitted
    FROM regexp_matches(declared, '''([a-z_]+)''', 'g') AS m;
    IF permitted IS DISTINCT FROM (SELECT array_agg(x ORDER BY x) FROM unnest(kinds) x) THEN
        RAISE EXCEPTION
            'Per-kind views name % but mdm_v2.identity permits %', kinds, permitted;
    END IF;

    FOREACH k IN ARRAY kinds LOOP
        -- Every source statement about this kind, whole.
        EXECUTE format($v$
            CREATE VIEW mdm_v2.%I AS
            SELECT a.assertion_id, a.source_code, a.record_key, a.publication_key,
                   a.revision, a.mapping_version, a.effective_at, a.batch_id,
                   a.body->>'subject' AS subject,
                   a.body->>'schema_version' AS schema_version,
                   a.body
            FROM mdm_v2.assertion a
            WHERE a.body->>'kind' = %L
        $v$, k || '_evidence', k);

        -- The stage shape: one row per source record per field.
        EXECUTE format($v$
            CREATE VIEW mdm_v2.%I AS
            SELECT a.assertion_id, a.source_code, a.record_key, a.publication_key,
                   a.revision, a.mapping_version, a.effective_at, a.batch_id,
                   a.body->>'subject' AS subject,
                   f.key AS field_name,
                   f.value->>'op' AS operation,
                   f.value->>'value' AS field_value
            FROM mdm_v2.assertion a
            CROSS JOIN LATERAL jsonb_each(COALESCE(a.body->'fields','{}'::jsonb)) f
            WHERE a.body->>'kind' = %L
        $v$, k || '_evidence_field', k);

        -- The master record for each entity of this kind.
        EXECUTE format($v$
            CREATE VIEW mdm_v2.%I AS
            SELECT p.object_id AS entity_id, p.batch_id,
                   p.body->>'status' AS status,
                   p.body->>'canonical_id' AS canonical_id,
                   p.body
            FROM mdm_v2.projection p
            WHERE p.object_type = 'entity' AND p.body->>'kind' = %L
        $v$, k || '_master', k);

        -- One row per mastered field, naming the source record that won it.
        EXECUTE format($v$
            CREATE VIEW mdm_v2.%I AS
            SELECT p.object_id AS entity_id, p.batch_id,
                   p.body->>'status' AS status,
                   f.key AS field_name,
                   f.value->>'value' AS field_value,
                   (f.value->>'cleared')::boolean AS cleared,
                   f.value->'winner'->>'source_code' AS source_code,
                   f.value->'winner'->>'record_key' AS record_key,
                   f.value->'winner'->>'effective_at' AS effective_at,
                   f.value->>'policy_digest' AS policy_digest,
                   jsonb_array_length(COALESCE(f.value->'conflicts','[]'::jsonb))
                       AS conflict_count
            FROM mdm_v2.projection p
            CROSS JOIN LATERAL jsonb_each(COALESCE(p.body->'fields','{}'::jsonb)) f
            WHERE p.object_type = 'entity' AND p.body->>'kind' = %L
        $v$, k || '_master_field', k);
    END LOOP;
END;
$$;

-- Without these every per-kind view is a sequential scan of the whole table.
-- 025 indexed the subject for closure queries; the kind was not read until now.
CREATE INDEX clean_assertion_kind ON mdm_v2.assertion ((body->>'kind'));
CREATE INDEX clean_projection_entity_kind ON mdm_v2.projection ((body->>'kind'))
    WHERE object_type = 'entity';

-- A view over one table with no set-returning function is auto-updatable in
-- PostgreSQL, so the whole-record shapes would accept an INSERT that bypassed
-- commit_batch if the privileges ever allowed it. store.migrate() revokes and
-- re-grants SELECT across the whole schema after every migration, and
-- ALL TABLES covers views, so the application role gets no write here. This
-- repeats the revoke for any role that reaches the schema another way, and
-- test_clean_per_kind_views.py proves the write is refused rather than trusting
-- either statement.
REVOKE ALL ON ALL TABLES IN SCHEMA mdm_v2 FROM PUBLIC;
