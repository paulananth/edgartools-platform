-- Grants EDGARTOOLS_PROD_DEPLOYER read access to MDM_COMPANY_ENTITY, the
-- same access 07_mdm_export_targets.sql already grants EDGARTOOLS_PROD_LOADER.
--
-- Root cause this file exists to fix: same shape as
-- 16_silver_landing_deployer_read.sql -- dbt gold's initial `dbt run` (the
-- one-time deploy step that creates every dynamic table) must run as
-- EDGARTOOLS_PROD_DEPLOYER, the only role with database-level CREATE SCHEMA
-- (see that file's header for the full CREATE-SCHEMA-privilege-checked-
-- before-existence gotcha). A Snowflake dynamic table's INITIAL refresh
-- executes as whichever role ran `dbt run` -- deployer, in this case -- so
-- company.sql's `EDGARTOOLS_GOLD.COMPANY` dynamic table failed its INITIAL
-- refresh with "Object 'MDM_COMPANY_ENTITY' does not exist or not
-- authorized" even though 07_mdm_export_targets.sql already grants loader
-- SELECT on it. Confirmed live against PRJEDJU-QJB05385: the sole remaining
-- dbt-gold failure after 16_'s fix.
--
-- This does not conflict with 07_mdm_export_targets.sql's own comment that
-- "company.sql runs as $loader_role_name" -- that describes STEADY STATE:
-- Stage 11 (08_loader_role.sql) transfers ownership of every gold/silver
-- dynamic table from deployer to loader after the initial `dbt run`, and a
-- dynamic table's SCHEDULED (target_lag-driven) refreshes always run as its
-- CURRENT owner, not whoever originally created it -- so once Stage 11 has
-- run, ongoing refreshes genuinely do execute as loader, matching that
-- comment, while this grant only matters for the one-time INITIAL refresh
-- during `dbt run` itself, before ownership transfers.
--
-- Additive only (no REVOKE/DROP/OWNERSHIP transfer, per CLAUDE.md's
-- manifest-pipeline-ownership incident). Applied live to PRJEDJU-QJB05385.
--
-- Run once per environment, AFTER 07_mdm_export_targets.sql (idempotent,
-- safe to re-run):
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/17_mdm_export_deployer_read.sql

USE ROLE ACCOUNTADMIN;
USE DATABASE EDGARTOOLS_PROD;
USE SCHEMA EDGARTOOLS_GOLD;

GRANT SELECT ON TABLE MDM_COMPANY_ENTITY TO ROLE EDGARTOOLS_PROD_DEPLOYER;
