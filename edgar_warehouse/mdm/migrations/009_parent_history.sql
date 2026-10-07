-- Parent links follow corporate actions (profiling ticket 04b, part B;
-- operator, 2026-10-07: "It should also consider corporate actions").
--
-- Every stated link's dates now carry their basis, not only a person's: stated
-- when the source gives the date, observed from when it was first seen. A
-- period a succession ended names that succession (ended_by), and a calculated
-- ultimate parent has periods, one for each stretch its chain held.
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
    CASE WHEN coalesce((r.body ->> 'derived')::boolean, false) THEN 'calculated' ELSE 'stated' END AS basis,
    p.period ->> 'ended_by' AS ended_by
   FROM mdm.current_record r
     LEFT JOIN LATERAL jsonb_array_elements(coalesce(r.body -> 'periods', '[]'::jsonb))
          WITH ORDINALITY AS p(period, n) ON true
     LEFT JOIN mdm.current_entity f ON f.object_id = r.body ->> 'source_id'
     LEFT JOIN mdm.current_entity t ON t.object_id = r.body ->> 'target_id'
  WHERE r.object_type = 'relationship'
    AND coalesce(r.body -> 'retired', 'false'::jsonb) = 'false'::jsonb;

COMMENT ON VIEW mdm.relationship_context IS
    'Every mastered relationship of any type, both ends named, one row per period (a link held, left and held again has two rows). A calculated ultimate parent has one row per stretch of time its chain held; under an earlier algorithm (accounting-chain-v1) it has one row with no dates. Retired links are left out. What each type means is in the Mastering Policy''s relationship types.';
COMMENT ON COLUMN mdm.relationship_context.valid_from_basis IS 'stated (the source gave the date, e.g. a corporate action''s effective date) or observed (first seen then); empty for a calculated link.';
COMMENT ON COLUMN mdm.relationship_context.valid_to_basis IS 'stated or observed; empty while it holds or for a calculated link.';
COMMENT ON COLUMN mdm.relationship_context.period IS 'The period''s number. A calculated ultimate parent has one period for each stretch of time its chain held.';
COMMENT ON COLUMN mdm.relationship_context.ended_by IS 'The succession (e.g. SUCCESSOR_ENTITY) whose date ended this period: the entity at one end ceased then. Empty when a source stated the end, or it holds.';
