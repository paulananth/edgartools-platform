-- What an agent reads of reference data (docs/specs/agent-context/spec.md §2,
-- profiling ticket 05, RDM part): every code of every version ever published,
-- with its meaning, its place in the hierarchy and the version's pin, and a
-- search over labels and synonyms.
CREATE VIEW rdm.code_context AS
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
       v.published_at
  FROM rdm.code c
  JOIN rdm.code_set_version v ON (v.code_set, v.version) = (c.code_set, c.version)
  JOIN rdm.code_set s ON s.code_set = c.code_set
  JOIN rdm.code_path p ON (p.code_set, p.version, p.code) = (c.code_set, c.version, c.code)
 WHERE v.status IN ('published', 'retired');
COMMENT ON VIEW rdm.code_context IS 'One row per code of every version ever published (current, superseded or retired), for agents: what the code means, where it sits in the hierarchy, and the version''s pin. The current version is the one whose valid_to is empty and version_status published.';
COMMENT ON COLUMN rdm.code_context.code_set IS 'The code set.';
COMMENT ON COLUMN rdm.code_context.code_set_name IS 'The code set''s name in plain words.';
COMMENT ON COLUMN rdm.code_context.code IS 'The code as values carry it.';
COMMENT ON COLUMN rdm.code_context.label IS 'What the code stands for, in a few words (its preferred label).';
COMMENT ON COLUMN rdm.code_context.definition IS 'What the code stands for, in full.';
COMMENT ON COLUMN rdm.code_context.synonyms IS 'Other names of the code, as a JSON list.';
COMMENT ON COLUMN rdm.code_context.path IS 'The codes from the top of the hierarchy down to this one, joined by "/".';
COMMENT ON COLUMN rdm.code_context.label_path IS 'The labels from the top down, joined by " > ".';
COMMENT ON COLUMN rdm.code_context.level IS 'The name of the code''s level, when stewards named it.';
COMMENT ON COLUMN rdm.code_context.depth IS 'How deep the code is; 1 is the top.';
COMMENT ON COLUMN rdm.code_context.parent_code IS 'The code above it; empty at the top.';
COMMENT ON COLUMN rdm.code_context.crosswalk IS 'The codes of other code sets it maps to, each with its match type (exact, close, broad, narrow), as a JSON list.';
COMMENT ON COLUMN rdm.code_context.version IS 'The version this row belongs to.';
COMMENT ON COLUMN rdm.code_context.sha256 IS 'The version''s pin: the sha256 of its canonical form.';
COMMENT ON COLUMN rdm.code_context.valid_from IS 'When the version became the published one.';
COMMENT ON COLUMN rdm.code_context.valid_to IS 'When a later version replaced it, or it was retired; empty while current.';
COMMENT ON COLUMN rdm.code_context.version_status IS 'published or retired.';
COMMENT ON COLUMN rdm.code_context.code_status IS 'The code''s status: valid, or invalid (kept, but breaking a rule of the version).';
COMMENT ON COLUMN rdm.code_context.code_valid_from IS 'The first business day the code means this; empty when always.';
COMMENT ON COLUMN rdm.code_context.code_valid_to IS 'The last business day the code means this; empty when still.';
COMMENT ON COLUMN rdm.code_context.invalid_reason IS 'Why an invalid code is invalid.';
COMMENT ON COLUMN rdm.code_context.approved_by IS 'Who approved the version.';
COMMENT ON COLUMN rdm.code_context.approved_at IS 'When the approval was recorded.';
COMMENT ON COLUMN rdm.code_context.published_at IS 'When the version was published.';

-- Word indexes on labels and synonyms (simple configuration: codes and names,
-- not one language's stems).
CREATE INDEX code_label_words ON rdm.code USING gin (to_tsvector('simple', label));
CREATE INDEX code_synonym_words ON rdm.code_label USING gin (to_tsvector('simple', label));

-- The codes of one version whose label or synonym holds the words: full-text
-- search first, ranked; when it finds nothing, labels and synonyms containing
-- the words as typed (% and _ match themselves).
CREATE FUNCTION rdm.code_search(words text, wanted_set text, wanted_version text, max_rows integer)
RETURNS TABLE (code_set text, code text, label text, label_path text, version text, matched_by text, rank real)
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, rdm AS $$
#variable_conflict use_column
DECLARE
  query tsquery := websearch_to_tsquery('simple', words);
  pattern text := '%' || replace(replace(replace(words, '\', '\\'), '%', '\%'), '_', '\_') || '%';
BEGIN
  RETURN QUERY
  WITH hits AS (
    SELECT c.code, 'label'::text AS matched_by, ts_rank_cd(to_tsvector('simple', c.label), query) AS rank
      FROM rdm.code c
     WHERE c.code_set = wanted_set AND c.version = wanted_version AND to_tsvector('simple', c.label) @@ query
    UNION ALL
    SELECT l.code, 'synonym', ts_rank_cd(to_tsvector('simple', l.label), query) * 0.9
      FROM rdm.code_label l
     WHERE l.code_set = wanted_set AND l.version = wanted_version AND l.kind = 'synonym'
       AND to_tsvector('simple', l.label) @@ query),
  best AS (SELECT DISTINCT ON (h.code) h.code, h.matched_by, h.rank FROM hits h ORDER BY h.code, h.rank DESC)
  SELECT x.code_set, b.code, x.label, x.label_path, x.version, b.matched_by, b.rank::real
    FROM best b JOIN rdm.code_context x ON (x.code_set, x.version, x.code) = (wanted_set, wanted_version, b.code)
   ORDER BY b.rank DESC, b.code LIMIT max_rows;
  IF FOUND THEN RETURN; END IF;
  RETURN QUERY
  SELECT x.code_set, x.code, x.label, x.label_path, x.version,
         CASE WHEN x.label ILIKE pattern THEN 'label contains' ELSE 'synonym contains' END, 0::real
    FROM rdm.code_context x
   WHERE x.code_set = wanted_set AND x.version = wanted_version
     AND (x.label ILIKE pattern OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(x.synonyms) s WHERE s ILIKE pattern))
   ORDER BY x.code LIMIT max_rows;
END;
$$;
COMMENT ON FUNCTION rdm.code_search(text, text, text, integer) IS 'Codes of one version of a code set whose label or synonym holds the words: full-text search (simple) ranked first; when it finds nothing, labels and synonyms containing the words as typed.';
REVOKE ALL ON FUNCTION rdm.code_search(text, text, text, integer) FROM PUBLIC;
