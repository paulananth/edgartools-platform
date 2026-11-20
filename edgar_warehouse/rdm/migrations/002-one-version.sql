-- A code set keeps exactly one version. Publishing a version deletes the one it replaces, and retiring deletes the
-- code set's version, in the same transaction: the rows of every table leave with the version. History is git
-- (rules/reference/published/). A delete is allowed only for a version whose valid_to is set (replaced or retired);
-- every other delete, and every update of a published version, stays refused.

-- supersedes names the version a new one replaced; that version is deleted, so it is a recorded name, not a key.
ALTER TABLE rdm.code_set_version DROP CONSTRAINT code_set_version_code_set_supersedes_fkey;

CREATE OR REPLACE FUNCTION rdm.govern_version() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'rdm'
    AS $$
DECLARE rank_old integer; rank_new integer;
BEGIN
  IF TG_OP = 'TRUNCATE' THEN RAISE EXCEPTION 'Reference data history is retained'; END IF;
  -- A code set keeps one version: only a version that was replaced or retired (its valid_to is set) is deleted.
  IF TG_OP = 'DELETE' THEN
    IF OLD.valid_to IS NULL THEN RAISE EXCEPTION 'Only a replaced or retired version is deleted'; END IF;
    RETURN OLD;
  END IF;
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

CREATE OR REPLACE FUNCTION rdm.guard_content() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'rdm'
    AS $$
DECLARE row_set text; row_version text; current_status text; closed boolean;
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
  SELECT status, valid_to IS NOT NULL INTO current_status, closed FROM rdm.code_set_version
    WHERE code_set = row_set AND version = row_version FOR SHARE;
  IF TG_OP = 'DELETE' AND closed THEN RETURN OLD; END IF;  -- the content of a replaced or retired version leaves with it
  IF TG_TABLE_NAME = 'code_path' THEN
    IF TG_OP <> 'INSERT' OR current_status IS DISTINCT FROM 'approved' THEN
      RAISE EXCEPTION 'Paths are written once, while an approved version is published'; END IF;
  ELSIF current_status IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'Only a draft version''s content may change'; END IF;
  RETURN coalesce(NEW, OLD);
END;
$$;

CREATE OR REPLACE FUNCTION rdm.guard_published() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'rdm'
    AS $$
BEGIN
  IF TG_OP = 'DELETE' AND (SELECT valid_to IS NOT NULL FROM rdm.code_set_version
                            WHERE code_set = OLD.code_set AND version = OLD.version FOR SHARE) THEN RETURN OLD; END IF;
  IF TG_OP <> 'INSERT' OR (SELECT status FROM rdm.code_set_version
                            WHERE code_set = NEW.code_set AND version = NEW.version FOR SHARE) IS DISTINCT FROM 'published' THEN
    RAISE EXCEPTION 'Published codes are written once, when a version is published'; END IF;
  RETURN NEW;
END;
$$;

-- One writer for the deletes too: the runtime has no right to write the mirror's table itself.
CREATE FUNCTION rdm.delete_published_codes(wanted_set text, wanted_version text) RETURNS bigint
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'rdm'
    AS $$
  WITH removed AS (
    DELETE FROM rdm.published_code WHERE code_set = wanted_set AND version = wanted_version RETURNING 1)
  SELECT count(*) FROM removed;
$$;

COMMENT ON TABLE rdm.published_code IS 'One row per code of each code set''s one published version, written when the version is published and deleted with it when a later version replaces it or the code set is retired. The published-only form of rdm.code_context, for the Snowflake mirror.';
COMMENT ON VIEW rdm.code_context IS 'One row per code of the published version of each code set (a code set keeps one version), for agents: what the code means, where it sits in the hierarchy, and the version''s pin. The current version is the one whose valid_to is empty and version_status published.';
COMMENT ON COLUMN rdm.code_set_version.supersedes IS 'The version this one replaced; a recorded name, since the replaced version is deleted when this one is published.';
