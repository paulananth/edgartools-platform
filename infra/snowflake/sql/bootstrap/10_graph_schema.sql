-- EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION graph schema bootstrap.
--
-- Root cause this file exists to fix: identical failure class to
-- 09_mdm_mirror_schema.sql, one step further down the pipeline. The graph
-- destination schema (`mdm sync-graph`'s target -- see
-- docs/prod-mdm-snowflake-graph-first-load.md) was never re-provisioned
-- after the Snowflake account cutover, so `mdm sync-graph` failed:
--   "SQL compilation error: Insufficient privileges to operate on database
--   'EDGARTOOLS_PROD'. Your primary role EDGARTOOLS_PROD_LOADER must have
--   CREATE SCHEMA granted on DATABASE EDGARTOOLS_PROD."
--
-- Two distinct grants are required, not one -- discovered the hard way by
-- re-running sync-graph after only fixing the first:
--   1. CREATE SCHEMA ON DATABASE EDGARTOOLS_PROD, granted to
--      EDGARTOOLS_PROD_LOADER. Snowflake gotcha: `CREATE SCHEMA IF NOT
--      EXISTS` still evaluates the CREATE SCHEMA privilege BEFORE checking
--      whether the schema already exists -- pre-creating the schema as
--      ACCOUNTADMIN does NOT make the IF NOT EXISTS clause skip the
--      privilege check for the role actually running the command. The
--      database-level grant is required even once the schema exists.
--   2. USAGE/CREATE TABLE/CREATE VIEW + DML grants on the schema itself,
--      for the same reason 09_mdm_mirror_schema.sql needs them on MDM.
--
-- `docs/prod-mdm-snowflake-graph-first-load.md`'s original "Required
-- Production Objects" section documented the sync-graph/verify-graph
-- runtime role as EDGARTOOLS_PROD_DEPLOYER. That was never actually true in
-- this account -- edgar_warehouse/mdm/snowflake_graph.py's
-- SnowflakeGraphSyncExecutor.from_env() reads the exact same
-- MDM_SNOWFLAKE_SECRET_JSON secret (and its ROLE field) as
-- edgar_warehouse/mdm/export.py's mirror writer, so both commands run as
-- whatever role that one secret specifies -- currently EDGARTOOLS_PROD_LOADER.
--
-- Run once per environment (idempotent, safe to re-run):
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/10_graph_schema.sql
--
-- After this, also (re-)apply the Native App grants, which target the same
-- schema and are likewise idempotent:
--   sed 's/{{ database }}/EDGARTOOLS_PROD/g' infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql \
--     | snow sql --connection edgartools-prod -f /dev/stdin

USE ROLE ACCOUNTADMIN;
USE DATABASE EDGARTOOLS_PROD;

GRANT CREATE SCHEMA ON DATABASE EDGARTOOLS_PROD TO ROLE EDGARTOOLS_PROD_LOADER;

CREATE SCHEMA IF NOT EXISTS NEO4J_GRAPH_MIGRATION;

GRANT USAGE, CREATE TABLE, CREATE VIEW ON SCHEMA EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION TO ROLE EDGARTOOLS_PROD_LOADER;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION TO ROLE EDGARTOOLS_PROD_LOADER;
GRANT SELECT, INSERT, UPDATE, DELETE ON FUTURE TABLES IN SCHEMA EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION TO ROLE EDGARTOOLS_PROD_LOADER;
