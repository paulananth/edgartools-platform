-- Add mdm_entity_id to the 6 silver-landing tables provisioned by
-- 11_silver_landing_schema.sql before the mdm-ahead-of-silver map's Phase A
-- (commit 6980f0f0) added the column to that generator's output.
--
-- Not covered by re-running 11_silver_landing_schema.sql: that file is a
-- CREATE TABLE IF NOT EXISTS snapshot generated from silver_store.py's
-- fully-migrated DuckDB schema (infra/scripts/generate_silver_landing_ddl.py)
-- -- re-applying it against tables that already exist (as prod's do, created
-- 2026-08-13 per Ticket 07) is a silent no-op; it does not evolve existing
-- tables the way silver_store.py's own DuckDB-side
-- `_ensure_mdm_entity_id_columns` migration does locally. This file is the
-- Snowflake-side equivalent of that local migration, following the existing
-- hand-written ALTER TABLE ... ADD COLUMN IF NOT EXISTS precedent in
-- 01_source_stage.sql and 07_mdm_export_targets.sql.
--
-- Idempotent -- ADD COLUMN IF NOT EXISTS -- safe to re-run.
-- Run once per environment:
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/14_silver_landing_mdm_entity_id.sql

USE DATABASE EDGARTOOLS_PROD;
USE SCHEMA EDGARTOOLS_SILVER_LANDING;
USE ROLE ACCOUNTADMIN;

ALTER TABLE sec_company ADD COLUMN IF NOT EXISTS mdm_entity_id TEXT;
ALTER TABLE sec_adv_filing ADD COLUMN IF NOT EXISTS mdm_entity_id TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS mdm_entity_id TEXT;
ALTER TABLE sec_adv_private_fund ADD COLUMN IF NOT EXISTS mdm_entity_id TEXT;
ALTER TABLE sec_ownership_non_derivative_txn ADD COLUMN IF NOT EXISTS mdm_entity_id TEXT;
ALTER TABLE sec_ownership_derivative_txn ADD COLUMN IF NOT EXISTS mdm_entity_id TEXT;
