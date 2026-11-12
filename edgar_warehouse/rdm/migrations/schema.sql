-- RDM's schema: code sets, their versions, codes, labels, levels, paths and crosswalks.
-- `rdm init` creates it in an empty database; a later change is a numbered file beside this one.
SET LOCAL check_function_bodies = false;

CREATE SCHEMA rdm;

CREATE FUNCTION rdm.code_search(words text, wanted_set text, wanted_version text, max_rows integer) RETURNS TABLE(code_set text, code text, label text, label_path text, version text, matched_by text, rank real)
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'rdm'
    AS $$
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

COMMENT ON FUNCTION rdm.code_search(words text, wanted_set text, wanted_version text, max_rows integer) IS 'Codes of one version of a code set whose label or synonym holds the words: full-text search (simple) ranked first; when it finds nothing, labels and synonyms containing the words as typed.';

CREATE FUNCTION rdm.govern_version() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'rdm'
    AS $$
DECLARE rank_old integer; rank_new integer;
BEGIN
  IF TG_OP IN ('DELETE', 'TRUNCATE') THEN RAISE EXCEPTION 'Reference data history is retained'; END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'draft' OR NEW.approved_by IS NOT NULL OR NEW.approved_words IS NOT NULL
       OR NEW.approved_at IS NOT NULL OR NEW.published_at IS NOT NULL OR NEW.sha256 IS NOT NULL
       OR NEW.valid_from IS NOT NULL OR NEW.valid_to IS NOT NULL THEN
      RAISE EXCEPTION 'A new version must be an unapproved draft'; END IF;
    RETURN NEW;
  END IF;
  IF (NEW.code_set, NEW.version, NEW.created_by, NEW.created_at, NEW.supersedes)
     IS DISTINCT FROM (OLD.code_set, OLD.version, OLD.created_by, OLD.created_at, OLD.supersedes) THEN
    RAISE EXCEPTION 'A version''s identity is immutable'; END IF;
  IF OLD.status <> 'draft' AND NEW.evidence IS DISTINCT FROM OLD.evidence THEN
    RAISE EXCEPTION 'Evidence is fixed once a version is approved'; END IF;
  rank_old := array_position(ARRAY['draft','approved','published','retired'], OLD.status);
  rank_new := array_position(ARRAY['draft','approved','published','retired'], NEW.status);
  IF rank_new < rank_old OR rank_new > rank_old + 1 THEN
    RAISE EXCEPTION 'Invalid reference data lifecycle transition'; END IF;
  IF (NEW.approved_by, NEW.approved_words, NEW.approved_at) IS DISTINCT FROM
     (OLD.approved_by, OLD.approved_words, OLD.approved_at) THEN
    IF OLD.status <> 'draft' OR NEW.status <> 'approved' THEN
      RAISE EXCEPTION 'Approval is recorded once, on a draft'; END IF;
    NEW.approved_at := clock_timestamp();
  END IF;
  IF NEW.status = 'approved' AND (btrim(coalesce(NEW.approved_by, '')) = '' OR btrim(coalesce(NEW.approved_words, '')) = '') THEN
    RAISE EXCEPTION 'An approval names who approved and holds their exact words'; END IF;
  IF NEW.status = 'approved' AND OLD.status = 'draft' AND NEW.approved_by = NEW.created_by THEN
    RAISE EXCEPTION 'The drafter cannot approve its own draft'; END IF;
  IF (NEW.sha256, NEW.published_at, NEW.valid_from) IS DISTINCT FROM (OLD.sha256, OLD.published_at, OLD.valid_from) THEN
    IF OLD.status <> 'approved' OR NEW.status <> 'published' THEN
      RAISE EXCEPTION 'The sha256 and valid_from are set once, when published'; END IF;
  END IF;
  IF NEW.status = 'published' AND OLD.status = 'approved' THEN
    IF NEW.sha256 IS NULL OR NEW.valid_from IS NULL THEN
      RAISE EXCEPTION 'Publishing needs the sha256 and valid_from'; END IF;
    -- A version replaces the newest version ever published (current or
    -- retired), which it must name; the first names nothing.
    IF NEW.supersedes IS DISTINCT FROM (
         SELECT v.version FROM rdm.code_set_version v WHERE v.code_set = NEW.code_set
            AND v.status IN ('published', 'retired') AND v.version <> NEW.version
          ORDER BY v.valid_from DESC LIMIT 1) THEN
      RAISE EXCEPTION 'A published version must supersede the version it replaces'; END IF;
    IF EXISTS (SELECT 1 FROM rdm.code c WHERE c.code_set = NEW.code_set AND c.version = NEW.version
               AND NOT EXISTS (SELECT 1 FROM rdm.code_path p WHERE (p.code_set, p.version, p.code) = (c.code_set, c.version, c.code))) THEN
      RAISE EXCEPTION 'Publishing needs a path for every code'; END IF;
    NEW.published_at := clock_timestamp();
  END IF;
  IF NEW.valid_to IS DISTINCT FROM OLD.valid_to AND (OLD.valid_to IS NOT NULL OR OLD.status NOT IN ('published')) THEN
    RAISE EXCEPTION 'valid_to is set once, on a published version'; END IF;
  IF NEW.status = 'retired' AND OLD.status = 'published' AND NEW.valid_to IS NULL THEN
    NEW.valid_to := clock_timestamp(); END IF;
  RETURN NEW;
END;
$$;

CREATE FUNCTION rdm.guard_content() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'rdm'
    AS $$
DECLARE row_set text; row_version text; current_status text;
BEGIN
  IF TG_TABLE_NAME = 'crosswalk_row' THEN
    row_set := coalesce(NEW.from_set, OLD.from_set); row_version := coalesce(NEW.from_version, OLD.from_version);
  ELSE
    row_set := coalesce(NEW.code_set, OLD.code_set); row_version := coalesce(NEW.version, OLD.version);
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF TG_TABLE_NAME = 'crosswalk_row' THEN
      IF (NEW.from_set, NEW.from_version) IS DISTINCT FROM (OLD.from_set, OLD.from_version) THEN
        RAISE EXCEPTION 'A row stays in its version'; END IF;
    ELSIF (NEW.code_set, NEW.version) IS DISTINCT FROM (OLD.code_set, OLD.version) THEN
      RAISE EXCEPTION 'A row stays in its version'; END IF;
  END IF;
  SELECT status INTO current_status FROM rdm.code_set_version
    WHERE code_set = row_set AND version = row_version FOR SHARE;
  IF TG_TABLE_NAME = 'code_path' THEN
    IF TG_OP <> 'INSERT' OR current_status IS DISTINCT FROM 'approved' THEN
      RAISE EXCEPTION 'Paths are written once, while an approved version is published'; END IF;
  ELSIF current_status IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'Only a draft version''s content may change'; END IF;
  RETURN coalesce(NEW, OLD);
END;
$$;

CREATE TABLE rdm.code (
    code_set text NOT NULL,
    version text NOT NULL,
    code text NOT NULL,
    label text NOT NULL,
    definition text DEFAULT ''::text NOT NULL,
    parent_code text,
    valid_from date,
    valid_to date,
    status text DEFAULT 'valid'::text NOT NULL,
    invalid_reason text,
    value text,
    unit text,
    properties jsonb,
    CONSTRAINT code_check CHECK (((valid_to IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT code_check1 CHECK (((status = 'invalid'::text) = (invalid_reason IS NOT NULL))),
    CONSTRAINT code_check2 CHECK ((parent_code IS DISTINCT FROM code)),
    CONSTRAINT code_code_check CHECK ((code <> ''::text)),
    CONSTRAINT code_properties_check CHECK (((properties IS NULL) OR ((jsonb_typeof(properties) = 'object'::text) AND (properties <> '{}'::jsonb)))),
    CONSTRAINT code_status_check CHECK ((status = ANY (ARRAY['valid'::text, 'invalid'::text]))),
    CONSTRAINT code_unit_check CHECK ((btrim(unit) <> ''::text)),
    CONSTRAINT code_value_check CHECK ((value ~ '^-?[0-9]+(\.[0-9]+)?$'::text)),
    CONSTRAINT code_value_has_unit CHECK (((value IS NULL) = (unit IS NULL)))
);

COMMENT ON TABLE rdm.code IS 'One code of a version, with its meaning and, in a reference hierarchy, its one parent.';

COMMENT ON COLUMN rdm.code.code_set IS 'The code set.';

COMMENT ON COLUMN rdm.code.version IS 'The version.';

COMMENT ON COLUMN rdm.code.code IS 'The code as values carry it.';

COMMENT ON COLUMN rdm.code.label IS 'What the code stands for, in a few words.';

COMMENT ON COLUMN rdm.code.definition IS 'What the code stands for, in full.';

COMMENT ON COLUMN rdm.code.parent_code IS 'The code above it in this version''s one hierarchy; empty at the top.';

COMMENT ON COLUMN rdm.code.valid_from IS 'The first day the code means this.';

COMMENT ON COLUMN rdm.code.valid_to IS 'The last day the code means this.';

COMMENT ON COLUMN rdm.code.status IS 'valid, or invalid: kept, but breaking a rule of the version (such as its hierarchy).';

COMMENT ON COLUMN rdm.code.invalid_reason IS 'Why an invalid code is invalid; empty for a valid one.';

COMMENT ON COLUMN rdm.code.value IS 'The code''s value for its period (valid_from to valid_to), as exact decimal text; empty for a code that only names something.';

COMMENT ON COLUMN rdm.code.unit IS 'What the value measures, such as "percent of taxable income"; set exactly when value is.';

COMMENT ON COLUMN rdm.code.properties IS 'The code''s named properties: text, true or false, or a list of texts; empty for a code that has none.';

CREATE TABLE rdm.code_label (
    code_set text NOT NULL,
    version text NOT NULL,
    code text NOT NULL,
    language text DEFAULT 'en'::text NOT NULL,
    label text NOT NULL,
    kind text NOT NULL,
    source text DEFAULT ''::text NOT NULL,
    CONSTRAINT code_label_kind_check CHECK ((kind = ANY (ARRAY['preferred'::text, 'synonym'::text]))),
    CONSTRAINT code_label_label_check CHECK ((btrim(label) <> ''::text)),
    CONSTRAINT code_label_language_check CHECK ((language ~ '^[a-z]{2,3}(-[A-Za-z0-9]+)*$'::text))
);

COMMENT ON TABLE rdm.code_label IS 'The names a code goes by, per language: one preferred and any synonyms. Search reads them.';

COMMENT ON COLUMN rdm.code_label.code_set IS 'The code set.';

COMMENT ON COLUMN rdm.code_label.version IS 'The version.';

COMMENT ON COLUMN rdm.code_label.code IS 'The code named.';

COMMENT ON COLUMN rdm.code_label.language IS 'The language of the name (BCP 47).';

COMMENT ON COLUMN rdm.code_label.label IS 'The name.';

COMMENT ON COLUMN rdm.code_label.kind IS 'preferred or synonym.';

COMMENT ON COLUMN rdm.code_label.source IS 'Where the name came from: steward, profiling, an agent draft, a migrated file.';

CREATE TABLE rdm.code_path (
    code_set text NOT NULL,
    version text NOT NULL,
    code text NOT NULL,
    path text NOT NULL,
    label_path text NOT NULL,
    level text,
    depth integer NOT NULL,
    CONSTRAINT code_path_depth_check CHECK ((depth >= 1))
);

COMMENT ON TABLE rdm.code_path IS 'Each code''s place in the hierarchy, written once when the version is published. A subtree is path LIKE ''<path>/%''.';

COMMENT ON COLUMN rdm.code_path.code_set IS 'The code set.';

COMMENT ON COLUMN rdm.code_path.version IS 'The version.';

COMMENT ON COLUMN rdm.code_path.code IS 'The code.';

COMMENT ON COLUMN rdm.code_path.path IS 'The codes from the top down to this one, joined by "/" (a "/" or "\" inside a code is escaped with "\").';

COMMENT ON COLUMN rdm.code_path.label_path IS 'The labels from the top down, joined by " > ".';

COMMENT ON COLUMN rdm.code_path.level IS 'The name of the code''s level, when stewards named it.';

COMMENT ON COLUMN rdm.code_path.depth IS 'How deep the code is; 1 is the top.';

CREATE TABLE rdm.code_set (
    code_set text NOT NULL,
    name text NOT NULL,
    definition text DEFAULT ''::text NOT NULL,
    authority text DEFAULT ''::text NOT NULL,
    steward text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT code_set_code_set_check CHECK ((code_set ~ '^[a-z0-9][a-z0-9_.-]*$'::text)),
    CONSTRAINT code_set_name_check CHECK ((btrim(name) <> ''::text))
);

COMMENT ON TABLE rdm.code_set IS 'One list of codes that gives values their meaning. Written once, when its first version is drafted, and never changed (meaning that changes is a version''s hint); read by every consumer of reference data.';

COMMENT ON COLUMN rdm.code_set.code_set IS 'The code set''s id: lower case letters, digits, dot, dash, underscore.';

COMMENT ON COLUMN rdm.code_set.name IS 'The code set''s name in plain words.';

COMMENT ON COLUMN rdm.code_set.definition IS 'What the codes stand for.';

COMMENT ON COLUMN rdm.code_set.authority IS 'Who issues the codes: a standard body, a source, or internal.';

COMMENT ON COLUMN rdm.code_set.steward IS 'Who looks after the code set.';

COMMENT ON COLUMN rdm.code_set.created_at IS 'When the code set was first written.';

CREATE TABLE rdm.code_set_version (
    code_set text NOT NULL,
    version text NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    valid_from timestamp with time zone,
    valid_to timestamp with time zone,
    supersedes text,
    created_by text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    evidence jsonb DEFAULT '{}'::jsonb NOT NULL,
    approved_by text,
    approved_words text,
    approved_at timestamp with time zone,
    published_at timestamp with time zone,
    sha256 text,
    CONSTRAINT code_set_version_check CHECK (((valid_to IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT code_set_version_created_by_check CHECK ((btrim(created_by) <> ''::text)),
    CONSTRAINT code_set_version_evidence_check CHECK ((jsonb_typeof(evidence) = 'object'::text)),
    CONSTRAINT code_set_version_sha256_check CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT code_set_version_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'approved'::text, 'published'::text, 'retired'::text]))),
    CONSTRAINT code_set_version_version_check CHECK ((version ~ '^[A-Za-z0-9][A-Za-z0-9_.-]*$'::text))
);

COMMENT ON TABLE rdm.code_set_version IS 'One version of a code set: drafted by an agent or a steward, approved in the operator''s words, published once and never changed. Consumers pin a version by its sha256.';

COMMENT ON COLUMN rdm.code_set_version.code_set IS 'The code set this version belongs to.';

COMMENT ON COLUMN rdm.code_set_version.version IS 'The version label.';

COMMENT ON COLUMN rdm.code_set_version.status IS 'draft, approved, published or retired; only forward.';

COMMENT ON COLUMN rdm.code_set_version.valid_from IS 'When this version became the published one.';

COMMENT ON COLUMN rdm.code_set_version.valid_to IS 'When a later version replaced it; empty while it is the current one.';

COMMENT ON COLUMN rdm.code_set_version.supersedes IS 'The version this one replaces, if any.';

COMMENT ON COLUMN rdm.code_set_version.created_by IS 'The agent and skill, or the person, who drafted it.';

COMMENT ON COLUMN rdm.code_set_version.created_at IS 'When the draft was written.';

COMMENT ON COLUMN rdm.code_set_version.evidence IS 'Why the draft says what it says: the profiling findings it came from, counts.';

COMMENT ON COLUMN rdm.code_set_version.approved_by IS 'Who approved it: the operator.';

COMMENT ON COLUMN rdm.code_set_version.approved_words IS 'The operator''s exact words of approval.';

COMMENT ON COLUMN rdm.code_set_version.approved_at IS 'When the approval was recorded.';

COMMENT ON COLUMN rdm.code_set_version.published_at IS 'When it was published.';

COMMENT ON COLUMN rdm.code_set_version.sha256 IS 'The sha256 of the version''s canonical form; what a consumer pins.';

CREATE TABLE rdm.crosswalk_row (
    from_set text NOT NULL,
    from_version text NOT NULL,
    from_code text NOT NULL,
    to_set text NOT NULL,
    to_version text NOT NULL,
    to_code text NOT NULL,
    match_type text NOT NULL,
    evidence jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT crosswalk_row_evidence_check CHECK ((jsonb_typeof(evidence) = 'object'::text)),
    CONSTRAINT crosswalk_row_match_type_check CHECK ((match_type = ANY (ARRAY['exact'::text, 'close'::text, 'broad'::text, 'narrow'::text]))),
    CONSTRAINT crosswalk_row_to_code_check CHECK ((to_code <> ''::text)),
    CONSTRAINT crosswalk_row_to_set_check CHECK ((to_set ~ '^[a-z0-9][a-z0-9_.-]*$'::text)),
    CONSTRAINT crosswalk_row_to_version_check CHECK ((btrim(to_version) <> ''::text))
);

COMMENT ON TABLE rdm.crosswalk_row IS 'A code of this version mapped to a code of another code set, which RDM may or may not hold (an outside standard).';

COMMENT ON COLUMN rdm.crosswalk_row.from_set IS 'The code set mapped from.';

COMMENT ON COLUMN rdm.crosswalk_row.from_version IS 'Its version.';

COMMENT ON COLUMN rdm.crosswalk_row.from_code IS 'The code mapped from.';

COMMENT ON COLUMN rdm.crosswalk_row.to_set IS 'The code set mapped to.';

COMMENT ON COLUMN rdm.crosswalk_row.to_version IS 'Its version; "outside" when RDM does not hold that code set.';

COMMENT ON COLUMN rdm.crosswalk_row.to_code IS 'The code mapped to.';

COMMENT ON COLUMN rdm.crosswalk_row.match_type IS 'exact, close, broad (the target is broader) or narrow (the target is narrower), as SKOS mapping relations.';

COMMENT ON COLUMN rdm.crosswalk_row.evidence IS 'Why the mapping holds.';

CREATE VIEW rdm.code_context AS
 SELECT c.code_set,
    s.name AS code_set_name,
    c.code,
    c.label,
    c.definition,
    COALESCE(( SELECT jsonb_agg(l.label ORDER BY l.language, l.label) AS jsonb_agg
           FROM rdm.code_label l
          WHERE (((l.code_set = c.code_set) AND (l.version = c.version) AND (l.code = c.code)) AND (l.kind = 'synonym'::text))), '[]'::jsonb) AS synonyms,
    p.path,
    p.label_path,
    p.level,
    p.depth,
    c.parent_code,
    COALESCE(( SELECT jsonb_agg(jsonb_build_object('to_set', x.to_set, 'to_version', x.to_version, 'to_code', x.to_code, 'match_type', x.match_type) ORDER BY x.to_set, x.to_version, x.to_code) AS jsonb_agg
           FROM rdm.crosswalk_row x
          WHERE ((x.from_set = c.code_set) AND (x.from_version = c.version) AND (x.from_code = c.code))), '[]'::jsonb) AS crosswalk,
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
   FROM (((rdm.code c
     JOIN rdm.code_set_version v ON (((v.code_set = c.code_set) AND (v.version = c.version))))
     JOIN rdm.code_set s ON ((s.code_set = c.code_set)))
     JOIN rdm.code_path p ON (((p.code_set = c.code_set) AND (p.version = c.version) AND (p.code = c.code))))
  WHERE (v.status = ANY (ARRAY['published'::text, 'retired'::text]));

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

COMMENT ON COLUMN rdm.code_context.value IS 'The code''s value for its period, as exact decimal text; empty for a code that only names something.';

COMMENT ON COLUMN rdm.code_context.unit IS 'What the value measures.';

COMMENT ON COLUMN rdm.code_context.properties IS 'The code''s named properties.';

CREATE TABLE rdm.code_set_hint (
    code_set text NOT NULL,
    version text NOT NULL,
    kind text NOT NULL,
    ordinal integer NOT NULL,
    text text NOT NULL,
    CONSTRAINT code_set_hint_kind_check CHECK ((kind = ANY (ARRAY['meaning'::text, 'use_when'::text, 'avoid_when'::text, 'example_question'::text]))),
    CONSTRAINT code_set_hint_ordinal_check CHECK ((ordinal >= 1)),
    CONSTRAINT code_set_hint_text_check CHECK ((btrim(text) <> ''::text))
);

COMMENT ON TABLE rdm.code_set_hint IS 'Plain-words hints for an agent using this code set: what its codes mean, when to use it, when not to, and questions it answers.';

COMMENT ON COLUMN rdm.code_set_hint.code_set IS 'The code set.';

COMMENT ON COLUMN rdm.code_set_hint.version IS 'The version.';

COMMENT ON COLUMN rdm.code_set_hint.kind IS 'meaning, use_when, avoid_when or example_question.';

COMMENT ON COLUMN rdm.code_set_hint.ordinal IS 'The hint''s place among hints of its kind.';

COMMENT ON COLUMN rdm.code_set_hint.text IS 'The hint.';

CREATE TABLE rdm.code_set_usage (
    code_set text NOT NULL,
    version text NOT NULL,
    store text NOT NULL,
    object text NOT NULL,
    field text NOT NULL,
    match text DEFAULT 'exact'::text NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    CONSTRAINT code_set_usage_field_check CHECK ((btrim(field) <> ''::text)),
    CONSTRAINT code_set_usage_match_check CHECK ((match = ANY (ARRAY['exact'::text, 'upper_trimmed'::text]))),
    CONSTRAINT code_set_usage_object_check CHECK ((btrim(object) <> ''::text)),
    CONSTRAINT code_set_usage_store_check CHECK ((store = ANY (ARRAY['mdm'::text, 'silver'::text, 'source'::text, 'other'::text])))
);

COMMENT ON TABLE rdm.code_set_usage IS 'Where values of this code set live in the data, so an agent can find and compare them without guessing.';

COMMENT ON COLUMN rdm.code_set_usage.code_set IS 'The code set.';

COMMENT ON COLUMN rdm.code_set_usage.version IS 'The version.';

COMMENT ON COLUMN rdm.code_set_usage.store IS 'Where the field is: mdm (a mastered field), silver (a table column), source (a feed''s field path), other.';

COMMENT ON COLUMN rdm.code_set_usage.object IS 'The kind, table or source that holds the field.';

COMMENT ON COLUMN rdm.code_set_usage.field IS 'The field, column or path whose values are codes of this set.';

COMMENT ON COLUMN rdm.code_set_usage.match IS 'How a value is compared with a code: exact, or upper_trimmed (upper case, spaces trimmed).';

COMMENT ON COLUMN rdm.code_set_usage.note IS 'Anything an agent must know about this field''s values.';

CREATE TABLE rdm.level (
    code_set text NOT NULL,
    version text NOT NULL,
    depth integer NOT NULL,
    name text NOT NULL,
    definition text DEFAULT ''::text NOT NULL,
    CONSTRAINT level_depth_check CHECK ((depth >= 1)),
    CONSTRAINT level_name_check CHECK ((btrim(name) <> ''::text))
);

COMMENT ON TABLE rdm.level IS 'The names stewards give the depths of a version''s hierarchy (depth 1 is the top).';

COMMENT ON COLUMN rdm.level.code_set IS 'The code set.';

COMMENT ON COLUMN rdm.level.version IS 'The version.';

COMMENT ON COLUMN rdm.level.depth IS 'The depth named; 1 is the top.';

COMMENT ON COLUMN rdm.level.name IS 'The level''s name.';

COMMENT ON COLUMN rdm.level.definition IS 'What codes at this level are.';

ALTER TABLE ONLY rdm.code_label
    ADD CONSTRAINT code_label_pkey PRIMARY KEY (code_set, version, code, language, label);

ALTER TABLE ONLY rdm.code_path
    ADD CONSTRAINT code_path_pkey PRIMARY KEY (code_set, version, code);

ALTER TABLE ONLY rdm.code
    ADD CONSTRAINT code_pkey PRIMARY KEY (code_set, version, code);

ALTER TABLE ONLY rdm.code_set_hint
    ADD CONSTRAINT code_set_hint_pkey PRIMARY KEY (code_set, version, kind, ordinal);

ALTER TABLE ONLY rdm.code_set
    ADD CONSTRAINT code_set_pkey PRIMARY KEY (code_set);

ALTER TABLE ONLY rdm.code_set_usage
    ADD CONSTRAINT code_set_usage_pkey PRIMARY KEY (code_set, version, store, object, field);

ALTER TABLE ONLY rdm.code_set_version
    ADD CONSTRAINT code_set_version_pkey PRIMARY KEY (code_set, version);

ALTER TABLE ONLY rdm.crosswalk_row
    ADD CONSTRAINT crosswalk_row_pkey PRIMARY KEY (from_set, from_version, from_code, to_set, to_version, to_code);

ALTER TABLE ONLY rdm.level
    ADD CONSTRAINT level_pkey PRIMARY KEY (code_set, version, depth);

CREATE INDEX code_label_words ON rdm.code USING gin (to_tsvector('simple'::regconfig, label));

CREATE INDEX code_path_prefix ON rdm.code_path USING btree (code_set, version, path text_pattern_ops);

CREATE INDEX code_synonym_words ON rdm.code_label USING gin (to_tsvector('simple'::regconfig, label));

CREATE UNIQUE INDEX one_current_published ON rdm.code_set_version USING btree (code_set) WHERE ((status = 'published'::text) AND (valid_to IS NULL));

CREATE UNIQUE INDEX one_preferred_label ON rdm.code_label USING btree (code_set, version, code, language) WHERE (kind = 'preferred'::text);

CREATE TRIGGER code_guard BEFORE INSERT OR DELETE OR UPDATE ON rdm.code FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();

CREATE TRIGGER code_label_guard BEFORE INSERT OR DELETE OR UPDATE ON rdm.code_label FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();

CREATE TRIGGER code_path_guard BEFORE INSERT OR DELETE OR UPDATE ON rdm.code_path FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();

CREATE TRIGGER crosswalk_guard BEFORE INSERT OR DELETE OR UPDATE ON rdm.crosswalk_row FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();

CREATE TRIGGER hint_guard BEFORE INSERT OR DELETE OR UPDATE ON rdm.code_set_hint FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();

CREATE TRIGGER level_guard BEFORE INSERT OR DELETE OR UPDATE ON rdm.level FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();

CREATE TRIGGER no_truncate_version BEFORE TRUNCATE ON rdm.code_set_version FOR EACH STATEMENT EXECUTE FUNCTION rdm.govern_version();

CREATE TRIGGER usage_guard BEFORE INSERT OR DELETE OR UPDATE ON rdm.code_set_usage FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();

CREATE TRIGGER version_governance BEFORE INSERT OR DELETE OR UPDATE ON rdm.code_set_version FOR EACH ROW EXECUTE FUNCTION rdm.govern_version();

ALTER TABLE ONLY rdm.code
    ADD CONSTRAINT code_code_set_version_fkey FOREIGN KEY (code_set, version) REFERENCES rdm.code_set_version(code_set, version);

ALTER TABLE ONLY rdm.code
    ADD CONSTRAINT code_code_set_version_parent_code_fkey FOREIGN KEY (code_set, version, parent_code) REFERENCES rdm.code(code_set, version, code) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY rdm.code_label
    ADD CONSTRAINT code_label_code_set_version_code_fkey FOREIGN KEY (code_set, version, code) REFERENCES rdm.code(code_set, version, code);

ALTER TABLE ONLY rdm.code_path
    ADD CONSTRAINT code_path_code_set_version_code_fkey FOREIGN KEY (code_set, version, code) REFERENCES rdm.code(code_set, version, code);

ALTER TABLE ONLY rdm.code_set_hint
    ADD CONSTRAINT code_set_hint_code_set_version_fkey FOREIGN KEY (code_set, version) REFERENCES rdm.code_set_version(code_set, version);

ALTER TABLE ONLY rdm.code_set_usage
    ADD CONSTRAINT code_set_usage_code_set_version_fkey FOREIGN KEY (code_set, version) REFERENCES rdm.code_set_version(code_set, version);

ALTER TABLE ONLY rdm.code_set_version
    ADD CONSTRAINT code_set_version_code_set_fkey FOREIGN KEY (code_set) REFERENCES rdm.code_set(code_set);

ALTER TABLE ONLY rdm.code_set_version
    ADD CONSTRAINT code_set_version_code_set_supersedes_fkey FOREIGN KEY (code_set, supersedes) REFERENCES rdm.code_set_version(code_set, version);

ALTER TABLE ONLY rdm.crosswalk_row
    ADD CONSTRAINT crosswalk_row_from_set_from_version_from_code_fkey FOREIGN KEY (from_set, from_version, from_code) REFERENCES rdm.code(code_set, version, code);

ALTER TABLE ONLY rdm.level
    ADD CONSTRAINT level_code_set_version_fkey FOREIGN KEY (code_set, version) REFERENCES rdm.code_set_version(code_set, version);
