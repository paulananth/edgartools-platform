-- A master's detail rows, every one kept (ticket 120; operator, 2026-10-20:
-- "Maybe create a security detail table and keep it in the mdm", then "Detail
-- rows set in config (Recommended)" and "End it, keep history (Recommended)").
--
-- A Dataset Contract may state detail lists (a Security's listings, keyed by
-- FIGI); a master's body carries them under `details`. One table for every
-- kind and list: one row per master, list and key per change. A trigger on
-- mdm.current_record writes it, as for relationships (010): a row the body no
-- longer carries is ended; its history stays. No batch before this migration
-- carries details, so there is nothing to back-fill.

CREATE TABLE mdm.detail_version (
    entity_id text NOT NULL,
    detail text NOT NULL,
    key text NOT NULL,
    from_generation bigint NOT NULL,
    to_generation bigint,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    batch_id text NOT NULL REFERENCES mdm.batch(batch_id),
    body jsonb NOT NULL,
    PRIMARY KEY (entity_id, detail, key, from_generation),
    CONSTRAINT detail_version_open_has_no_end CHECK (((valid_to IS NULL) = (to_generation IS NULL))),
    CONSTRAINT detail_version_valid_period CHECK (((valid_to IS NULL) OR (valid_from < valid_to))),
    CONSTRAINT detail_version_generation_period CHECK (((to_generation IS NULL) OR (from_generation < to_generation)))
);

CREATE UNIQUE INDEX detail_version_open ON mdm.detail_version (entity_id, detail, key) WHERE to_generation IS NULL;
-- A lookup by a row's key (a FIGI to its Security) across every master.
CREATE INDEX detail_version_key ON mdm.detail_version (detail, key) WHERE to_generation IS NULL;

COMMENT ON TABLE mdm.detail_version IS
    'Every recorded state of every detail row of every master (a Security''s listings), one row per master, list and key per change. The row whose from_generation <= g < to_generation (to_generation empty: still current) is what MDM had recorded at generation g. mdm.current_record''s entity body holds the current rows under details.';
COMMENT ON COLUMN mdm.detail_version.entity_id IS 'The master, as in mdm.current_record.object_id.';
COMMENT ON COLUMN mdm.detail_version.detail IS 'The list, as the Dataset Contract names it (listings).';
COMMENT ON COLUMN mdm.detail_version.key IS 'The row''s key within its list (a listing''s FIGI).';
COMMENT ON COLUMN mdm.detail_version.from_generation IS 'The generation of the batch that recorded this state.';
COMMENT ON COLUMN mdm.detail_version.to_generation IS 'The generation of the batch that changed or ended it; empty while current.';
COMMENT ON COLUMN mdm.detail_version.valid_from IS 'Recording time this state started: its batch''s created_at.';
COMMENT ON COLUMN mdm.detail_version.valid_to IS 'Recording time it was changed or ended; empty while current.';
COMMENT ON COLUMN mdm.detail_version.batch_id IS 'The batch that recorded this state (mdm.batch).';
COMMENT ON COLUMN mdm.detail_version.body IS 'The row as recorded: its fields and the sources that gave its key.';

-- One master's detail rows as committed by one batch: each row as for a
-- relationship (unchanged: nothing; the same generation: replaced; else the
-- open row closed and a new one opened), and each open row the body no longer
-- carries ended.
CREATE FUNCTION mdm.record_detail_versions(entity text, projected jsonb, source_batch text) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE
    generation_number bigint;
    recorded_at timestamptz;
    starts_at timestamptz;
    item record;
    previous mdm.detail_version%ROWTYPE;
BEGIN
    SELECT generation, created_at INTO generation_number, recorded_at FROM mdm.batch WHERE batch_id = source_batch;
    IF generation_number IS NULL THEN RAISE EXCEPTION 'Detail projection has no committed batch'; END IF;
    FOR item IN
        SELECT d.key AS detail, r.value ->> 'key' AS key, r.value AS body
          FROM jsonb_each(coalesce(projected -> 'details', '{}'::jsonb)) d,
               jsonb_array_elements(d.value) r
    LOOP
        SELECT * INTO previous FROM mdm.detail_version
          WHERE entity_id = entity AND detail = item.detail AND key = item.key AND to_generation IS NULL FOR UPDATE;
        IF previous.entity_id IS NOT NULL AND previous.body = item.body THEN CONTINUE; END IF;
        IF previous.entity_id IS NOT NULL AND previous.from_generation = generation_number THEN
            UPDATE mdm.detail_version SET body = item.body, batch_id = source_batch
             WHERE entity_id = entity AND detail = item.detail AND key = item.key AND from_generation = generation_number;
            CONTINUE;
        END IF;
        IF previous.entity_id IS NOT NULL AND previous.from_generation > generation_number THEN
            RAISE EXCEPTION 'Detail % % of % recorded out of generation order', item.detail, item.key, entity;
        END IF;
        starts_at := greatest(recorded_at, coalesce(previous.valid_from + interval '1 microsecond', recorded_at));
        IF previous.entity_id IS NOT NULL THEN
            UPDATE mdm.detail_version SET valid_to = starts_at, to_generation = generation_number
             WHERE entity_id = entity AND detail = item.detail AND key = item.key AND to_generation IS NULL;
        END IF;
        INSERT INTO mdm.detail_version (entity_id, detail, key, from_generation, valid_from, batch_id, body)
        VALUES (entity, item.detail, item.key, generation_number, starts_at, source_batch, item.body);
    END LOOP;
    -- A row the body no longer carries is ended, its history kept; one opened by
    -- this same generation is removed, since that generation never held it.
    DELETE FROM mdm.detail_version v
     WHERE v.entity_id = entity AND v.to_generation IS NULL AND v.from_generation = generation_number
       AND NOT coalesce(projected -> 'details' -> v.detail, '[]'::jsonb) @> jsonb_build_array(jsonb_build_object('key', v.key));
    UPDATE mdm.detail_version v
       SET valid_to = greatest(recorded_at, v.valid_from + interval '1 microsecond'), to_generation = generation_number
     WHERE v.entity_id = entity AND v.to_generation IS NULL AND v.from_generation < generation_number
       AND NOT coalesce(projected -> 'details' -> v.detail, '[]'::jsonb) @> jsonb_build_array(jsonb_build_object('key', v.key));
END;
$$;

COMMENT ON FUNCTION mdm.record_detail_versions(text, jsonb, text) IS
    'Record one master''s detail rows committed by one batch in mdm.detail_version: each row nothing when unchanged, replaced within its generation, else closed and reopened; each open row the body no longer carries ended.';

CREATE FUNCTION mdm.keep_detail_versions() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
BEGIN
    PERFORM mdm.record_detail_versions(NEW.object_id, NEW.body, NEW.batch_id);
    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION mdm.keep_detail_versions() IS
    'Trigger on mdm.current_record: every master row that carries details, or carried them before, is recorded in mdm.detail_version.';

-- Two triggers: a trigger on INSERT cannot name OLD in its condition.
CREATE TRIGGER keep_detail_versions_insert AFTER INSERT ON mdm.current_record
    FOR EACH ROW WHEN (NEW.object_type = 'entity' AND NEW.body ? 'details')
    EXECUTE FUNCTION mdm.keep_detail_versions();
CREATE TRIGGER keep_detail_versions_update AFTER UPDATE ON mdm.current_record
    FOR EACH ROW WHEN (NEW.object_type = 'entity' AND (NEW.body ? 'details' OR OLD.body ? 'details'))
    EXECUTE FUNCTION mdm.keep_detail_versions();

-- Readers of mdm.current_record read this table too; copy only SELECT.
DO $$
DECLARE reader text;
BEGIN
    FOR reader IN
        SELECT DISTINCT pg_get_userbyid(a.grantee)
        FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
        WHERE c.oid='mdm.current_record'::regclass AND a.privilege_type='SELECT' AND a.grantee<>0
    LOOP
        EXECUTE format('GRANT SELECT ON mdm.detail_version TO %I',reader);
    END LOOP;
END;
$$;
