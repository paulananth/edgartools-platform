-- Grants EDGARTOOLS_PROD_DEPLOYER the same read access to
-- EDGARTOOLS_SILVER_LANDING that 11_silver_landing_schema.sql already
-- grants EDGARTOOLS_PROD_LOADER.
--
-- Root cause this file exists to fix: install.sh's "Snowflake: dbt gold"
-- stage comment assumed "dbt gold above already runs as this loader role
-- (profiles.yml's prod target)" -- false in practice. profiles.yml's prod
-- target defaults DBT_SNOWFLAKE_ROLE to EDGARTOOLS_PROD_LOADER, but dbt's
-- Snowflake adapter unconditionally issues `CREATE SCHEMA IF NOT EXISTS`
-- against its target schema at the start of every run, and Snowflake
-- evaluates the CREATE SCHEMA privilege before checking whether the schema
-- already exists (the same gotcha CLAUDE.md's "MDM Snowflake mirror schema
-- lost on cutover" documents). infra/terraform/access/snowflake/modules/
-- account_access/main.tf's `database_usage` grant deliberately gives
-- CREATE SCHEMA on the database to ONLY the deployer role, not loader --
-- so `dbt run` under the default loader role fails immediately with
-- "Insufficient privileges ... must have CREATE SCHEMA granted on DATABASE"
-- on a genuinely fresh account, confirmed live against PRJEDJU-QJB05385.
--
-- The fix is to run dbt gold as EDGARTOOLS_PROD_DEPLOYER instead (matching
-- Terraform's own separation: deployer creates objects from scratch, and
-- Stage 11 ("Snowflake: loader role ownership", 08_loader_role.sql)
-- transfers ownership of the resulting gold/silver dynamic tables onto
-- loader afterward -- exactly the flow install.sh's Stage 11 comment
-- already describes, just not the "harmless no-op" case it assumed). But a
-- Snowflake dynamic table executes its own scheduled refresh AS ITS OWNER
-- role, not as whoever ran `dbt run` -- so a silver dynamic table created
-- while dbt runs as deployer needs deployer itself (not just loader) to be
-- able to read EDGARTOOLS_SILVER_LANDING, or its INITIAL refresh fails with
-- "Schema 'EDGARTOOLS_SILVER_LANDING' does not exist or not authorized"
-- even though the schema exists and loader can read it fine. Confirmed live
-- against PRJEDJU-QJB05385: 21 of 27 dbt-gold failures were exactly this,
-- for every silver/*.sql model reading edgartools_silver_landing.
--
-- Every statement is an additive GRANT (no REVOKE, no DROP, no OWNERSHIP
-- transfer -- see CLAUDE.md's "Manifest-pipeline ownership + cursor-syntax
-- incident" for why GRANT OWNERSHIP ... REVOKE CURRENT GRANTS silently
-- strips unrelated grants). Mirrors 11_silver_landing_schema.sql's own
-- grants to EDGARTOOLS_PROD_LOADER exactly, for EDGARTOOLS_PROD_DEPLOYER.
--
-- Run once per environment, AFTER 11_silver_landing_schema.sql (idempotent,
-- safe to re-run):
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/16_silver_landing_deployer_read.sql

USE ROLE ACCOUNTADMIN;
USE DATABASE EDGARTOOLS_PROD;

GRANT USAGE ON SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING TO ROLE EDGARTOOLS_PROD_DEPLOYER;
GRANT USAGE ON SEQUENCE EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING.PARSE_SEQ TO ROLE EDGARTOOLS_PROD_DEPLOYER;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING TO ROLE EDGARTOOLS_PROD_DEPLOYER;
GRANT SELECT, INSERT ON FUTURE TABLES IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING TO ROLE EDGARTOOLS_PROD_DEPLOYER;
