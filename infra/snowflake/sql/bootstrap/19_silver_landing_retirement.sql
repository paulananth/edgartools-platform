-- Ticket 35: Silver Landing Retirement Record companion table.
--
-- Append-only. A source family writes one row per business key that a
-- Scope Completion proved dropped. dbt silver models anti-join the latest
-- event per key via macros/silver_not_retired.sql. Never physically
-- deletes from domain landing tables.
--
-- Also adds cause_reference to sec_company_ticker so Ticket 35's
-- Snowflake-landing COUNT(*) barrier can read back rows for one
-- cause_reference. Additive; old Parquet without the column still COPY
-- IN (NULL).
--
-- Idempotent. Run once per environment:
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/19_silver_landing_retirement.sql

USE DATABASE EDGARTOOLS_PROD;
USE SCHEMA EDGARTOOLS_SILVER_LANDING;
USE ROLE ACCOUNTADMIN;

CREATE TABLE IF NOT EXISTS silver_landing_retirement (
    source_family TEXT NOT NULL,
    target_table TEXT NOT NULL,
    business_key TEXT NOT NULL,
    cause_reference TEXT NOT NULL,
    retired_at TIMESTAMP_TZ NOT NULL,
    parse_sequence BIGINT DEFAULT PARSE_SEQ.NEXTVAL,
    PRIMARY KEY (parse_sequence)
);
ALTER TABLE silver_landing_retirement ALTER COLUMN parse_sequence DROP NOT NULL;

ALTER TABLE sec_company_ticker ADD COLUMN IF NOT EXISTS cause_reference TEXT;

GRANT SELECT, INSERT ON TABLE silver_landing_retirement TO ROLE EDGARTOOLS_PROD_LOADER;
GRANT SELECT ON TABLE silver_landing_retirement TO ROLE EDGARTOOLS_PROD_DEPLOYER;
