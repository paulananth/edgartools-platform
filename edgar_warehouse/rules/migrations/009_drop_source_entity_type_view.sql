-- The entity type listing is read in code from the saved source versions (`RulesDatabase.entity_types`), so it is the
-- same on every database (operator, 2026-11-10: nothing may be database specific). The view of migration 008 was
-- PostgreSQL only and is dropped.
DROP VIEW IF EXISTS rules.source_entity_type;
