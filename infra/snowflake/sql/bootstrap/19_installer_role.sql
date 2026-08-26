-- EDGARTOOLS_PROD_INSTALLER: a dedicated, least-privilege role for
-- install.sh's own schema-bootstrap stages, so they stop running as
-- ACCOUNTADMIN by default.
--
-- Root cause this file exists to fix: every bootstrap SQL file install.sh
-- pipes through `snow sql` (09_mdm_mirror_schema.sql, 10_graph_schema.sql,
-- 11-14/16/17/18_*.sql, 06/07's inline session-var blocks) opens with
-- `USE ROLE ACCOUNTADMIN;` -- not implied by the connection's default role,
-- literally hardcoded per file. Every schema/table/task/procedure install.sh
-- creates directly (not via Terraform or dbt, both of which already run
-- under their own dedicated roles/profiles) ends up owned by ACCOUNTADMIN as
-- a result -- the same "all-powerful-role owns everything" shape CLAUDE.md
-- already documents for the original Streamlit dashboard ("Still shared /
-- not fixed", Streamlit-in-Snowflake ownership 5-whys).
--
-- Scope is deliberately surgical, not total (change-propagation map, Ticket
-- 30 follow-up investigation, 2026-08-26): Snowflake makes the role that
-- creates a schema its owner, so a role granted only CREATE SCHEMA ON
-- DATABASE can create a schema and then freely create/grant on everything
-- inside it, with no further per-object-type grants needed. That covers the
-- files that are pure "create a new schema, populate it" -- currently
-- 09_mdm_mirror_schema.sql and 11_silver_landing_schema.sql, both verified
-- by inspection to contain no statement touching an object this role
-- wouldn't itself own.
--
-- What is deliberately NOT covered, and stays running as ACCOUNTADMIN
-- (each with its own comment at the point it happens, not silently):
--   - Statements that GRANT a privilege ON an object this role doesn't own
--     (e.g. 10_graph_schema.sql's `GRANT CREATE SCHEMA ON DATABASE ... TO
--     ROLE LOADER` -- a database-level grant; 13_silver_landing_ingest.sql's
--     `GRANT EXECUTE TASK ON ACCOUNT TO ROLE LOADER` -- an account-level
--     grant). Both require either owning the database/account-level
--     privilege management (MANAGE GRANTS ON ACCOUNT) or already owning the
--     target object -- granting either to this role would make it nearly as
--     powerful as ACCOUNTADMIN, defeating the point of a separate role.
--   - CREATE ROLE (12_silver_schema_and_mdm_reader.sql creates
--     EDGARTOOLS_PROD_MDM_SILVER_READER) -- needs CREATEROLE or ACCOUNTADMIN.
--   - Grants on objects owned by EDGARTOOLS_PROD_DEPLOYER/other pre-existing
--     roles (16/17's deployer-read grants; 07/06's session-var-driven blocks
--     against Terraform-owned EDGARTOOLS_SOURCE/EDGARTOOLS_GOLD schemas).
--   - 08_loader_role.sql itself (GRANT OWNERSHIP transfers require admin).
--
-- Run once per environment (idempotent, safe to re-run), before any stage
-- that references EDGARTOOLS_PROD_INSTALLER:
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/19_installer_role.sql

USE ROLE ACCOUNTADMIN;
USE DATABASE EDGARTOOLS_PROD;

CREATE ROLE IF NOT EXISTS EDGARTOOLS_PROD_INSTALLER
  COMMENT = 'Creates new schemas (and everything inside them) during install.sh bootstrap runs, in place of running those stages as ACCOUNTADMIN. Deliberately scoped to CREATE SCHEMA ON DATABASE only -- see this role''s own file, 19_installer_role.sql, for exactly which install.sh stages use it and which stay on ACCOUNTADMIN.';

GRANT ROLE EDGARTOOLS_PROD_INSTALLER TO ROLE ACCOUNTADMIN;

GRANT USAGE, CREATE SCHEMA ON DATABASE EDGARTOOLS_PROD TO ROLE EDGARTOOLS_PROD_INSTALLER;
