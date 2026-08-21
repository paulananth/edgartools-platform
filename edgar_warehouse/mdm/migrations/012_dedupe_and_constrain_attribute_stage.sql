-- mdm_entity_attribute_stage was discovered live in production carrying
-- 10,713-14,785+ duplicate rows for one heavily-refiled security entity.
-- stage_candidate() (edgar_warehouse/mdm/survivorship.py) previously
-- INSERTed unconditionally with no natural-key dedup, so every restart of
-- a resolver loop before its skip-if-unchanged fast path existed (or any
-- future resolver that lacks one) re-staged every already-processed row
-- again -- mdm_entity_attribute_stage has no pruning anywhere in this
-- codebase, so the duplicates were permanent and every future
-- run_survivorship_for_entity() call for the entity had to read the whole
-- bloated history.
--
-- Collapse each (entity_id, source_system, source_id, field_name) group
-- down to its most-recently-loaded row (ties broken by stage_id -- an
-- arbitrary but deterministic tie-break among rows loaded in the same
-- instant), then add a unique index so this cannot silently reoccur --
-- the same natural key mdm_source_ref already uses as its primary key for
-- the same (entity_id, source_system, source_id) grouping. Recency is the
-- right tie-break even when duplicate rows genuinely differ in
-- field_value (not just pure restart copies): it's what stage_candidate()'s
-- new upsert would produce anyway going forward.

DELETE FROM mdm_entity_attribute_stage
WHERE stage_id IN (
    SELECT stage_id FROM (
        SELECT
            stage_id,
            ROW_NUMBER() OVER (
                PARTITION BY entity_id, source_system, source_id, field_name
                ORDER BY loaded_at DESC NULLS LAST, stage_id DESC
            ) AS rn
        FROM mdm_entity_attribute_stage
    ) ranked
    WHERE rn > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_attr_stage_entity_source_field
    ON mdm_entity_attribute_stage (entity_id, source_system, source_id, field_name);
