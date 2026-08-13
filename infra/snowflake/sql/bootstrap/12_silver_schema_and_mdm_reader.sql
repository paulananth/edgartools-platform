-- Snowflake silver schema (EDGARTOOLS_PROD.EDGARTOOLS_SILVER) provisioning,
-- and MDM's dedicated silver-reader role.
--
-- Hand-authored, not generated: unlike 11_silver_landing_schema.sql (which
-- ports 30 existing table definitions verbatim from silver_store.py), the
-- tables in EDGARTOOLS_SILVER are new dbt models with no prior Python
-- definition to reflect from (silver-snowflake-migration map, Ticket 01) --
-- `dbt run` creates them, not this script. This script provisions only what
-- must exist BEFORE that first `dbt run`: the schema itself, and the grants
-- that let it succeed and let MDM read the result.
--
-- Root cause this file exists to prevent, same standing requirement as
-- 11_silver_landing_schema.sql and 09_mdm_mirror_schema.sql: every
-- provisioning step in this migration is committed and re-runnable, never a
-- manual/uncommitted session (CLAUDE.md, "MDM Snowflake mirror schema lost
-- on cutover").
--
-- Run once per environment, BEFORE the first `dbt run` against the silver
-- models (idempotent, safe to re-run):
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/12_silver_schema_and_mdm_reader.sql
--
-- Every statement is CREATE ... IF NOT EXISTS or an additive GRANT (no
-- REVOKE, no DROP, no OWNERSHIP transfer -- see CLAUDE.md's
-- "Manifest-pipeline ownership + cursor-syntax incident").

USE ROLE ACCOUNTADMIN;
USE DATABASE EDGARTOOLS_PROD;
CREATE SCHEMA IF NOT EXISTS EDGARTOOLS_SILVER;

-- EDGARTOOLS_PROD_LOADER needs CREATE DYNAMIC TABLE on this schema before
-- its first `dbt run` can succeed -- CREATE SCHEMA IF NOT EXISTS alone does
-- NOT imply this (same real Snowflake gotcha CLAUDE.md's "MDM Snowflake
-- mirror schema lost on cutover" follow-up documents for CREATE SCHEMA
-- itself: the privilege is evaluated before existence is checked, so
-- pre-creating the schema as ACCOUNTADMIN doesn't let a role without this
-- grant skip the check). Same loader role reused from
-- 11_silver_landing_schema.sql -- see that file's header for why a second
-- pipeline-object owner was not minted for this migration.
GRANT USAGE, CREATE DYNAMIC TABLE, CREATE TABLE, CREATE VIEW
    ON SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER TO ROLE EDGARTOOLS_PROD_LOADER;

-- MDM's new dedicated silver-reader role, replacing ShardedSilverReader's
-- Python-side _TABLES allowlist (silver-snowflake-migration map, Ticket 03)
-- -- deliberately a brand-new, minimally-scoped role rather than extending
-- EDGARTOOLS_PROD_LOADER's write privileges, matching the
-- EDGARTOOLS_GRAPH_REVIEW_READER precedent (dedicated per-consumer reader
-- roles, not overloading a write/owner role for read access).
CREATE ROLE IF NOT EXISTS EDGARTOOLS_PROD_MDM_SILVER_READER;
GRANT USAGE ON DATABASE EDGARTOOLS_PROD TO ROLE EDGARTOOLS_PROD_MDM_SILVER_READER;
GRANT USAGE ON SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER TO ROLE EDGARTOOLS_PROD_MDM_SILVER_READER;

-- FUTURE-scoped, not a hand-maintained per-table list: this is the whole
-- point of retiring the old allowlist (Ticket 03) -- a table added to
-- EDGARTOOLS_SILVER later is automatically readable without this script
-- needing to be edited and re-run to keep up, closing off the exact
-- silent-gap failure shape that caused the INSTITUTIONAL_HOLDS/
-- EMPLOYED_BY incidents (CLAUDE.md).
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER TO ROLE EDGARTOOLS_PROD_MDM_SILVER_READER;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER TO ROLE EDGARTOOLS_PROD_MDM_SILVER_READER;

-- NOT DECIDED BY THIS SCRIPT, flagged explicitly rather than silently
-- assumed: how does MDM's entity-resolution read session actually activate
-- EDGARTOOLS_PROD_MDM_SILVER_READER? Two real options, genuinely different
-- operational shapes:
--   (a) A separate Snowflake secret/connection for MDM's read path,
--       authenticating directly as this role -- the cleanest read/write
--       separation, matching the intent of minting a dedicated role at all.
--   (b) Grant this role to EDGARTOOLS_PROD_LOADER as a secondary role
--       (GRANT ROLE EDGARTOOLS_PROD_MDM_SILVER_READER TO ROLE
--       EDGARTOOLS_PROD_LOADER), since every one of MDM's other Snowflake
--       commands (export/sync-graph/verify-graph) already shares that one
--       runtime role/secret (CLAUDE.md, "Manifest-pipeline ownership +
--       cursor-syntax incident") -- reuses the existing credential, but
--       partially reintroduces the write-role read-access overlap Ticket 03
--       chose a dedicated role specifically to avoid.
-- Ticket 03 decided the role should be dedicated and minimally-scoped; it
-- did not decide which credential activates it. Resolve this when MDM's
-- actual entity-resolution silver-read code is implemented, not here.
