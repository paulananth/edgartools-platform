-- Company mastering ticket 14: SEC's address countryCode on
-- sec_company_address.
--
-- 11_silver_landing_schema.sql carries the same column in its CREATE TABLE
-- IF NOT EXISTS block for a fresh environment; against a table that already
-- exists that file is a silent no-op, so the live table gets the column here
-- (same shape as 14_silver_landing_mdm_entity_id.sql and
-- 20_silver_landing_ownership_evidence.sql). Additive and nullable: landing
-- Parquet written before this change still COPYs in by column name with
-- country_code NULL.
--
-- What it holds: the EDGAR country code SEC writes for a foreign address
-- ("X0" for the United Kingdom, Shell plc). A foreign address carries its
-- country here and leaves stateOrCountry empty; a US address carries its
-- state in stateOrCountry and leaves this empty. Across the 76,230 filers of
-- the company mastering ticket 08 bronze scan the two never both hold a
-- value. The Company matching rules read the country from state_or_country,
-- else country_code.
--
-- Deploy order: apply this file BEFORE any warehouse image carrying company
-- mastering ticket 14 runs a capture. The landing COPY matches by column
-- name, so Parquet that carries country_code into a table without the column
-- loads with it silently dropped, and COPY's load metadata never reloads
-- those files after the ALTER: their rows keep country_code NULL until the
-- CIK's submissions document is landed again. Then rebuild the silver
-- dynamic table, whose SQL body gains the column (dbt does not detect a
-- body-only change):
--   uv run --with dbt-snowflake dbt run --select sec_company_address --full-refresh
-- Rows landed before this change keep country_code NULL until their CIK's
-- submissions document is re-landed.
--
-- Idempotent -- ADD COLUMN IF NOT EXISTS -- safe to re-run.
-- Run once per environment:
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/21_silver_landing_company_country_code.sql

USE DATABASE EDGARTOOLS_PROD;
USE SCHEMA EDGARTOOLS_SILVER_LANDING;
USE ROLE ACCOUNTADMIN;

ALTER TABLE sec_company_address ADD COLUMN IF NOT EXISTS country_code TEXT;
