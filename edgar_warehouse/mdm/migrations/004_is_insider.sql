-- `IS_INSIDER` is no mastered link of its own (`docs/specs/person/consumer.md`,
-- "Relationships"; mastering to-do 14). It is this view over the two Person
-- link types, kept to the Section 16 capacities, so readers keep the name they
-- query without a second mastered fact. `INSIDER_OF` is gone.

CREATE VIEW mdm.is_insider AS
 SELECT p.object_id AS relationship_id,
    (p.body ->> 'source_id'::text) AS person_id,
    (p.body ->> 'target_id'::text) AS company_id,
    (p.body ->> 'type'::text) AS link_type,
    (p.body ->> 'capacity'::text) AS capacity,
    (p.body -> 'periods'::text) AS periods
   FROM mdm.current_record p
  WHERE ((p.object_type = 'relationship'::text)
    AND ((p.body ->> 'type'::text) = ANY (ARRAY['EMPLOYED_BY'::text, 'CONTROLS'::text]))
    AND ((p.body ->> 'capacity'::text) = ANY (ARRAY['director'::text, 'officer'::text, 'ten_percent_owner'::text]))
    AND ((p.body ->> 'retired'::text) IS DISTINCT FROM 'true'::text));

COMMENT ON VIEW mdm.is_insider IS
    'Each Person who is or was a Section 16 insider of a Company: a director, officer or 10% owner link, read from current_record; its periods say when. Not a link of its own: the EMPLOYED_BY and CONTROLS links it shows are the mastered facts. For readers that ask for insiders by that name.';
COMMENT ON COLUMN mdm.is_insider.relationship_id IS 'The id of the EMPLOYED_BY or CONTROLS link it shows.';
COMMENT ON COLUMN mdm.is_insider.person_id IS 'The Person.';
COMMENT ON COLUMN mdm.is_insider.company_id IS 'The Company the Person is an insider of.';
COMMENT ON COLUMN mdm.is_insider.link_type IS 'EMPLOYED_BY for a director or officer, CONTROLS for a 10% owner.';
COMMENT ON COLUMN mdm.is_insider.capacity IS 'director, officer or ten_percent_owner.';
COMMENT ON COLUMN mdm.is_insider.periods IS 'The link''s dated periods, each date with its basis (stated or observed), its last sighting and its titles.';
