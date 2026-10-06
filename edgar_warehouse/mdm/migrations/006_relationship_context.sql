-- Relationship context for agents (profiling ticket 04; agent-context spec
-- §2): every mastered relationship of any type, with both ends named, one row
-- per period, and the source records that state it; and the parent chain of an
-- entity, walked with recursive SQL, a hop limit and a cycle guard.
--
-- What a relationship is comes from its type in the Mastering Policy
-- (`rules/merge/relationships.yaml`); this file names no type. Retired links
-- are left out, as `mdm.is_insider` leaves them out.

-- The name an entity is known by: the first filled of `name`, `legal_name` (a
-- person) and `display_name`.
CREATE FUNCTION mdm.entity_name(body jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    SET search_path TO 'pg_catalog'
    AS $$
    SELECT coalesce(body -> 'fields' -> 'name' ->> 'value',
                    body -> 'fields' -> 'legal_name' ->> 'value',
                    body -> 'fields' -> 'display_name' ->> 'value')
$$;

COMMENT ON FUNCTION mdm.entity_name(jsonb) IS
    'The name a master entity is known by: the first filled of its name, its legal name (a person) and its display name; empty when it has none yet.';

CREATE VIEW mdm.relationship_context AS
 SELECT r.object_id AS relationship_id,
    r.body ->> 'type' AS type,
    r.body ->> 'source_id' AS from_entity_id,
    f.kind AS from_kind,
    mdm.entity_name(f.body) AS from_name,
    r.body ->> 'target_id' AS to_entity_id,
    t.kind AS to_kind,
    mdm.entity_name(t.body) AS to_name,
    r.body ->> 'capacity' AS role,
    r.body ->> 'scope' AS scope,
    coalesce((r.body ->> 'derived')::boolean, false) AS derived,
    p.n AS period,
    (p.period ->> 'valid_from')::timestamptz AS valid_from,
    (p.period ->> 'valid_to')::timestamptz AS valid_to,
    p.period ->> 'valid_from_basis' AS valid_from_basis,
    p.period ->> 'valid_to_basis' AS valid_to_basis,
    (r.body ->> 'last_seen')::timestamptz AS last_seen,
    (SELECT coalesce(jsonb_agg(DISTINCT jsonb_build_object('source_code', s.source_code, 'record_key', s.record_key)),
                     '[]'::jsonb)
       FROM jsonb_array_elements(coalesce(r.body -> 'evidence', '[]'::jsonb)) ev(item)
       JOIN mdm.source_reading s ON s.assertion_id = ev.item ->> 'assertion_id') AS sources,
    r.batch_id
   FROM mdm.current_record r
     LEFT JOIN LATERAL jsonb_array_elements(coalesce(r.body -> 'periods', '[]'::jsonb))
          WITH ORDINALITY AS p(period, n) ON true
     LEFT JOIN mdm.current_entity f ON f.object_id = r.body ->> 'source_id'
     LEFT JOIN mdm.current_entity t ON t.object_id = r.body ->> 'target_id'
  WHERE r.object_type = 'relationship'
    AND coalesce(r.body -> 'retired', 'false'::jsonb) = 'false'::jsonb;

COMMENT ON VIEW mdm.relationship_context IS
    'Every mastered relationship of any type, both ends named, one row per period (a link held, left and held again has two rows). A derived link (a calculated ultimate parent) has one row with no dates. Retired links are left out. What each type means is in the Mastering Policy''s relationship types.';
COMMENT ON COLUMN mdm.relationship_context.relationship_id IS 'The relationship: one per type, pair of entities, scope and (for a person) capacity.';
COMMENT ON COLUMN mdm.relationship_context.type IS 'The relationship type, as the Mastering Policy names it.';
COMMENT ON COLUMN mdm.relationship_context.from_entity_id IS 'The entity the relationship starts at (the child, for a parent link).';
COMMENT ON COLUMN mdm.relationship_context.from_kind IS 'The kind of that entity.';
COMMENT ON COLUMN mdm.relationship_context.from_name IS 'Its name, or for a person its legal name.';
COMMENT ON COLUMN mdm.relationship_context.to_entity_id IS 'The entity the relationship ends at (the parent, for a parent link).';
COMMENT ON COLUMN mdm.relationship_context.to_kind IS 'The kind of that entity.';
COMMENT ON COLUMN mdm.relationship_context.to_name IS 'Its name, or for a person its legal name.';
COMMENT ON COLUMN mdm.relationship_context.role IS 'The capacity a person holds in the relationship (a director, an owner); empty for other links.';
COMMENT ON COLUMN mdm.relationship_context.scope IS 'The family of relationships the source states it in (for example consolidated accounts); empty when the source names none.';
COMMENT ON COLUMN mdm.relationship_context.derived IS 'True for a link MDM calculates (an ultimate parent walked from the stated parents), false for a stated one.';
COMMENT ON COLUMN mdm.relationship_context.period IS 'Which period of the relationship this row is, counting from one.';
COMMENT ON COLUMN mdm.relationship_context.valid_from IS 'When the period began.';
COMMENT ON COLUMN mdm.relationship_context.valid_to IS 'When the period ended; empty while it holds.';
COMMENT ON COLUMN mdm.relationship_context.valid_from_basis IS 'For a person''s link: stated (the source said so) or observed (first seen then).';
COMMENT ON COLUMN mdm.relationship_context.valid_to_basis IS 'For a person''s link: stated or observed; empty while it holds.';
COMMENT ON COLUMN mdm.relationship_context.last_seen IS 'When a source last stated the relationship; silence never ends one.';
COMMENT ON COLUMN mdm.relationship_context.sources IS 'The source records that state it: each a source code and record key.';
COMMENT ON COLUMN mdm.relationship_context.batch_id IS 'The batch that last wrote the relationship.';

-- Whether a stated relationship holds at a time: not retired, not derived, and
-- one of its periods covers that time.
CREATE FUNCTION mdm.relationship_holds(body jsonb, at timestamp with time zone) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    SET search_path TO 'pg_catalog'
    AS $$
    SELECT coalesce(body -> 'retired', 'false'::jsonb) = 'false'::jsonb
       AND NOT coalesce((body ->> 'derived')::boolean, false)
       AND EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(body -> 'periods', '[]'::jsonb)) p(period)
                    WHERE (p.period ->> 'valid_from')::timestamptz <= at
                      AND (p.period ->> 'valid_to' IS NULL OR (p.period ->> 'valid_to')::timestamptz > at))
$$;

COMMENT ON FUNCTION mdm.relationship_holds(jsonb, timestamp with time zone) IS
    'Whether a stated relationship holds at a time: it is not retired, and one of its periods covers that time.';

-- The parent chain of one entity through one relationship type, within the
-- scope of each first link (the engine checks cycles and one parent per type
-- and scope), up to max_hops links (at most 50), each relationship holding at
-- `at`. Each step finds the next links through current_record_link_start.
CREATE FUNCTION mdm.relationship_chain(entity_id text, relationship_type text, max_hops integer DEFAULT 3,
                                       at timestamp with time zone DEFAULT now())
    RETURNS TABLE(depth integer, relationship_id text, scope text, from_entity_id text, from_name text,
                  to_entity_id text, to_name text, cycle boolean)
    LANGUAGE sql STABLE STRICT PARALLEL SAFE
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
    WITH RECURSIVE walk(depth, relationship_id, scope, from_entity_id, to_entity_id, path, cycle) AS (
        SELECT 1, r.object_id, r.body ->> 'scope', r.body ->> 'source_id', r.body ->> 'target_id',
               ARRAY[r.body ->> 'source_id', r.body ->> 'target_id'], r.body ->> 'target_id' = r.body ->> 'source_id'
          FROM mdm.current_record r
         WHERE r.object_type = 'relationship'
           AND r.body ->> 'source_id' = relationship_chain.entity_id
           AND r.body ->> 'type' = relationship_chain.relationship_type
           AND mdm.relationship_holds(r.body, relationship_chain.at)
           AND relationship_chain.max_hops >= 1
        UNION ALL
        SELECT w.depth + 1, r.object_id, w.scope, r.body ->> 'source_id', r.body ->> 'target_id',
               w.path || (r.body ->> 'target_id'), (r.body ->> 'target_id') = ANY(w.path)
          FROM walk w
          JOIN mdm.current_record r
            ON r.object_type = 'relationship' AND r.body ->> 'source_id' = w.to_entity_id
         WHERE r.body ->> 'type' = relationship_chain.relationship_type
           AND r.body ->> 'scope' = w.scope
           AND mdm.relationship_holds(r.body, relationship_chain.at)
           AND NOT w.cycle AND w.depth < least(relationship_chain.max_hops, 50)
    )
    SELECT w.depth, w.relationship_id, w.scope, w.from_entity_id, mdm.entity_name(f.body),
           w.to_entity_id, mdm.entity_name(t.body), w.cycle
      FROM walk w
      LEFT JOIN mdm.current_entity f ON f.object_id = w.from_entity_id
      LEFT JOIN mdm.current_entity t ON t.object_id = w.to_entity_id
     ORDER BY w.depth, w.relationship_id
$$;

COMMENT ON FUNCTION mdm.relationship_chain(text, text, integer, timestamp with time zone) IS
    'The parents of one entity through one relationship type, nearest first: within one scope, up to max_hops links (at most 50; the context command asks for at most 3), using the links that hold at a time (now, unless given). A link back to an entity already on the chain ends it, marked cycle.';
