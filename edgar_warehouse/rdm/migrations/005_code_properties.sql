-- A code may carry named properties (ticket 132): what a code's own words
-- cannot say, such as which kinds a relationship type links. Each value is
-- text, true or false, or a list of texts; the Rust preparation checks them
-- and names them in the canonical form only where a code has some, so every
-- version already published keeps its bytes and its pin.
ALTER TABLE rdm.code
  ADD COLUMN properties jsonb CHECK (properties IS NULL OR (jsonb_typeof(properties) = 'object' AND properties <> '{}'::jsonb));
COMMENT ON COLUMN rdm.code.properties IS 'The code''s named properties: text, true or false, or a list of texts; empty for a code that has none.';

-- Agents read a code's properties through the context view (spec §5): 004's
-- view with the column added at its end.
CREATE OR REPLACE VIEW rdm.code_context AS
SELECT c.code_set,
       s.name AS code_set_name,
       c.code,
       c.label,
       c.definition,
       coalesce((SELECT jsonb_agg(l.label ORDER BY l.language, l.label) FROM rdm.code_label l
                  WHERE (l.code_set, l.version, l.code) = (c.code_set, c.version, c.code) AND l.kind = 'synonym'),
                '[]'::jsonb) AS synonyms,
       p.path,
       p.label_path,
       p.level,
       p.depth,
       c.parent_code,
       coalesce((SELECT jsonb_agg(jsonb_build_object('to_set', x.to_set, 'to_version', x.to_version,
                                                     'to_code', x.to_code, 'match_type', x.match_type)
                                  ORDER BY x.to_set, x.to_version, x.to_code)
                   FROM rdm.crosswalk_row x
                  WHERE (x.from_set, x.from_version, x.from_code) = (c.code_set, c.version, c.code)),
                '[]'::jsonb) AS crosswalk,
       c.version,
       v.sha256,
       v.valid_from,
       v.valid_to,
       v.status AS version_status,
       c.status AS code_status,
       c.valid_from AS code_valid_from,
       c.valid_to AS code_valid_to,
       c.invalid_reason,
       v.approved_by,
       v.approved_at,
       v.published_at,
       c.value,
       c.unit,
       c.properties
  FROM rdm.code c
  JOIN rdm.code_set_version v ON (v.code_set, v.version) = (c.code_set, c.version)
  JOIN rdm.code_set s ON s.code_set = c.code_set
  JOIN rdm.code_path p ON (p.code_set, p.version, p.code) = (c.code_set, c.version, c.code)
 WHERE v.status IN ('published', 'retired');
COMMENT ON COLUMN rdm.code_context.properties IS 'The code''s named properties.';
