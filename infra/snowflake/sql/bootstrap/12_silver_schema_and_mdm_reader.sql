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
--
-- DYNAMIC TABLES and VIEWS need separate grant statements -- Snowflake's
-- "ALL/FUTURE DYNAMIC TABLES" grant does not cover plain views. Missed on
-- first pass (silver-snowflake-migration map, Ticket 12): sec_guidance_
-- fact_reject is deliberately a plain view, not a dynamic_table (Ticket
-- 01's "quarantine log, no natural key" exception) -- live grants confirmed
-- 30/31 EDGARTOOLS_SILVER tables covered, this one missing, before the
-- VIEW-specific grants below were added.
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER TO ROLE EDGARTOOLS_PROD_MDM_SILVER_READER;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER TO ROLE EDGARTOOLS_PROD_MDM_SILVER_READER;
GRANT SELECT ON ALL VIEWS IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER TO ROLE EDGARTOOLS_PROD_MDM_SILVER_READER;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER TO ROLE EDGARTOOLS_PROD_MDM_SILVER_READER;

-- Credential activation (silver-snowflake-migration map, Ticket 12,
-- resolved -- this section used to flag this as undecided; it no longer is).
-- MDM's read session activates this role via USE ROLE post-connect on the
-- SAME secret export/sync-graph/verify-graph already use
-- (MDM_SNOWFLAKE_SECRET_JSON), not a second dedicated secret -- reuses the
-- existing credential rather than adding new Secrets Manager/ECS wiring for
-- a first migration slice. This does reintroduce some write/read role
-- overlap on the connecting credential, same tradeoff that script's option
-- (b) already named -- accepted for this slice, revisit if a stricter
-- secret-per-role boundary is ever justified.
--
-- Note this file does NOT parameterize its grantee the way
-- 08_loader_role.sql's $loader_default_grantee session variable does (that
-- file is a template re-run per environment; this one is hand-authored and
-- hardcoded to EDGARTOOLS_PROD throughout, matching this file's own header
-- comment). The grant below is a literal ROLE name for that reason, not an
-- omitted convention.
--
-- Live-verified this session (2026-08-18): after connecting via
-- MDM_SNOWFLAKE_SECRET_JSON, `USE ROLE EDGARTOOLS_PROD_MDM_SILVER_READER`
-- succeeds and SEC_COMPANY is queryable through it -- confirming the grant
-- below, not asserting it un-tested. Separate finding, not fixed here: the
-- live secret's own ROLE field is ACCOUNTADMIN, not EDGARTOOLS_PROD_LOADER
-- as CLAUDE.md's "one runtime role" claim describes -- drifted from that
-- doc at some point; granting to ACCOUNTADMIN below matches today's actual
-- runtime identity, not the documented one. This is role-membership, not
-- object ownership -- it does not repeat the ACCOUNTADMIN-owns-pipeline-
-- objects pattern CLAUDE.md's manifest-pipeline-ownership incident forbids
-- (that incident was about who OWNS created objects; this grants an
-- existing role permission to activate a separate, minimally-scoped
-- read-only role, and creates/owns nothing).
GRANT ROLE EDGARTOOLS_PROD_MDM_SILVER_READER TO ROLE ACCOUNTADMIN;
-- If a future secret rotation moves the runtime role to EDGARTOOLS_PROD_LOADER
-- (matching CLAUDE.md's original documented shape), also run:
--   GRANT ROLE EDGARTOOLS_PROD_MDM_SILVER_READER TO ROLE EDGARTOOLS_PROD_LOADER;
