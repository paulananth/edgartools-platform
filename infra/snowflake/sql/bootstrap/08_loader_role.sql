-- Create EDGARTOOLS_LOADER, the dedicated role that owns the EDGARTOOLS_GOLD
-- dynamic tables and the manifest-pipeline procedures (LOAD_EXPORTS_FOR_RUN,
-- REFRESH_AFTER_LOAD, PROCESS_RUN_MANIFEST_STREAM), and grant it what those
-- procedures need to run EXECUTE AS OWNER.
--
-- Root cause (2026-07-27): manifest-pipeline objects had accumulated mixed
-- ownership -- some dynamic tables owned by ACCOUNTADMIN (from early ad-hoc
-- bootstrapping), the 3 procedures re-owned by EDGARTOOLS_PROD_DEPLOYER on a
-- later manual fix, and 4 brand-new Explore dynamic tables owned by whichever
-- role last ran `dbt run --full-refresh` against them. REFRESH_AFTER_LOAD
-- runs EXECUTE AS OWNER and calls `ALTER DYNAMIC TABLE ... REFRESH` on all
-- gold tables -- Snowflake requires the *direct owner* role for that ALTER,
-- so any owner split across the gold tables plus the 3 procedures breaks the
-- pipeline the next time ownership drifts. One dedicated role, consistently
-- applied, removes the drift instead of chasing it table-by-table. Full
-- timeline: CLAUDE.md's "Manifest-pipeline ownership + cursor-syntax
-- incident 5-whys" section.
--
-- IMPORTANT -- when transferring ownership of an object that may already
-- have downstream grants (reader roles, Streamlit app roles), always use
-- COPY CURRENT GRANTS, never REVOKE CURRENT GRANTS. REVOKE strips ALL
-- outbound grants on the object, not just the previous owner's -- it broke
-- EDGARTOOLS_PROD_READER's read access to all 20 gold tables during the
-- 2026-07-27 incident that created this role.
--
-- Deliberately written as explicit statements per object rather than a
-- Snowflake Scripting loop over an array: this session independently hit
-- two separate live Snowflake Scripting defects (the multi-column shorthand
-- FOR-cursor form, and an infinite-loop FETCH pattern) in code that looked
-- correct but wasn't verified against this account. A file that runs once
-- per environment bootstrap does not need loop brevity badly enough to
-- carry that risk again.
--
-- Required session variables:
--   set database_name = 'EDGARTOOLS_DEV';
--   set source_schema_name = 'EDGARTOOLS_SOURCE';
--   set gold_schema_name = 'EDGARTOOLS_GOLD';
--   set admin_role_name = 'ACCOUNTADMIN';
--   set loader_role_name = 'EDGARTOOLS_LOADER';
--   set loader_default_grantee = 'ACCOUNTADMIN';  -- role that should be able to USE ROLE EDGARTOOLS_LOADER
--   set refresh_warehouse_name = 'EDGARTOOLS_DEV_REFRESH_WH';
--   set source_load_procedure_name = 'LOAD_EXPORTS_FOR_RUN';
--   set refresh_procedure_name = 'REFRESH_AFTER_LOAD';
--   set stream_processor_procedure_name = 'PROCESS_RUN_MANIFEST_STREAM';
--   set manifest_stream_name = 'SNOWFLAKE_RUN_MANIFEST_STREAM';
--   set status_table_name = 'SNOWFLAKE_REFRESH_STATUS';
--
-- After running this file, also grant EDGARTOOLS_LOADER to whichever human
-- users need to operate the pipeline directly (not scripted here -- usernames
-- are per-operator, not environment config):
--   GRANT ROLE EDGARTOOLS_LOADER TO USER <username>;

USE ROLE IDENTIFIER($admin_role_name);

CREATE ROLE IF NOT EXISTS IDENTIFIER($loader_role_name)
  COMMENT = 'Owns EDGARTOOLS_GOLD dynamic tables and the manifest-pipeline procedures. Do not grant ad-hoc; extend this role''s grants instead of re-parenting ownership to ACCOUNTADMIN or a deployer role.';

GRANT ROLE IDENTIFIER($loader_role_name) TO ROLE IDENTIFIER($loader_default_grantee);

GRANT USAGE ON DATABASE IDENTIFIER($database_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT USAGE ON SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT USAGE ON SCHEMA IDENTIFIER($database_name || '.' || $gold_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT USAGE ON WAREHOUSE IDENTIFIER($refresh_warehouse_name) TO ROLE IDENTIFIER($loader_role_name);

-- Object-creation privileges mirroring what a deployer role needs to run
-- 01_source_stage.sql / 02_refresh_status.sql / 03_source_load_wrapper.sql /
-- 04_refresh_wrapper.sql end to end with $deployer_role_name = EDGARTOOLS_LOADER.
GRANT CREATE TABLE ON SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT CREATE STAGE ON SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT CREATE STREAM ON SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT CREATE TASK ON SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT CREATE PIPE ON SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT CREATE PROCEDURE ON SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT CREATE FILE FORMAT ON SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT CREATE VIEW ON SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT CREATE DYNAMIC TABLE ON SCHEMA IDENTIFIER($database_name || '.' || $gold_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT CREATE PROCEDURE ON SCHEMA IDENTIFIER($database_name || '.' || $gold_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT CREATE TASK ON SCHEMA IDENTIFIER($database_name || '.' || $gold_schema_name) TO ROLE IDENTIFIER($loader_role_name);

-- Manifest pipeline reads: every EDGARTOOLS_SOURCE table (current + future),
-- the manifest stream, and the per-run status table it writes to.
GRANT SELECT ON ALL TABLES IN SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT SELECT ON FUTURE TABLES IN SCHEMA IDENTIFIER($database_name || '.' || $source_schema_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT SELECT ON IDENTIFIER($database_name || '.' || $source_schema_name || '.' || $manifest_stream_name) TO ROLE IDENTIFIER($loader_role_name);
GRANT SELECT, UPDATE ON IDENTIFIER($database_name || '.' || $source_schema_name || '.' || $status_table_name) TO ROLE IDENTIFIER($loader_role_name);

-- Re-parent ownership of the EDGARTOOLS_GOLD dynamic tables onto the loader
-- role. COPY CURRENT GRANTS keeps every existing downstream grant (reader
-- roles, Streamlit app roles) intact across the ownership change -- see the
-- incident note above for what REVOKE does instead. If a fresh environment
-- has not created these tables yet (first-ever bootstrap, nothing to
-- reparent), comment out this block; `dbt run` will create them owned by
-- whichever role runs it first.
USE ROLE IDENTIFIER($admin_role_name);
USE DATABASE IDENTIFIER($database_name);
USE SCHEMA IDENTIFIER($gold_schema_name);

GRANT OWNERSHIP ON DYNAMIC TABLE COMPANY TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE FILING_ACTIVITY TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE OWNERSHIP_ACTIVITY TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE OWNERSHIP_HOLDINGS TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE ADVISER_OFFICES TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE ADVISER_DISCLOSURES TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE PRIVATE_FUNDS TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE FILING_DETAIL TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE TICKER_REFERENCE TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE EXECUTIVE_RECORDS TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE EARNINGS_RELEASES TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE INSTITUTIONAL_HOLDINGS TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE ACCOUNTING_FLAGS TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE FINANCIAL_FACTS TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE FINANCIAL_DERIVED TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE FINANCIAL_FACTORS TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE EARNINGS_CALENDAR TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE GUIDANCE_FACTS TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE CONSENSUS_ESTIMATES TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON DYNAMIC TABLE TRANSCRIPT_EVENTS TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;

-- Re-parent ownership of the 3 manifest-pipeline procedures onto the loader
-- role so EXECUTE AS OWNER runs as EDGARTOOLS_LOADER consistently. Signatures
-- must match exactly (Snowflake identifies procedures by name + arg types).
USE SCHEMA IDENTIFIER($source_schema_name);
GRANT OWNERSHIP ON PROCEDURE IDENTIFIER($source_load_procedure_name)(VARCHAR, VARCHAR)
  TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;

USE SCHEMA IDENTIFIER($gold_schema_name);
GRANT OWNERSHIP ON PROCEDURE IDENTIFIER($refresh_procedure_name)(VARCHAR, VARCHAR)
  TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON PROCEDURE IDENTIFIER($stream_processor_procedure_name)()
  TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
