-- Cross-reference identifiers (profiling ticket 03; operator, 2026-09-26: "cross
-- reference id for lookup any document only with ids", lookup only).
--
-- A Dataset Contract names them in `cross_references`, apart from
-- `identifiers`. They ride in each assertion, so the winning reading of every
-- source record in `stage_record` holds them, and no second write path has to
-- be kept in step. Matching and binding read `identifiers` only: a
-- cross-reference never joins records. Registration refuses a cross-reference
-- namespace that is also an identifier, or one a binding rule matches on.
--
-- Migrations run in one transaction, so the index is built without
-- CONCURRENTLY: it blocks writes to stage_record (not reads) while it builds.

CREATE INDEX stage_record_cross_references ON mdm.stage_record
    USING gin ((reading -> 'cross_references') jsonb_path_ops);

CREATE VIEW mdm.cross_reference AS
 SELECT x.key AS namespace,
    x.value,
    s.source_code,
    s.record_key,
    s.kind,
    (s.entity_id)::text AS bound_entity_id,
    coalesce(e.canonical_id, (s.entity_id)::text) AS entity_id,
    s.assertion_id,
    s.batch_id
   FROM mdm.stage_record s
     CROSS JOIN LATERAL jsonb_each_text(s.reading -> 'cross_references') x(key, value)
     LEFT JOIN mdm.current_entity e ON e.object_id = (s.entity_id)::text AND e.canonical_id IS NOT NULL;

COMMENT ON VIEW mdm.cross_reference IS
    'Every cross-reference id a source record carries: an id kept so any document can be looked up by it, never used to join records. One row per id of each record, read from the record''s current reading. To look one id up, use mdm.cross_reference_lookup, which uses an index.';
COMMENT ON COLUMN mdm.cross_reference.namespace IS 'What kind of id it is, as the Dataset Contract names it (for example a tax number).';
COMMENT ON COLUMN mdm.cross_reference.value IS 'The id, formatted as the contract says.';
COMMENT ON COLUMN mdm.cross_reference.source_code IS 'The Dataset Contract of the record that carries the id.';
COMMENT ON COLUMN mdm.cross_reference.record_key IS 'The record''s key in that source.';
COMMENT ON COLUMN mdm.cross_reference.kind IS 'The kind of master entity the record describes.';
COMMENT ON COLUMN mdm.cross_reference.bound_entity_id IS 'The master entity the record is bound to; empty while the record waits for binding.';
COMMENT ON COLUMN mdm.cross_reference.entity_id IS 'The master entity to read now: the bound entity, or the entity it was merged into.';
COMMENT ON COLUMN mdm.cross_reference.assertion_id IS 'The reading the id comes from.';
COMMENT ON COLUMN mdm.cross_reference.batch_id IS 'The batch that wrote that reading.';

-- The lookup: the index finds the records, the view says what each one is.
CREATE FUNCTION mdm.cross_reference_lookup(namespace text, value text)
    RETURNS SETOF mdm.cross_reference
    LANGUAGE sql STABLE PARALLEL SAFE
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
    SELECT v.* FROM mdm.cross_reference v
     WHERE (v.source_code, v.record_key) IN (
            SELECT s.source_code, s.record_key FROM mdm.stage_record s
             WHERE s.reading -> 'cross_references' @> jsonb_build_object(namespace, value))
       AND v.namespace = cross_reference_lookup.namespace
       AND v.value = cross_reference_lookup.value
     ORDER BY v.source_code, v.record_key
$$;

COMMENT ON FUNCTION mdm.cross_reference_lookup(text, text) IS
    'The source records, and their master entities, that carry one cross-reference id. Lookup only: two records sharing an id are not the same entity because of it.';
