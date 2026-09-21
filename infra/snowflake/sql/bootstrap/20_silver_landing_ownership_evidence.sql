-- Person Consumer Contract ticket 19: reporting-owner classification
-- evidence and joint-filing markers on the three Form 3/4/5 landing tables.
--
-- 11_silver_landing_schema.sql carries the same columns in its CREATE TABLE
-- IF NOT EXISTS blocks for a fresh environment; against tables that already
-- exist that file is a silent no-op, so live tables get the columns here
-- (same shape as 14_silver_landing_mdm_entity_id.sql). Additive and
-- nullable: Parquet written by ownership_v1 PARSER_VERSION 2 still COPYs in
-- with these NULL; PARSER_VERSION 3 populates them and its version bump
-- makes the ownership artifact pipeline re-parse every accession on its next
-- run (has_successful_ownership_parse is version-gated), no --force needed.
--
-- What the columns hold (edgar_warehouse/parsers/ownership.py):
--   owner_name_raw -- rptOwnerName exactly as EDGAR disseminated it ("COOK
--     TIMOTHY D"); owner_name keeps edgartools' display reversal. The Person
--     normalizer parses the raw form.
--   other_text, filing_footnote_text, filing_remarks -- the deputization /
--     self-description text rule C-J reads as evidence (research 18 F4);
--     footnotes and remarks are document-level in the SEC schema, so every
--     owner row of a filing carries the same two values.
--   address_is_care_of, address_non_us -- the only two facts kept from
--     reportingOwnerAddress; no street, city, state or zip enters silver
--     (consumer.md, "Never captured into MDM").
--   owner_submissions_present + the seven owner_* structural fields -- rule
--     C-J's step 0 and step 3 inputs, read from the CIK's newest bronze
--     submissions.json at parse time; "" means absent.
--     owner_submissions_sha256 names that snapshot (provenance, replay).
--     A row parsed while bronze had no snapshot for the owner stays
--     "not present" until the next PARSER_VERSION bump or a forced
--     re-parse -- it does not heal when the snapshot is captured later.
--     With no snapshot the owner also counts as a non-company, so an entity
--     owner's owner_name is reversed; watch the not-present rate after the
--     first re-parse (research 18: 0 of 4,831 owner CIKs lacked one).
--   reporting_owner_count (both txn tables) -- a transaction has no owner
--     reference in the SEC schema, so on a joint filing owner_index = 1 is
--     not an attribution; consumers fail closed on reporting_owner_count > 1.
--
-- Idempotent -- ADD COLUMN IF NOT EXISTS -- safe to re-run.
-- Run once per environment:
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/20_silver_landing_ownership_evidence.sql

USE DATABASE EDGARTOOLS_PROD;
USE SCHEMA EDGARTOOLS_SILVER_LANDING;
USE ROLE ACCOUNTADMIN;

ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS owner_name_raw TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS other_text TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS filing_footnote_text TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS filing_remarks TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS address_is_care_of BOOLEAN;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS address_non_us BOOLEAN;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS owner_submissions_present BOOLEAN;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS owner_submissions_sha256 TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS owner_entity_type TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS owner_sic TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS owner_state_of_incorporation TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS owner_ein TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS owner_ticker_count BIGINT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS owner_org TEXT;
ALTER TABLE sec_ownership_reporting_owner ADD COLUMN IF NOT EXISTS owner_fiscal_year_end TEXT;

ALTER TABLE sec_ownership_non_derivative_txn ADD COLUMN IF NOT EXISTS reporting_owner_count BIGINT;
ALTER TABLE sec_ownership_derivative_txn ADD COLUMN IF NOT EXISTS reporting_owner_count BIGINT;
