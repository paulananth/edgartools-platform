-- Silver for the trials and the proof (profiling plan decision 36, ticket 06):
-- a `silver` schema on PostgreSQL 16. Each silver table is created from an
-- approved silver table spec (docs/specs/profiling/findings.md section 6) when
-- the schema owner registers it; the registry keeps the spec it was made from.

CREATE SCHEMA silver;

CREATE TABLE silver.table_spec (
    table_name text PRIMARY KEY,
    spec jsonb NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    registered_at timestamp with time zone NOT NULL DEFAULT now(),
    CHECK (spec ->> 'table' = table_name)
);

COMMENT ON TABLE silver.table_spec IS
    'Every silver table and the silver table spec it was created from. A table keeps its spec: a changed spec is registered as a new table.';
COMMENT ON COLUMN silver.table_spec.table_name IS 'The silver table, in the silver schema.';
COMMENT ON COLUMN silver.table_spec.spec IS 'The approved silver table spec: grain, columns, key, links to masters, time columns, partition, load mode and why.';
COMMENT ON COLUMN silver.table_spec.sha256 IS 'The sha256 of the spec in canonical JSON: what a load checks it writes against.';
COMMENT ON COLUMN silver.table_spec.registered_at IS 'When the schema owner created the table from the spec.';

CREATE VIEW silver.table_context AS
 SELECT t.table_name,
    t.spec ->> 'grain' AS grain,
    t.spec -> 'key' AS key,
    coalesce((SELECT jsonb_agg(jsonb_build_object(
                'columns', l -> 'columns', 'kind', l ->> 'kind', 'source_code', l ->> 'source_code',
                'source_key', l ->> 'source_key', 'mdm_id_column', l ->> 'mdm_id_column',
                'inclusion', l -> 'inclusion'))
                FROM jsonb_array_elements(coalesce(t.spec -> 'links', '[]'::jsonb)) l), '[]'::jsonb) AS links,
    t.spec -> 'time' AS time_columns,
    t.spec ->> 'load_mode' AS load_mode,
    coalesce(t.spec ->> 'definition', t.spec ->> 'why') AS definition,
    'silver.table_spec/' || t.table_name || '@' || t.sha256 AS spec_ref,
    t.registered_at
   FROM silver.table_spec t;

COMMENT ON VIEW silver.table_context IS
    'What each silver table holds, for agents: one row per table, read from the spec it was created from.';
COMMENT ON COLUMN silver.table_context.table_name IS 'The silver table, in the silver schema.';
COMMENT ON COLUMN silver.table_context.grain IS 'What one row is.';
COMMENT ON COLUMN silver.table_context.key IS 'The columns that identify a row.';
COMMENT ON COLUMN silver.table_context.links IS 'Each pointer to a master: the source key column, the master kind and Dataset Contract, the column holding the master''s MDM id (empty until the entity is mastered), and the share of source keys profiling found among the master''s keys (inclusion).';
COMMENT ON COLUMN silver.table_context.time_columns IS 'The as-of, as-at and event time columns.';
COMMENT ON COLUMN silver.table_context.load_mode IS 'append (rows only grow), upsert (rows change by key) or snapshot (the table is the latest delivery).';
COMMENT ON COLUMN silver.table_context.definition IS 'The table in plain words: its definition, or the spec''s why.';
COMMENT ON COLUMN silver.table_context.spec_ref IS 'The registry row and spec digest this answer comes from.';
COMMENT ON COLUMN silver.table_context.registered_at IS 'When the table was created from its spec.';
