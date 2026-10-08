-- Relationships at a past recording time (profiling ticket 05b; operator,
-- 2026-10-08: "Approve (Recommended)").
--
-- mdm.current_record holds each relationship as it stands now. Every change is
-- also kept here, one row per relationship per change, as mdm.company keeps
-- Company versions: the version open at a generation is what MDM had recorded
-- by then. A trigger on mdm.current_record writes it, so the batch writer is
-- unchanged; history committed before this migration is back-filled from the
-- stored batches (mdm.batch.effects), in generation order.
CREATE TABLE mdm.relationship_version (
    relationship_id text NOT NULL,
    from_generation bigint NOT NULL,
    to_generation bigint,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    batch_id text NOT NULL REFERENCES mdm.batch(batch_id),
    source_id text,
    target_id text,
    type text,
    body jsonb NOT NULL,
    PRIMARY KEY (relationship_id, from_generation),
    CONSTRAINT relationship_version_open_has_no_end CHECK (((valid_to IS NULL) = (to_generation IS NULL))),
    CONSTRAINT relationship_version_valid_period CHECK (((valid_to IS NULL) OR (valid_from < valid_to))),
    CONSTRAINT relationship_version_generation_period CHECK (((to_generation IS NULL) OR (from_generation < to_generation)))
);

CREATE UNIQUE INDEX relationship_version_open ON mdm.relationship_version (relationship_id) WHERE to_generation IS NULL;
CREATE INDEX relationship_version_source ON mdm.relationship_version (source_id, from_generation);
CREATE INDEX relationship_version_target ON mdm.relationship_version (target_id, from_generation);

COMMENT ON TABLE mdm.relationship_version IS
    'Every recorded state of every relationship, one row per relationship per change. The row whose from_generation <= g < to_generation (to_generation empty: still current) is what MDM had recorded at generation g; a batch''s generation and created_at say when. mdm.current_record holds the latest; this table answers "what did MDM have by then" (--as-at). Business time is in the body''s periods.';
COMMENT ON COLUMN mdm.relationship_version.relationship_id IS 'The relationship''s id, as in mdm.current_record.object_id.';
COMMENT ON COLUMN mdm.relationship_version.from_generation IS 'The generation of the batch that recorded this state.';
COMMENT ON COLUMN mdm.relationship_version.to_generation IS 'The generation of the batch that replaced it; empty while it is the current state.';
COMMENT ON COLUMN mdm.relationship_version.valid_from IS 'Recording time this state started: its batch''s created_at.';
COMMENT ON COLUMN mdm.relationship_version.valid_to IS 'Recording time it was replaced; empty while current.';
COMMENT ON COLUMN mdm.relationship_version.source_id IS 'The entity the link starts from (body source_id), indexed for a walk at a past generation.';
COMMENT ON COLUMN mdm.relationship_version.target_id IS 'The entity the link points to (body target_id), indexed likewise.';
COMMENT ON COLUMN mdm.relationship_version.type IS 'The relationship type (body type).';
COMMENT ON COLUMN mdm.relationship_version.body IS 'The relationship as recorded: periods, evidence, retired flag and the rest.';

-- One relationship state recorded by one batch. An unchanged body writes
-- nothing; a second change in the same generation replaces that generation's
-- row; otherwise the open row is closed and a new one opened.
CREATE FUNCTION mdm.record_relationship_version(relationship text, projected jsonb, source_batch text) RETURNS void
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
DECLARE
    previous mdm.relationship_version%ROWTYPE;
    generation_number bigint;
    recorded_at timestamptz;
    starts_at timestamptz;
BEGIN
    SELECT generation, created_at INTO generation_number, recorded_at FROM mdm.batch WHERE batch_id = source_batch;
    IF generation_number IS NULL THEN RAISE EXCEPTION 'Relationship projection has no committed batch'; END IF;
    SELECT * INTO previous FROM mdm.relationship_version
      WHERE relationship_id = relationship AND to_generation IS NULL FOR UPDATE;
    IF previous.relationship_id IS NOT NULL AND previous.body = projected THEN RETURN; END IF;
    IF previous.relationship_id IS NOT NULL AND previous.from_generation = generation_number THEN
        UPDATE mdm.relationship_version
           SET body = projected, batch_id = source_batch, source_id = projected ->> 'source_id',
               target_id = projected ->> 'target_id', type = projected ->> 'type'
         WHERE relationship_id = relationship AND from_generation = generation_number;
        RETURN;
    END IF;
    IF previous.relationship_id IS NOT NULL AND previous.from_generation > generation_number THEN
        RAISE EXCEPTION 'Relationship % recorded out of generation order', relationship;
    END IF;
    starts_at := greatest(recorded_at, coalesce(previous.valid_from + interval '1 microsecond', recorded_at));
    IF previous.relationship_id IS NOT NULL THEN
        UPDATE mdm.relationship_version SET valid_to = starts_at, to_generation = generation_number
         WHERE relationship_id = relationship AND to_generation IS NULL;
    END IF;
    INSERT INTO mdm.relationship_version (relationship_id, from_generation, valid_from, batch_id,
                                          source_id, target_id, type, body)
    VALUES (relationship, generation_number, starts_at, source_batch,
            projected ->> 'source_id', projected ->> 'target_id', projected ->> 'type', projected);
END;
$$;

-- History before this migration: every relationship projection of every
-- stored batch, in generation order.
DO $$
DECLARE
    b record;
    item jsonb;
BEGIN
    FOR b IN SELECT batch_id, effects FROM mdm.batch ORDER BY generation LOOP
        FOR item IN SELECT value FROM jsonb_array_elements(coalesce(b.effects -> 'projections', '[]'::jsonb)) LOOP
            IF item ->> 'object_type' = 'relationship' THEN
                PERFORM mdm.record_relationship_version(item ->> 'object_id', item -> 'body', b.batch_id);
            END IF;
        END LOOP;
    END LOOP;
    -- The current state must be the open version; a relationship the batches do
    -- not show (none is expected) stops the migration rather than lose it.
    IF EXISTS (
        SELECT 1 FROM mdm.current_record r
          LEFT JOIN mdm.relationship_version v ON v.relationship_id = r.object_id AND v.to_generation IS NULL
         WHERE r.object_type = 'relationship' AND v.body IS DISTINCT FROM r.body) THEN
        RAISE EXCEPTION 'Relationship history from the stored batches does not end at the current state';
    END IF;
END;
$$;

CREATE FUNCTION mdm.keep_relationship_version() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'mdm'
    AS $$
BEGIN
    PERFORM mdm.record_relationship_version(NEW.object_id, NEW.body, NEW.batch_id);
    RETURN NULL;
END;
$$;

CREATE TRIGGER keep_relationship_version AFTER INSERT OR UPDATE ON mdm.current_record
    FOR EACH ROW WHEN (NEW.object_type = 'relationship') EXECUTE FUNCTION mdm.keep_relationship_version();
