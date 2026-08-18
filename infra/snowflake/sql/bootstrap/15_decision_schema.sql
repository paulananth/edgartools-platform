-- EDGARTOOLS_PROD.EDGARTOOLS_DECISION schema bootstrap.
--
-- Root cause this file exists to fix: identical failure class to
-- 09_mdm_mirror_schema.sql and 10_graph_schema.sql -- another schema that
-- infra/terraform/access/snowflake/modules/account_access/main.tf grants
-- privileges on (reader_decision_schema_usage, reader_decision_all_views,
-- reader_decision_future_views -- GH-247's Decision Contract reader grants)
-- but that no Terraform root actually creates.
-- infra/terraform/snowflake/modules/account_baseline/main.tf's
-- snowflake_schema.schemas resource only creates `source` and `gold`
-- (its schema_names local has exactly those two keys) -- EDGARTOOLS_DECISION
-- was never one of them. CLAUDE.md's "Dev Terraform/Snowflake go-live
-- blockers" 5-whys already documented this exact gap for the dev account
-- ("EDGARTOOLS_DECISION ... does not exist ... Not fixed") without a
-- resolution being committed; this file is that resolution.
--
-- The decision_contract SQL (infra/snowflake/sql/decision_contract/*.sql)
-- that would populate this schema with actual views remains an explicit
-- "sketch" per CLAUDE.md's own account-swap history -- no Snowflake-side
-- source has been chosen yet for "MDM active company universe", and this
-- file does not resolve that. It only creates the empty schema container
-- so the already-Terraform-managed reader grants (which target
-- EDGARTOOLS_PROD.EDGARTOOLS_DECISION unconditionally, regardless of
-- whether the decision contract views themselves exist yet) have something
-- to grant on -- without that, `terraform apply` on
-- access/snowflake/accounts/<env> fails outright on a brand-new account:
--   "Error: [errors.go:23] object does not exist or not authorized"
-- for reader_decision_schema_usage / reader_decision_all_views /
-- reader_decision_future_views.
--
-- Run once per environment (idempotent, safe to re-run):
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/15_decision_schema.sql
--
-- CREATE ... IF NOT EXISTS only -- no DROP, no OWNERSHIP transfer (see
-- CLAUDE.md's "manifest-pipeline ownership" incident for why GRANT
-- OWNERSHIP ... REVOKE CURRENT GRANTS silently strips unrelated grants).

USE ROLE ACCOUNTADMIN;
USE DATABASE IDENTIFIER($database_name);

CREATE SCHEMA IF NOT EXISTS IDENTIFIER($decision_schema_name)
  COMMENT = 'Decision Contract schema (GH-247) -- reader-grant target only; views not yet built, see infra/snowflake/sql/decision_contract/*.sql';
