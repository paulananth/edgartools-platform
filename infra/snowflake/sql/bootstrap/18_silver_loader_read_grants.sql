-- Grants EDGARTOOLS_<ENV>_LOADER OPERATE + SELECT on every dynamic table in
-- EDGARTOOLS_SILVER, so REFRESH_AFTER_LOAD (which runs EXECUTE AS OWNER as
-- the loader role -- see 08_loader_role.sql) can actually refresh gold
-- dynamic tables that read from silver via dbt ref()/source().
--
-- Root cause (found live 2026-08-22, PRJEDJU-QJB05385): the
-- dbt-gold-silver-rewiring map repointed several gold models (COMPANY,
-- FILING_ACTIVITY, OWNERSHIP_ACTIVITY, OWNERSHIP_HOLDINGS, TICKER_REFERENCE,
-- ...) to read directly from EDGARTOOLS_SILVER dynamic tables (e.g.
-- SEC_COMPANY) instead of the old Python-populated EDGARTOOLS_SOURCE mirror
-- tables -- but 08_loader_role.sql's grants only ever covered
-- EDGARTOOLS_GOLD, never EDGARTOOLS_SILVER. Every EDGARTOOLS_SILVER dynamic
-- table is owned by EDGARTOOLS_<ENV>_DEPLOYER (dbt's default target role),
-- not the loader role -- so REFRESH_AFTER_LOAD's manual refresh of COMPANY
-- (and every other gold table with a silver upstream) failed outright:
--   SQL compilation error: OPERATE privilege is required on all upstream
--   Dynamic Tables of 'EDGARTOOLS_PROD.EDGARTOOLS_GOLD.COMPANY' to perform
--   a manual refresh.
-- and, once OPERATE alone was granted, a second, distinct privilege gap
-- surfaced (a Snowflake dynamic table's query runs as its OWNER, so the
-- owner role also needs SELECT on every object the query references, not
-- just OPERATE on the dynamic table object itself):
--   SQL access control error: Insufficient privileges to operate on
--   dynamic table 'SEC_COMPANY'. Your primary role EDGARTOOLS_PROD_LOADER
--   must have SELECT granted on TABLE EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY.
-- This had been silently failing gold refresh on every scheduled
-- SNOWFLAKE_RUN_MANIFEST_TASK tick (confirmed via TASK_HISTORY: failing
-- since at least 2026-08-18, the day SEC_COMPANY was first created) --
-- masked because the task's overall "started" state and its 6-hour
-- schedule firing on time gave no indication every single run was failing.
-- Full timeline: CLAUDE.md's "SNOWFLAKE_RUN_MANIFEST_TASK / silver-loader
-- OPERATE+SELECT gap" 5-whys section.
--
-- ALL + FUTURE, so a silver table added after this file is applied doesn't
-- reopen the same gap the next time dbt creates one. Additive only (no
-- REVOKE/DROP/OWNERSHIP transfer, per CLAUDE.md's manifest-pipeline-
-- ownership incident -- REVOKE CURRENT GRANTS strips ALL outbound grants on
-- an object, not just the previous state's).
--
-- Required session variables:
--   set database_name = 'EDGARTOOLS_PROD';
--   set silver_schema_name = 'EDGARTOOLS_SILVER';
--   set loader_role_name = 'EDGARTOOLS_PROD_LOADER';
--
-- Run once per environment, AFTER 08_loader_role.sql (idempotent, safe to
-- re-run; also safe to run before any EDGARTOOLS_SILVER dynamic tables
-- exist, since the FUTURE grant still lands):
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/18_silver_loader_read_grants.sql

USE ROLE ACCOUNTADMIN;
USE DATABASE IDENTIFIER($database_name);
USE SCHEMA IDENTIFIER($silver_schema_name);

GRANT OPERATE ON ALL DYNAMIC TABLES IN SCHEMA IDENTIFIER($silver_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT OPERATE ON FUTURE DYNAMIC TABLES IN SCHEMA IDENTIFIER($silver_schema_name) TO ROLE IDENTIFIER($loader_role_name);

GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA IDENTIFIER($silver_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA IDENTIFIER($silver_schema_name) TO ROLE IDENTIFIER($loader_role_name);
