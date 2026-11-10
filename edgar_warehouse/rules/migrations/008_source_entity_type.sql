-- Mastering step 0: where each registered source's records get their entity type (operator, 2026-11-09: "stored in a
-- table and a YAML", then "Step 0 table. Rules db"). A view over the saved source versions, so it holds no second
-- copy that could drift from the Dataset Contracts: one row per source version and dataset code, with the origin
-- (`fixed`: the contract names one kind; `rule`: a classification rule decides; `source_field`: the source's own
-- category field) and the types it can give.
CREATE VIEW rules.source_entity_type AS
SELECT v.name AS source, v.version, v.status, c.key AS dataset_code,
       CASE WHEN a ? 'kind' THEN 'fixed' WHEN a ? 'classification' THEN 'rule' ELSE 'source_field' END AS origin,
       CASE WHEN a ? 'kind' THEN a->>'kind'
            WHEN a ? 'classification' THEN a->'classification'->>'kind'
            ELSE (SELECT string_agg(DISTINCT t.value, ',' ORDER BY t.value) FROM jsonb_each_text(a->'kind_values') t) END AS entity_types,
       a->'classification'->>'rule_id' AS rule_id
FROM rules.rule_version v
CROSS JOIN LATERAL jsonb_each(v.body::jsonb->'dataset_contracts') c
CROSS JOIN LATERAL (SELECT c.value->'contract'->'adapter' AS a) x
WHERE v.kind='source';
