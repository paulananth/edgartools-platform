-- A link names every kind its master may be (`kinds`), and finds that master by a Dataset Contract's record key
-- (`source_code`) or by an identifier the master holds (`identifier`), with the row's exchange column (`venue`) when
-- several masters hold the value. The context shows each link as its spec states it.
CREATE OR REPLACE VIEW silver.table_context AS
 SELECT t.table_name,
    t.spec ->> 'grain' AS grain,
    t.spec -> 'key' AS key,
    coalesce((SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                'columns', l -> 'columns', 'kinds', l -> 'kinds', 'source_code', l ->> 'source_code',
                'identifier', l ->> 'identifier', 'venue', l ->> 'venue', 'source_key', l ->> 'source_key',
                'inclusion', l -> 'inclusion')))
                FROM jsonb_array_elements(coalesce(t.spec -> 'links', '[]'::jsonb)) l), '[]'::jsonb) AS links,
    t.spec -> 'time' AS time_columns,
    t.spec ->> 'load_mode' AS load_mode,
    coalesce(t.spec ->> 'definition', t.spec ->> 'why') AS definition,
    'silver.table_spec/' || t.table_name || '@' || t.sha256 AS spec_ref,
    t.registered_at
   FROM silver.table_spec t;

COMMENT ON COLUMN silver.table_context.links IS 'Each pointer to a master: the source key column, the kinds its master may be, and how the master is found (a Dataset Contract''s record key, or an identifier the master holds, with the row''s exchange column when several hold it), and the share of source keys profiling found among the master''s keys (inclusion).';
