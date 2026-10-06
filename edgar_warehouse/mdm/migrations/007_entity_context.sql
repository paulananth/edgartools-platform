-- Entity context for agents (profiling ticket 05; agent-context spec §2): every
-- live master entity of any kind, named, with its surviving values and the
-- source that won each, its identifiers, its cross-reference ids (lookup only,
-- kept apart) and the source records it is built from; a name search; and an
-- index that finds the records carrying any identifier.
--
-- This file names no kind. Migrations run in one transaction, so the indexes
-- are built without CONCURRENTLY: each blocks writes to its table (not reads)
-- while it builds.

CREATE VIEW mdm.entity_context AS
 WITH live AS (
    SELECT p.object_id, p.body, p.batch_id, b.created_at AS valid_from
      FROM mdm.current_record p
      JOIN mdm.batch b ON b.batch_id = p.batch_id
     WHERE p.object_type = 'entity'
       AND p.body ->> 'kind' <> 'company'
       AND p.body ->> 'canonical_id' = p.object_id
       AND coalesce(p.body ->> 'status', '') <> 'alias'
    UNION ALL
    SELECT c.entity_id::text, c.body, c.batch_id, c.valid_from
      FROM mdm.company c
     WHERE c.valid_to IS NULL
)
 SELECT l.object_id AS entity_id,
    l.body ->> 'kind' AS kind,
    mdm.entity_name(l.body) AS name,
    l.body ->> 'status' AS status,
    l.body ->> 'canonical_id' AS canonical_id,
    coalesce(l.body -> 'identifiers', '{}'::jsonb) AS identifiers,
    (SELECT coalesce(jsonb_object_agg(x.namespace, x.ids), '{}'::jsonb)
       FROM (SELECT r.key AS namespace, jsonb_agg(DISTINCT r.value ORDER BY r.value) AS ids
               FROM mdm.stage_record s
               CROSS JOIN LATERAL jsonb_each_text(coalesce(s.reading -> 'cross_references', '{}'::jsonb)) r(key, value)
              WHERE s.subject IN (SELECT jsonb_array_elements_text(coalesce(l.body -> 'subjects', '[]'::jsonb)))
              GROUP BY r.key) x) AS cross_references,
    (SELECT coalesce(jsonb_object_agg(f.key, jsonb_build_object(
                'value', f.value -> 'value',
                'source_code', f.value -> 'winner' ->> 'source_code',
                'record_key', f.value -> 'winner' ->> 'record_key')), '{}'::jsonb)
       FROM jsonb_each(coalesce(l.body -> 'fields', '{}'::jsonb)) f(key, value)
      WHERE NOT coalesce((f.value ->> 'cleared')::boolean, false)) AS fields,
    (SELECT coalesce(jsonb_object_agg(z.source_code, z.record_keys), '{}'::jsonb)
       FROM (SELECT s.source_code, jsonb_agg(s.record_key ORDER BY s.record_key) AS record_keys
               FROM mdm.stage_record s
              WHERE s.subject IN (SELECT jsonb_array_elements_text(coalesce(l.body -> 'subjects', '[]'::jsonb)))
              GROUP BY s.source_code) z) AS sources,
    l.valid_from,
    NULL::timestamp with time zone AS valid_to,
    l.batch_id,
    m.published_at
   FROM live l
     LEFT JOIN mdm.master_entity m ON m.entity_id::text = l.object_id;

COMMENT ON VIEW mdm.entity_context IS
    'Every live master entity of any kind, named, with its surviving values and the source that won each, its identifiers, its cross-reference ids and the source records it is built from. An entity merged into another is left out: read the one it was merged into. What each kind means is in rules/context/definitions.yaml; an older version is read with edgar-warehouse context --as-at or --as-of.';
COMMENT ON COLUMN mdm.entity_context.entity_id IS 'The master entity.';
COMMENT ON COLUMN mdm.entity_context.kind IS 'What kind of entity it is (as the Mastering Policy names kinds).';
COMMENT ON COLUMN mdm.entity_context.name IS 'The name it is known by: the first filled of its name, its legal name (a person) and its display name; empty when it has none yet.';
COMMENT ON COLUMN mdm.entity_context.status IS 'accepted, or review while a steward must decide something about it.';
COMMENT ON COLUMN mdm.entity_context.canonical_id IS 'The entity itself: merged entities are left out, so this always equals entity_id.';
COMMENT ON COLUMN mdm.entity_context.identifiers IS 'Its identifiers, each namespace with its values: the ids that decide which records are this entity.';
COMMENT ON COLUMN mdm.entity_context.cross_references IS 'Other ids its source records carry, each namespace with its values. Lookup only: two entities sharing one are not the same entity because of it.';
COMMENT ON COLUMN mdm.entity_context.fields IS 'Its surviving values: each field with its value and the source code and record key that won it. A cleared field is left out.';
COMMENT ON COLUMN mdm.entity_context.sources IS 'The source records it is built from: each source code with its record keys.';
COMMENT ON COLUMN mdm.entity_context.valid_from IS 'When this version of the entity was recorded.';
COMMENT ON COLUMN mdm.entity_context.valid_to IS 'Always empty here: the view holds current versions only.';
COMMENT ON COLUMN mdm.entity_context.batch_id IS 'The batch that wrote this version.';
COMMENT ON COLUMN mdm.entity_context.published_at IS 'When the entity was first published.';

-- Finds the records carrying any identifier, of any namespace.
CREATE INDEX stage_record_identifiers ON mdm.stage_record
    USING gin ((reading -> 'identifiers') jsonb_path_ops);

COMMENT ON INDEX mdm.stage_record_identifiers IS
    'Finds the source records that carry one identifier of any namespace, for edgar-warehouse context <kind> <namespace>:<value>.';

-- Name search: one index on the entity rows, one on the company table, each on
-- the same expression the search uses.
CREATE INDEX current_record_entity_name_search ON mdm.current_record
    USING gin (to_tsvector('simple'::regconfig, coalesce(mdm.entity_name(body), '')))
    WHERE object_type = 'entity';

COMMENT ON INDEX mdm.current_record_entity_name_search IS 'Word search on master entity names, for mdm.entity_search.';

CREATE INDEX company_name_search ON mdm.company
    USING gin (to_tsvector('simple'::regconfig, coalesce(mdm.entity_name(body), '')))
    WHERE valid_to IS NULL;

COMMENT ON INDEX mdm.company_name_search IS 'Word search on current company names, for mdm.entity_search.';

-- The live entities whose name matches some words: word search first, ranked;
-- when it finds nothing, names that contain the words as typed.
CREATE FUNCTION mdm.entity_search(words text, entity_kind text, max_rows integer)
    RETURNS TABLE(entity_id text, kind text, name text, status text, matched_by text, rank real)
    LANGUAGE plpgsql STABLE STRICT PARALLEL SAFE
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
#variable_conflict use_column
DECLARE
    query tsquery := websearch_to_tsquery('simple', words);
    pattern text := '%' || replace(replace(replace(words, '\', '\\'), '%', '\%'), '_', '\_') || '%';
    found integer;
BEGIN
    RETURN QUERY
    SELECT h.object_id, h.kind, h.name, h.status, 'words'::text, h.rank FROM (
        SELECT p.object_id, p.body ->> 'kind' AS kind, mdm.entity_name(p.body) AS name, p.body ->> 'status' AS status,
               ts_rank_cd(to_tsvector('simple'::regconfig, coalesce(mdm.entity_name(p.body), '')), query) AS rank
          FROM mdm.current_record p
         WHERE p.object_type = 'entity'
           AND to_tsvector('simple'::regconfig, coalesce(mdm.entity_name(p.body), '')) @@ query
           AND p.body ->> 'kind' <> 'company' AND p.body ->> 'canonical_id' = p.object_id
           AND (entity_kind = '' OR p.body ->> 'kind' = entity_kind)
        UNION ALL
        SELECT c.entity_id::text, 'company', mdm.entity_name(c.body), c.status,
               ts_rank_cd(to_tsvector('simple'::regconfig, coalesce(mdm.entity_name(c.body), '')), query)
          FROM mdm.company c
         WHERE c.valid_to IS NULL
           AND to_tsvector('simple'::regconfig, coalesce(mdm.entity_name(c.body), '')) @@ query
           AND entity_kind IN ('', 'company')
    ) h
    ORDER BY h.rank DESC, h.name, h.object_id
    LIMIT max_rows;
    GET DIAGNOSTICS found = ROW_COUNT;
    IF found > 0 THEN
        RETURN;
    END IF;
    RETURN QUERY
    SELECT h.object_id, h.kind, h.name, h.status, 'contains'::text, 0::real FROM (
        SELECT p.object_id, p.body ->> 'kind' AS kind, mdm.entity_name(p.body) AS name, p.body ->> 'status' AS status
          FROM mdm.current_record p
         WHERE p.object_type = 'entity' AND mdm.entity_name(p.body) ILIKE pattern
           AND p.body ->> 'kind' <> 'company' AND p.body ->> 'canonical_id' = p.object_id
           AND (entity_kind = '' OR p.body ->> 'kind' = entity_kind)
        UNION ALL
        SELECT c.entity_id::text, 'company', mdm.entity_name(c.body), c.status
          FROM mdm.company c
         WHERE c.valid_to IS NULL AND mdm.entity_name(c.body) ILIKE pattern
           AND entity_kind IN ('', 'company')
    ) h
    ORDER BY h.name, h.object_id
    LIMIT max_rows;
END
$$;

COMMENT ON FUNCTION mdm.entity_search(text, text, integer) IS
    'Live master entities whose name matches some words, best first: word search (matched_by words, ranked), or, when that finds nothing, names containing the words as typed (matched_by contains). entity_kind narrows it to one kind; an empty string searches every kind.';
