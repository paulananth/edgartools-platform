-- Replace the historical copied kind list with owner-managed vocabulary.
-- Seed every historical permitted kind before replacing its CHECK constraint.
CREATE TABLE mdm.master_kind (
    kind text PRIMARY KEY,
    enabled boolean NOT NULL
);
INSERT INTO mdm.master_kind(kind,enabled)
SELECT m[1],true
FROM pg_constraint c,
LATERAL regexp_matches(
    substring(pg_get_constraintdef(c.oid) from 'kind[^=]*= ANY \(ARRAY\[(.*?)\]\)'),
    '''([a-z_]+)''', 'g') m
WHERE c.conrelid='mdm.master_entity'::regclass
  AND c.conname='master_entity_kind_check';
ALTER TABLE mdm.master_entity DROP CONSTRAINT master_entity_kind_check;
ALTER TABLE mdm.master_entity ADD CONSTRAINT master_entity_kind_fkey
    FOREIGN KEY(kind) REFERENCES mdm.master_kind(kind);

CREATE FUNCTION mdm.require_configured_kind() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $kind$
BEGIN
    PERFORM 1 FROM mdm.master_kind WHERE kind=NEW.kind AND enabled FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Master kind is not enabled in the installed configuration';
    END IF;
    RETURN NEW;
END;
$kind$;
CREATE TRIGGER master_entity_configured_kind
BEFORE INSERT OR UPDATE OF kind ON mdm.master_entity
FOR EACH ROW EXECUTE FUNCTION mdm.require_configured_kind();
REVOKE ALL ON mdm.master_kind FROM PUBLIC;
REVOKE ALL ON FUNCTION mdm.require_configured_kind() FROM PUBLIC;
COMMENT ON TABLE mdm.master_kind IS
    'Owner-installed configured master kinds; disabled historical kinds retain their identities and read views.';
