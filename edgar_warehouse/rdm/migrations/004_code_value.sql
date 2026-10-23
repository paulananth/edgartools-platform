-- A code may carry one typed value for its period (ticket 133): a statutory
-- rate, a threshold. The value is exact decimal text, as filed, never a float;
-- its unit says what it measures. Both or neither. Existing codes hold neither,
-- so every version already published keeps its canonical bytes and its pin.
ALTER TABLE rdm.code
  ADD COLUMN value text CHECK (value ~ '^-?[0-9]+(\.[0-9]+)?$'),
  ADD COLUMN unit text CHECK (btrim(unit) <> ''),
  ADD CONSTRAINT code_value_has_unit CHECK ((value IS NULL) = (unit IS NULL));
COMMENT ON COLUMN rdm.code.value IS 'The code''s value for its period (valid_from to valid_to), as exact decimal text; empty for a code that only names something.';
COMMENT ON COLUMN rdm.code.unit IS 'What the value measures, such as "percent of taxable income"; set exactly when value is.';

-- Agents read a code's value through the context view (spec §5): 002's view
-- with the two columns added at its end.
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
       c.unit
  FROM rdm.code c
  JOIN rdm.code_set_version v ON (v.code_set, v.version) = (c.code_set, c.version)
  JOIN rdm.code_set s ON s.code_set = c.code_set
  JOIN rdm.code_path p ON (p.code_set, p.version, p.code) = (c.code_set, c.version, c.code)
 WHERE v.status IN ('published', 'retired');
COMMENT ON COLUMN rdm.code_context.value IS 'The code''s value for its period, as exact decimal text; empty for a code that only names something.';
COMMENT ON COLUMN rdm.code_context.unit IS 'What the value measures.';
