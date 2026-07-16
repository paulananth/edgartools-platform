-- Idempotent DDL for the 5 MDM golden-record export targets that
-- edgar_warehouse/mdm/export.py::MDMExporter.export_pending() MERGEs into.
--
-- Root cause (06-03, 2026-07-10): `load_history`'s MdmExport step failed with
-- "Object 'EDGARTOOLS_DEV.EDGARTOOLS_GOLD.MDM_COMPANY' does not exist or not
-- authorized" because export.py's SnowflakeConnectorWriter.upsert() assumes
-- its 5 target tables (DOMAIN_TO_TABLE in export.py) already exist -- it only
-- ever CREATEs a TEMPORARY staging table, never the target. There was no DDL
-- anywhere in this repo provisioning them; MdmExport had zero prior dev
-- executions before this run, so the gap was never exercised.
--
-- Column shapes are derived from the SQLAlchemy models in
-- edgar_warehouse/mdm/database.py (MdmCompany, MdmAdviser, MdmPerson,
-- MdmSecurity, MdmFund) -- the same models export.py serializes rows from
-- via MDMExporter._serialize() (row.__table__.columns, datetime -> isoformat
-- string).
--
-- Type choices verified live against dev Snowflake (06-03 smoke test) using
-- the exact MERGE pattern export.py's SnowflakeConnectorWriter.upsert() emits
-- (temp table with all-VARIANT columns populated via
-- `SELECT PARSE_JSON(...) FROM VALUES (%s, ...)`, MERGE ... WHEN MATCHED /
-- WHEN NOT MATCHED using bare `source.<col>` references): Snowflake
-- implicitly coerces VARIANT source values into VARCHAR, NUMBER, BOOLEAN,
-- and TIMESTAMP_TZ target columns without explicit casts, and
-- PARSE_JSON('null') (export.py's encoding of a Python None) coerces to a
-- real SQL NULL on the target column, not a JSON null literal. JSON-typed
-- SQLAlchemy columns (MdmPerson.name_variants / role_titles) are kept as
-- Snowflake VARIANT so they round-trip natively.
--
-- The MERGE key export.py always uses is "entity_id" (default param,
-- unchanged by any current caller) -- entity_id is the natural key on every
-- table below.
--
-- Required session variables:
--   set database_name = 'EDGARTOOLS_DEV';
--   set gold_schema_name = 'EDGARTOOLS_GOLD';
--   set deployer_role_name = 'ACCOUNTADMIN';  -- must match MDM_SNOWFLAKE_ROLE /
--     DBT_SNOWFLAKE_ROLE in the environment's Snowflake secret (dev:
--     edgartools-dev/mdm/snowflake -> MDM_SNOWFLAKE_ROLE=ACCOUNTADMIN as of
--     2026-07-10; prod may differ -- confirm against
--     edgartools-prod/mdm/snowflake before applying there).

USE ROLE IDENTIFIER($deployer_role_name);
USE DATABASE IDENTIFIER($database_name);
USE SCHEMA IDENTIFIER($gold_schema_name);

CREATE TABLE IF NOT EXISTS MDM_COMPANY (
  entity_id                 VARCHAR(36)   NOT NULL,
  cik                       NUMBER(38, 0),
  canonical_name            VARCHAR,
  ein                       VARCHAR,
  sic_code                  VARCHAR,
  sic_description           VARCHAR,
  state_of_incorporation    VARCHAR,
  fiscal_year_end           VARCHAR,
  ticker                    VARCHAR,
  primary_ticker            VARCHAR,
  primary_exchange          VARCHAR,
  tracking_status           VARCHAR,
  parent_company_entity_id  VARCHAR(36),
  valid_from                TIMESTAMP_TZ,
  valid_to                  TIMESTAMP_TZ,
  PRIMARY KEY (entity_id)
)
COMMENT = 'MDM golden-record company export target. MERGEd by MDMExporter.export_pending() (edgar_warehouse/mdm/export.py) keyed on entity_id. Mirrors edgar_warehouse/mdm/database.py::MdmCompany.';

CREATE TABLE IF NOT EXISTS MDM_ADVISER (
  entity_id                  VARCHAR(36)   NOT NULL,
  cik                        NUMBER(38, 0),
  crd_number                 VARCHAR,
  sec_file_number            VARCHAR,
  canonical_name             VARCHAR,
  adviser_type                VARCHAR,
  hq_city                    VARCHAR,
  hq_state                   VARCHAR,
  aum_total                  FLOAT,
  fund_count                 NUMBER(38, 0),
  linked_company_entity_id   VARCHAR(36),
  valid_from                 TIMESTAMP_TZ,
  valid_to                   TIMESTAMP_TZ,
  PRIMARY KEY (entity_id)
)
COMMENT = 'MDM golden-record adviser export target. MERGEd by MDMExporter.export_pending() (edgar_warehouse/mdm/export.py) keyed on entity_id. Mirrors edgar_warehouse/mdm/database.py::MdmAdviser.';

CREATE TABLE IF NOT EXISTS MDM_PERSON (
  entity_id                  VARCHAR(36)   NOT NULL,
  owner_cik                  NUMBER(38, 0),
  canonical_name              VARCHAR,
  name_variants               VARIANT,
  primary_role                VARCHAR,
  role_titles                 VARIANT,
  affiliated_company_count    NUMBER(38, 0),
  valid_from                  TIMESTAMP_TZ,
  valid_to                    TIMESTAMP_TZ,
  PRIMARY KEY (entity_id)
)
COMMENT = 'MDM golden-record person export target. MERGEd by MDMExporter.export_pending() (edgar_warehouse/mdm/export.py) keyed on entity_id. Mirrors edgar_warehouse/mdm/database.py::MdmPerson.';

CREATE TABLE IF NOT EXISTS MDM_SECURITY (
  entity_id          VARCHAR(36)   NOT NULL,
  issuer_entity_id   VARCHAR(36),
  canonical_title    VARCHAR,
  security_type      VARCHAR,
  security_class     VARCHAR,
  cusip              VARCHAR,
  isin               VARCHAR,
  valid_from         TIMESTAMP_TZ,
  valid_to           TIMESTAMP_TZ,
  PRIMARY KEY (entity_id)
)
COMMENT = 'MDM golden-record security export target. MERGEd by MDMExporter.export_pending() (edgar_warehouse/mdm/export.py) keyed on entity_id. Mirrors edgar_warehouse/mdm/database.py::MdmSecurity.';

CREATE TABLE IF NOT EXISTS MDM_FUND (
  entity_id            VARCHAR(36)   NOT NULL,
  adviser_entity_id    VARCHAR(36),
  private_fund_id      VARCHAR,
  canonical_name       VARCHAR,
  fund_type            VARCHAR,
  jurisdiction         VARCHAR,
  aum_amount           FLOAT,
  aum_as_of_date       DATE,
  valid_from           TIMESTAMP_TZ,
  valid_to             TIMESTAMP_TZ,
  PRIMARY KEY (entity_id)
)
COMMENT = 'MDM golden-record fund export target. MERGEd by MDMExporter.export_pending() (edgar_warehouse/mdm/export.py) keyed on entity_id. Mirrors edgar_warehouse/mdm/database.py::MdmFund.';

-- Existing targets created before Snowflake Postgres migration 010 need the
-- newly exported ADV identifier as an additive, live-safe migration.
ALTER TABLE MDM_FUND ADD COLUMN IF NOT EXISTS private_fund_id VARCHAR;
