-- Reference Data Management (docs/specs/rdm/spec.md, profiling ticket 02).
-- Code sets give values their meaning. Each version is drafted, approved with
-- the operator's words, then published and never changed again.
CREATE SCHEMA rdm;
REVOKE ALL ON SCHEMA rdm FROM PUBLIC;

CREATE TABLE rdm.code_set (
  code_set text PRIMARY KEY CHECK (code_set ~ '^[a-z0-9][a-z0-9_.-]*$'),
  name text NOT NULL CHECK (btrim(name) <> ''),
  definition text NOT NULL DEFAULT '',
  authority text NOT NULL DEFAULT '',
  steward text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE rdm.code_set IS 'One list of codes that gives values their meaning. Written once, when its first version is drafted, and never changed (meaning that changes is a version''s hint); read by every consumer of reference data.';
COMMENT ON COLUMN rdm.code_set.code_set IS 'The code set''s id: lower case letters, digits, dot, dash, underscore.';
COMMENT ON COLUMN rdm.code_set.name IS 'The code set''s name in plain words.';
COMMENT ON COLUMN rdm.code_set.definition IS 'What the codes stand for.';
COMMENT ON COLUMN rdm.code_set.authority IS 'Who issues the codes: a standard body, a source, or internal.';
COMMENT ON COLUMN rdm.code_set.steward IS 'Who looks after the code set.';
COMMENT ON COLUMN rdm.code_set.created_at IS 'When the code set was first written.';

CREATE TABLE rdm.code_set_version (
  code_set text NOT NULL REFERENCES rdm.code_set,
  version text NOT NULL CHECK (version ~ '^[A-Za-z0-9][A-Za-z0-9_.-]*$'),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','published','retired')),
  valid_from timestamptz,
  valid_to timestamptz CHECK (valid_to IS NULL OR valid_to >= valid_from),
  supersedes text,
  created_by text NOT NULL CHECK (btrim(created_by) <> ''),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidence) = 'object'),
  approved_by text, approved_words text, approved_at timestamptz,
  published_at timestamptz,
  sha256 text CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (code_set, version),
  FOREIGN KEY (code_set, supersedes) REFERENCES rdm.code_set_version (code_set, version)
);
-- One current published version per code set (the spec's btree_gist exclusion
-- constraint, held instead by publishing: it closes the previous version's
-- valid_to at the new one's valid_from, and only one may stay open).
CREATE UNIQUE INDEX one_current_published ON rdm.code_set_version (code_set)
  WHERE status = 'published' AND valid_to IS NULL;
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

CREATE TABLE rdm.code (
  code_set text NOT NULL, version text NOT NULL,
  code text NOT NULL CHECK (code <> ''),
  label text NOT NULL,
  definition text NOT NULL DEFAULT '',
  parent_code text,
  valid_from date, valid_to date CHECK (valid_to IS NULL OR valid_to >= valid_from),
  status text NOT NULL DEFAULT 'valid' CHECK (status IN ('valid','invalid')),
  invalid_reason text CHECK ((status = 'invalid') = (invalid_reason IS NOT NULL)),
  PRIMARY KEY (code_set, version, code),
  FOREIGN KEY (code_set, version) REFERENCES rdm.code_set_version,
  FOREIGN KEY (code_set, version, parent_code) REFERENCES rdm.code DEFERRABLE INITIALLY DEFERRED,
  CHECK (parent_code IS DISTINCT FROM code)
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

CREATE TABLE rdm.code_label (
  code_set text NOT NULL, version text NOT NULL, code text NOT NULL,
  language text NOT NULL DEFAULT 'en' CHECK (language ~ '^[a-z]{2,3}(-[A-Za-z0-9]+)*$'),
  label text NOT NULL CHECK (btrim(label) <> ''),
  kind text NOT NULL CHECK (kind IN ('preferred','synonym')),
  source text NOT NULL DEFAULT '',
  PRIMARY KEY (code_set, version, code, language, label),
  FOREIGN KEY (code_set, version, code) REFERENCES rdm.code
);
CREATE UNIQUE INDEX one_preferred_label ON rdm.code_label (code_set, version, code, language) WHERE kind = 'preferred';
COMMENT ON TABLE rdm.code_label IS 'The names a code goes by, per language: one preferred and any synonyms. Search reads them.';
COMMENT ON COLUMN rdm.code_label.code_set IS 'The code set.';
COMMENT ON COLUMN rdm.code_label.version IS 'The version.';
COMMENT ON COLUMN rdm.code_label.code IS 'The code named.';
COMMENT ON COLUMN rdm.code_label.language IS 'The language of the name (BCP 47).';
COMMENT ON COLUMN rdm.code_label.label IS 'The name.';
COMMENT ON COLUMN rdm.code_label.kind IS 'preferred or synonym.';
COMMENT ON COLUMN rdm.code_label.source IS 'Where the name came from: steward, profiling, an agent draft, a migrated file.';

CREATE TABLE rdm.level (
  code_set text NOT NULL, version text NOT NULL,
  depth integer NOT NULL CHECK (depth >= 1),
  name text NOT NULL CHECK (btrim(name) <> ''),
  definition text NOT NULL DEFAULT '',
  PRIMARY KEY (code_set, version, depth),
  FOREIGN KEY (code_set, version) REFERENCES rdm.code_set_version
);
COMMENT ON TABLE rdm.level IS 'The names stewards give the depths of a version''s hierarchy (depth 1 is the top).';
COMMENT ON COLUMN rdm.level.code_set IS 'The code set.';
COMMENT ON COLUMN rdm.level.version IS 'The version.';
COMMENT ON COLUMN rdm.level.depth IS 'The depth named; 1 is the top.';
COMMENT ON COLUMN rdm.level.name IS 'The level''s name.';
COMMENT ON COLUMN rdm.level.definition IS 'What codes at this level are.';

CREATE TABLE rdm.code_path (
  code_set text NOT NULL, version text NOT NULL, code text NOT NULL,
  path text NOT NULL, label_path text NOT NULL,
  level text, depth integer NOT NULL CHECK (depth >= 1),
  PRIMARY KEY (code_set, version, code),
  FOREIGN KEY (code_set, version, code) REFERENCES rdm.code
);
CREATE INDEX code_path_prefix ON rdm.code_path (code_set, version, path text_pattern_ops);
COMMENT ON TABLE rdm.code_path IS 'Each code''s place in the hierarchy, written once when the version is published. A subtree is path LIKE ''<path>/%''.';
COMMENT ON COLUMN rdm.code_path.code_set IS 'The code set.';
COMMENT ON COLUMN rdm.code_path.version IS 'The version.';
COMMENT ON COLUMN rdm.code_path.code IS 'The code.';
COMMENT ON COLUMN rdm.code_path.path IS 'The codes from the top down to this one, joined by "/" (a "/" or "\" inside a code is escaped with "\").';
COMMENT ON COLUMN rdm.code_path.label_path IS 'The labels from the top down, joined by " > ".';
COMMENT ON COLUMN rdm.code_path.level IS 'The name of the code''s level, when stewards named it.';
COMMENT ON COLUMN rdm.code_path.depth IS 'How deep the code is; 1 is the top.';

CREATE TABLE rdm.crosswalk_row (
  from_set text NOT NULL, from_version text NOT NULL, from_code text NOT NULL,
  to_set text NOT NULL CHECK (to_set ~ '^[a-z0-9][a-z0-9_.-]*$'),
  to_version text NOT NULL CHECK (btrim(to_version) <> ''),
  to_code text NOT NULL CHECK (to_code <> ''),
  match_type text NOT NULL CHECK (match_type IN ('exact','close','broad','narrow')),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidence) = 'object'),
  PRIMARY KEY (from_set, from_version, from_code, to_set, to_version, to_code),
  FOREIGN KEY (from_set, from_version, from_code) REFERENCES rdm.code
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

-- The semantic layer an agent reads before using a code set: where its values
-- live in the data and how to compare them, and hints in plain words. Frozen
-- with the version, like its codes.
CREATE TABLE rdm.code_set_usage (
  code_set text NOT NULL, version text NOT NULL,
  store text NOT NULL CHECK (store IN ('mdm','silver','source','other')),
  object text NOT NULL CHECK (btrim(object) <> ''),
  field text NOT NULL CHECK (btrim(field) <> ''),
  match text NOT NULL DEFAULT 'exact' CHECK (match IN ('exact','upper_trimmed')),
  note text NOT NULL DEFAULT '',
  PRIMARY KEY (code_set, version, store, object, field),
  FOREIGN KEY (code_set, version) REFERENCES rdm.code_set_version
);
COMMENT ON TABLE rdm.code_set_usage IS 'Where values of this code set live in the data, so an agent can find and compare them without guessing.';
COMMENT ON COLUMN rdm.code_set_usage.code_set IS 'The code set.';
COMMENT ON COLUMN rdm.code_set_usage.version IS 'The version.';
COMMENT ON COLUMN rdm.code_set_usage.store IS 'Where the field is: mdm (a mastered field), silver (a table column), source (a feed''s field path), other.';
COMMENT ON COLUMN rdm.code_set_usage.object IS 'The kind, table or source that holds the field.';
COMMENT ON COLUMN rdm.code_set_usage.field IS 'The field, column or path whose values are codes of this set.';
COMMENT ON COLUMN rdm.code_set_usage.match IS 'How a value is compared with a code: exact, or upper_trimmed (upper case, spaces trimmed).';
COMMENT ON COLUMN rdm.code_set_usage.note IS 'Anything an agent must know about this field''s values.';

CREATE TABLE rdm.code_set_hint (
  code_set text NOT NULL, version text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('meaning','use_when','avoid_when','example_question')),
  ordinal integer NOT NULL CHECK (ordinal >= 1),
  text text NOT NULL CHECK (btrim(text) <> ''),
  PRIMARY KEY (code_set, version, kind, ordinal),
  FOREIGN KEY (code_set, version) REFERENCES rdm.code_set_version
);
COMMENT ON TABLE rdm.code_set_hint IS 'Plain-words hints for an agent using this code set: what its codes mean, when to use it, when not to, and questions it answers.';
COMMENT ON COLUMN rdm.code_set_hint.code_set IS 'The code set.';
COMMENT ON COLUMN rdm.code_set_hint.version IS 'The version.';
COMMENT ON COLUMN rdm.code_set_hint.kind IS 'meaning, use_when, avoid_when or example_question.';
COMMENT ON COLUMN rdm.code_set_hint.ordinal IS 'The hint''s place among hints of its kind.';
COMMENT ON COLUMN rdm.code_set_hint.text IS 'The hint.';

-- A version only moves forward. Approval needs the approver's name and exact
-- words; publishing needs the approval, the sha256 and a path for every code.
-- Nothing is deleted.
CREATE FUNCTION rdm.govern_version() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, rdm AS $$
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
CREATE TRIGGER version_governance BEFORE INSERT OR UPDATE OR DELETE ON rdm.code_set_version
  FOR EACH ROW EXECUTE FUNCTION rdm.govern_version();

-- A version's content changes only while it is a draft; its paths are written
-- once, while publishing (status approved), and never changed.
CREATE FUNCTION rdm.guard_content() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, rdm AS $$
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
  SELECT status INTO current_status FROM rdm.code_set_version WHERE code_set = row_set AND version = row_version;
  IF TG_TABLE_NAME = 'code_path' THEN
    IF TG_OP <> 'INSERT' OR current_status IS DISTINCT FROM 'approved' THEN
      RAISE EXCEPTION 'Paths are written once, while an approved version is published'; END IF;
  ELSIF current_status IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'Only a draft version''s content may change'; END IF;
  RETURN coalesce(NEW, OLD);
END;
$$;
CREATE TRIGGER code_guard BEFORE INSERT OR UPDATE OR DELETE ON rdm.code FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();
CREATE TRIGGER code_label_guard BEFORE INSERT OR UPDATE OR DELETE ON rdm.code_label FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();
CREATE TRIGGER level_guard BEFORE INSERT OR UPDATE OR DELETE ON rdm.level FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();
CREATE TRIGGER code_path_guard BEFORE INSERT OR UPDATE OR DELETE ON rdm.code_path FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();
CREATE TRIGGER crosswalk_guard BEFORE INSERT OR UPDATE OR DELETE ON rdm.crosswalk_row FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();
CREATE TRIGGER usage_guard BEFORE INSERT OR UPDATE OR DELETE ON rdm.code_set_usage FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();
CREATE TRIGGER hint_guard BEFORE INSERT OR UPDATE OR DELETE ON rdm.code_set_hint FOR EACH ROW EXECUTE FUNCTION rdm.guard_content();
CREATE TRIGGER no_truncate_version BEFORE TRUNCATE ON rdm.code_set_version FOR EACH STATEMENT EXECUTE FUNCTION rdm.govern_version();

REVOKE ALL ON ALL TABLES IN SCHEMA rdm FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA rdm FROM PUBLIC;
