-- A content edit holds its version against approval until that edit commits.
-- Without the row lock, an approval can freeze an earlier observation while a
-- previously admitted content UPDATE commits afterward.
CREATE OR REPLACE FUNCTION rdm.guard_content() RETURNS trigger
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
