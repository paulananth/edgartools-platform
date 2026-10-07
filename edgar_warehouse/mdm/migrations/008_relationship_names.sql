-- Relationship types under their sources' own names (profiling ticket 04b;
-- operator, 2026-10-07, each name approved one by one).
--
-- Each relationship's basis: stated
-- (a source says it) or calculated (MDM derived it, e.g. an ultimate parent
-- walked from the stated direct parents). A calculated ultimate parent is now
-- written under the same type as a stated one, so the basis tells them apart.
CREATE OR REPLACE VIEW mdm.relationship_context AS
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
    r.batch_id,
    CASE WHEN coalesce((r.body ->> 'derived')::boolean, false) THEN 'calculated' ELSE 'stated' END AS basis
   FROM mdm.current_record r
     LEFT JOIN LATERAL jsonb_array_elements(coalesce(r.body -> 'periods', '[]'::jsonb))
          WITH ORDINALITY AS p(period, n) ON true
     LEFT JOIN mdm.current_entity f ON f.object_id = r.body ->> 'source_id'
     LEFT JOIN mdm.current_entity t ON t.object_id = r.body ->> 'target_id'
  WHERE r.object_type = 'relationship'
    AND coalesce(r.body -> 'retired', 'false'::jsonb) = 'false'::jsonb;

COMMENT ON COLUMN mdm.relationship_context.basis IS 'stated (a source says it) or calculated (MDM derived it, such as an ultimate parent walked from the stated direct parents). A stated and a calculated link of one type sit side by side, so a disagreement shows.';

-- The insider view reads the 10% owner from BENEFICIAL_OWNER_OF (capacity
-- ten_percent_owner, the Forms 3/4/5 flag); CONTROLS is gone from the policy,
-- and is still read for links an earlier policy mastered.
CREATE OR REPLACE VIEW mdm.is_insider AS
 SELECT p.object_id AS relationship_id,
    (p.body ->> 'source_id'::text) AS person_id,
    (p.body ->> 'target_id'::text) AS company_id,
    (p.body ->> 'type'::text) AS link_type,
    (p.body ->> 'capacity'::text) AS capacity,
    (p.body -> 'periods'::text) AS periods
   FROM mdm.current_record p
  WHERE p.object_type = 'relationship'::text
    AND ((p.body ->> 'type' = 'EMPLOYED_BY' AND p.body ->> 'capacity' IN ('director', 'officer'))
      OR (p.body ->> 'type' IN ('BENEFICIAL_OWNER_OF', 'CONTROLS') AND p.body ->> 'capacity' = 'ten_percent_owner'))
    AND (p.body ->> 'retired'::text) IS DISTINCT FROM 'true'::text;

COMMENT ON VIEW mdm.is_insider IS
    'Each one who is or was a Section 16 insider of a Company: a director or officer (EMPLOYED_BY), or a ten percent owner (BENEFICIAL_OWNER_OF; a person, or an entity, which person_id then holds), read from current_record; its periods say when. Not a link of its own: the links it shows are the mastered facts. For readers that ask for insiders by that name.';
COMMENT ON COLUMN mdm.is_insider.relationship_id IS 'The id of the EMPLOYED_BY or BENEFICIAL_OWNER_OF link it shows.';
COMMENT ON COLUMN mdm.is_insider.link_type IS 'EMPLOYED_BY for a director or officer, BENEFICIAL_OWNER_OF for a ten percent owner (CONTROLS for one an earlier policy mastered).';
