-- Idempotent DDL for the 5 MDM golden-record export targets that
-- edgar_warehouse/mdm/export.py::MDMExporter.export_pending() MERGEs into.
--
-- Root cause (06-03, 2026-07-10): `load_history`'s Publish step failed with
-- "Object 'EDGARTOOLS_DEV.EDGARTOOLS_GOLD.MDM_COMPANY' does not exist or not
-- authorized" because export.py's SnowflakeConnectorWriter.upsert() assumes
-- its 5 target tables (DOMAIN_TO_TABLE in export.py) already exist -- it only
-- ever CREATEs a TEMPORARY staging table, never the target. There was no DDL
-- anywhere in this repo provisioning them; Publish had zero prior dev
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
--   set loader_role_name = 'EDGARTOOLS_DEV_LOADER';  -- EDGARTOOLS_PROD_LOADER in
--     prod (see 08_loader_role.sql). This is the role dbt's company.sql model
--     runs as; its dynamic-table INITIAL refresh checks this role's *direct*
--     grants only (see CLAUDE.md "EDGARTOOLS_DEV_DEPLOYER lacks direct SELECT
--     on EDGARTOOLS_SOURCE"), so it needs a direct SELECT grant on
--     MDM_COMPANY_ENTITY below, confirmed live 2026-07-29 that
--     EDGARTOOLS_PROD_LOADER had none.

USE ROLE IDENTIFIER($deployer_role_name);
USE DATABASE IDENTIFIER($database_name);
USE SCHEMA IDENTIFIER($gold_schema_name);

-- Ticket 06 (.scratch/unified-company-dimension/issues/06-resolve-mdm-company-export-target-circularity.md):
-- rename the company export target from MDM_COMPANY to MDM_COMPANY_ENTITY so
-- the MDM_COMPANY name is free for a future compat view over the enriched
-- COMPANY dimension (ticket 05). Preserves the existing 32k+ prod rows via
-- rename rather than a fresh CREATE TABLE, since MDM export only drains
-- mdm_change_log rows with exported_at IS NULL -- a brand-new empty table
-- would never get backfilled with already-exported history.
--
-- Guarded (not a bare `ALTER TABLE IF EXISTS ... RENAME`) so this file stays
-- safe to re-run indefinitely, confirmed live 2026-07-29:
--   1. A bare rename errors "already exists" on any run after the first,
--      since MDM_COMPANY_ENTITY exists by then.
--   2. `ALTER TABLE IF EXISTS` does not check object type -- once
--      MDM_COMPANY becomes a view (ticket 05 step 2), a guardless rename
--      would rename that view too (confirmed live to succeed, not error)
--      rather than being the no-op an idempotent script requires.
EXECUTE IMMEDIATE $$
BEGIN
  LET target_exists INTEGER := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = $gold_schema_name AND TABLE_NAME = 'MDM_COMPANY_ENTITY'
  );
  IF (target_exists = 0) THEN
    ALTER TABLE IF EXISTS MDM_COMPANY RENAME TO MDM_COMPANY_ENTITY;
  END IF;
  RETURN 'mdm_company_entity target_exists=' || target_exists;
END;
$$;

CREATE TABLE IF NOT EXISTS MDM_COMPANY_ENTITY (
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
COMMENT = 'MDM golden-record company export target (renamed from MDM_COMPANY, ticket 06). MERGEd by MDMExporter.export_pending() (edgar_warehouse/mdm/export.py) keyed on entity_id. Mirrors edgar_warehouse/mdm/database.py::MdmCompany. Joined by company.sql (ticket 05) to enrich EDGARTOOLS_GOLD.COMPANY; MDM_COMPANY itself is slated to become a compat view over that enriched COMPANY.';

-- company.sql (ticket 05) runs as $loader_role_name and its dynamic-table
-- INITIAL refresh only honors this role's direct grants, not a secondary role.
GRANT SELECT ON TABLE MDM_COMPANY_ENTITY TO ROLE IDENTIFIER($loader_role_name);

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
