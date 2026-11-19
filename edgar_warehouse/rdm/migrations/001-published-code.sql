-- The codes of every published version as a table, for the managed mirror, which carries tables and not views.
-- Written once, by rdm.write_published_codes, when a version is published; a draft never reaches it, and a
-- retired version keeps its rows. It holds what the version fixes when published: what changes later (the
-- version's valid_to and status) stays on rdm.code_set_version, and the latest valid_from of a code set is its
-- current version.

CREATE TABLE rdm.published_code (
    code_set text NOT NULL,
    code_set_name text NOT NULL,
    version text NOT NULL,
    code text NOT NULL,
    label text NOT NULL,
    definition text NOT NULL,
    synonyms jsonb NOT NULL,
    path text NOT NULL,
    label_path text NOT NULL,
    level text,
    depth bigint NOT NULL,
    parent_code text,
    crosswalk jsonb NOT NULL,
    sha256 text NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    code_status text NOT NULL,
    code_valid_from date,
    code_valid_to date,
    invalid_reason text,
    approved_by text NOT NULL,
    approved_at timestamp with time zone NOT NULL,
    published_at timestamp with time zone NOT NULL,
    value text,
    unit text,
    properties jsonb,
    PRIMARY KEY (code_set, version, code),
    FOREIGN KEY (code_set, version, code) REFERENCES rdm.code (code_set, version, code),
    CONSTRAINT published_code_depth_check CHECK (depth >= 1)
);

-- One writer: the function reads rdm.code_context, the published-only read form, so the table and the view agree.
-- It runs with its owner's rights, so the runtime login needs no right to write the table itself.
CREATE FUNCTION rdm.write_published_codes(wanted_set text, wanted_version text) RETURNS bigint
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'rdm'
    AS $$
  WITH written AS (
    INSERT INTO rdm.published_code
    SELECT code_set, code_set_name, version, code, label, definition, synonyms, path, label_path, level, depth,
           parent_code, crosswalk, sha256, valid_from, code_status, code_valid_from, code_valid_to, invalid_reason,
           approved_by, approved_at, published_at, value, unit, properties
      FROM rdm.code_context WHERE code_set = wanted_set AND version = wanted_version
    RETURNING 1)
  SELECT count(*) FROM written;
$$;

-- Every published or retired version already in the store.
SELECT rdm.write_published_codes(code_set, version) FROM rdm.code_set_version WHERE status IN ('published', 'retired');

CREATE FUNCTION rdm.guard_published() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'rdm'
    AS $$
BEGIN
  IF TG_OP <> 'INSERT' OR (SELECT status FROM rdm.code_set_version
                            WHERE code_set = NEW.code_set AND version = NEW.version FOR SHARE) IS DISTINCT FROM 'published' THEN
    RAISE EXCEPTION 'Published codes are written once, when a version is published'; END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER published_code_guard BEFORE INSERT OR DELETE OR UPDATE ON rdm.published_code
    FOR EACH ROW EXECUTE FUNCTION rdm.guard_published();

COMMENT ON TABLE rdm.published_code IS 'One row per code of every version ever published (current, superseded or retired), written once when the version is published. The published-only form of rdm.code_context, for the Snowflake mirror.';
COMMENT ON COLUMN rdm.published_code.code_set IS 'The code set.';
COMMENT ON COLUMN rdm.published_code.code_set_name IS 'The code set''s name in plain words.';
COMMENT ON COLUMN rdm.published_code.version IS 'The published version the code belongs to.';
COMMENT ON COLUMN rdm.published_code.code IS 'The code as values carry it.';
COMMENT ON COLUMN rdm.published_code.label IS 'What the code stands for, in a few words (its preferred label).';
COMMENT ON COLUMN rdm.published_code.definition IS 'The code''s definition, in words.';
COMMENT ON COLUMN rdm.published_code.synonyms IS 'Other labels the code goes by, as a JSON list.';
COMMENT ON COLUMN rdm.published_code.path IS 'The codes from the top down to this one, joined by "/".';
COMMENT ON COLUMN rdm.published_code.label_path IS 'The labels from the top down, joined by " > ".';
COMMENT ON COLUMN rdm.published_code.level IS 'The name of the code''s level, when stewards named it.';
COMMENT ON COLUMN rdm.published_code.depth IS 'How deep the code is; 1 is the top.';
COMMENT ON COLUMN rdm.published_code.parent_code IS 'The code above this one; empty at the top.';
COMMENT ON COLUMN rdm.published_code.crosswalk IS 'The codes of other code sets this one maps to and how closely, as a JSON list.';
COMMENT ON COLUMN rdm.published_code.sha256 IS 'The version''s pin: the hash of its content when published.';
COMMENT ON COLUMN rdm.published_code.valid_from IS 'When the version became current.';
COMMENT ON COLUMN rdm.published_code.code_status IS 'Whether the code is valid or invalid.';
COMMENT ON COLUMN rdm.published_code.code_valid_from IS 'The date the code takes effect, when the code set states one.';
COMMENT ON COLUMN rdm.published_code.code_valid_to IS 'The date the code stops being valid, when the code set states one.';
COMMENT ON COLUMN rdm.published_code.invalid_reason IS 'Why an invalid code is invalid.';
COMMENT ON COLUMN rdm.published_code.approved_by IS 'Who approved the version.';
COMMENT ON COLUMN rdm.published_code.approved_at IS 'When the version was approved.';
COMMENT ON COLUMN rdm.published_code.published_at IS 'When the version was published.';
COMMENT ON COLUMN rdm.published_code.value IS 'The code''s number, for a code that stands for one (a rate).';
COMMENT ON COLUMN rdm.published_code.unit IS 'The unit of the value.';
COMMENT ON COLUMN rdm.published_code.properties IS 'The code''s further facts, as a JSON object.';
