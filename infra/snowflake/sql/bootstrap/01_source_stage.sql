-- Bootstrap the Snowflake-native S3 import path for EdgarTools export packages.
--
-- Required session variables:
--   set database_name = 'EDGARTOOLS_DEV';
--   set source_schema_name = 'EDGARTOOLS_SOURCE';
--   set deployer_role_name = 'EDGARTOOLS_DEV_DEPLOYER';
--   set storage_integration_name = 'EDGARTOOLS_DEV_EXPORT_INTEGRATION';
--   set storage_role_arn = 'arn:aws:iam::123456789012:role/edgartools-dev-snowflake-s3';
--   set storage_external_id = NULL;
--   set export_root_url = 's3://edgartools-dev-snowflake-export/warehouse/artifacts/snowflake_exports/';
--   set stage_name = 'EDGARTOOLS_SOURCE_EXPORT_STAGE';
--   set parquet_file_format_name = 'EDGARTOOLS_SOURCE_EXPORT_FILE_FORMAT';
--   set manifest_file_format_name = 'EDGARTOOLS_SOURCE_RUN_MANIFEST_FILE_FORMAT';
--   set manifest_inbox_table_name = 'SNOWFLAKE_RUN_MANIFEST_INBOX';
--   set manifest_pipe_name = 'SNOWFLAKE_RUN_MANIFEST_PIPE';
--   set manifest_sns_topic_arn = 'arn:aws:sns:us-east-1:123456789012:edgartools-dev-snowflake-manifest-events';

USE ROLE IDENTIFIER($deployer_role_name);

BEGIN
  EXECUTE IMMEDIATE
    'CREATE STORAGE INTEGRATION IF NOT EXISTS ' || $storage_integration_name || '
       TYPE = EXTERNAL_STAGE
       STORAGE_PROVIDER = S3
       ENABLED = TRUE
       STORAGE_AWS_ROLE_ARN = ''' || $storage_role_arn || '''
       STORAGE_ALLOWED_LOCATIONS = (''' || $export_root_url || ''')
       COMMENT = ''EdgarTools native-pull storage integration.''';
END;

BEGIN
  EXECUTE IMMEDIATE
    'ALTER STORAGE INTEGRATION ' || $storage_integration_name || '
       SET ENABLED = TRUE
           STORAGE_AWS_ROLE_ARN = ''' || $storage_role_arn || '''
           STORAGE_ALLOWED_LOCATIONS = (''' || $export_root_url || ''')';
END;

BEGIN
  IF COALESCE($storage_external_id, '') <> '' THEN
    EXECUTE IMMEDIATE
      'ALTER STORAGE INTEGRATION ' || $storage_integration_name || '
         SET STORAGE_AWS_EXTERNAL_ID = ''' || $storage_external_id || '''';
  END IF;
END;

USE DATABASE IDENTIFIER($database_name);
USE SCHEMA IDENTIFIER($source_schema_name);

CREATE FILE FORMAT IF NOT EXISTS IDENTIFIER($parquet_file_format_name)
  TYPE = PARQUET
  COMPRESSION = AUTO;

CREATE FILE FORMAT IF NOT EXISTS IDENTIFIER($manifest_file_format_name)
  TYPE = JSON
  COMPRESSION = AUTO
  STRIP_OUTER_ARRAY = FALSE;

CREATE STAGE IF NOT EXISTS IDENTIFIER($stage_name)
  URL = $export_root_url
  STORAGE_INTEGRATION = $storage_integration_name
  COMMENT = 'EdgarTools export stage used for Snowflake-native pull ingestion.';

ALTER STAGE IDENTIFIER($stage_name)
  SET URL = $export_root_url
      STORAGE_INTEGRATION = $storage_integration_name;

CREATE TABLE IF NOT EXISTS IDENTIFIER($manifest_inbox_table_name) (
  source_filename STRING NOT NULL,
  manifest VARIANT NOT NULL,
  environment STRING NOT NULL,
  workflow_name STRING NOT NULL,
  run_id STRING NOT NULL,
  business_date DATE NOT NULL,
  completed_at TIMESTAMP_TZ NOT NULL,
  received_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Raw run manifests auto-ingested from the Snowflake export bucket.';

CREATE TABLE IF NOT EXISTS COMPANY (
  company_key NUMBER(38, 0),
  cik NUMBER(38, 0),
  entity_name STRING,
  entity_type STRING,
  sic STRING,
  sic_description STRING,
  state_of_incorporation STRING,
  fiscal_year_end STRING,
  last_sync_run_id STRING
)
COMMENT = 'Current company dimension mirrored from the canonical warehouse gold export.';

CREATE TABLE IF NOT EXISTS FILING_ACTIVITY (
  fact_key NUMBER(38, 0),
  company_key NUMBER(38, 0),
  filing_key NUMBER(38, 0),
  date_key NUMBER(38, 0),
  form_key NUMBER(38, 0),
  accession_number STRING,
  cik NUMBER(38, 0),
  form STRING,
  filing_date DATE,
  report_date DATE,
  is_xbrl BOOLEAN
)
COMMENT = 'Current filing-activity fact mirrored from the canonical warehouse gold export.';

CREATE TABLE IF NOT EXISTS OWNERSHIP_ACTIVITY (
  fact_key NUMBER(38, 0),
  company_key NUMBER(38, 0),
  date_key NUMBER(38, 0),
  form_key NUMBER(38, 0),
  party_key NUMBER(38, 0),
  security_key NUMBER(38, 0),
  ownership_txn_type_key NUMBER(38, 0),
  accession_number STRING,
  owner_index NUMBER(38, 0),
  txn_index NUMBER(38, 0),
  transaction_code STRING,
  transaction_shares FLOAT,
  transaction_price FLOAT,
  shares_owned_after FLOAT,
  is_derivative BOOLEAN
)
COMMENT = 'Current ownership-activity fact mirrored from the canonical warehouse gold export.';

CREATE TABLE IF NOT EXISTS OWNERSHIP_HOLDINGS (
  fact_key NUMBER(38, 0),
  company_key NUMBER(38, 0),
  date_key NUMBER(38, 0),
  party_key NUMBER(38, 0),
  security_key NUMBER(38, 0),
  accession_number STRING,
  owner_index NUMBER(38, 0),
  shares_owned_after FLOAT,
  ownership_direct_indirect STRING
)
COMMENT = 'Current ownership-holdings snapshot mirrored from the canonical warehouse gold export.';

CREATE TABLE IF NOT EXISTS ADVISER_OFFICES (
  fact_key NUMBER(38, 0),
  company_key NUMBER(38, 0),
  date_key NUMBER(38, 0),
  geography_key NUMBER(38, 0),
  accession_number STRING,
  office_index NUMBER(38, 0),
  office_name STRING,
  is_headquarters BOOLEAN
)
COMMENT = 'Current adviser-office fact mirrored from the canonical warehouse gold export.';

CREATE TABLE IF NOT EXISTS ADVISER_DISCLOSURES (
  fact_key NUMBER(38, 0),
  company_key NUMBER(38, 0),
  date_key NUMBER(38, 0),
  disclosure_category_key NUMBER(38, 0),
  accession_number STRING,
  event_index NUMBER(38, 0),
  is_reported BOOLEAN
)
COMMENT = 'Current adviser-disclosure fact mirrored from the canonical warehouse gold export.';

CREATE TABLE IF NOT EXISTS PRIVATE_FUNDS (
  fact_key NUMBER(38, 0),
  company_key NUMBER(38, 0),
  date_key NUMBER(38, 0),
  private_fund_key NUMBER(38, 0),
  accession_number STRING,
  fund_index NUMBER(38, 0),
  aum_amount FLOAT
)
COMMENT = 'Current private-fund fact mirrored from the canonical warehouse gold export.';

CREATE TABLE IF NOT EXISTS FILING_DETAIL (
  filing_key NUMBER(38, 0),
  accession_number STRING,
  cik NUMBER(38, 0),
  company_key NUMBER(38, 0),
  form STRING,
  form_key NUMBER(38, 0),
  filing_date DATE,
  date_key NUMBER(38, 0),
  report_date DATE,
  is_xbrl BOOLEAN,
  size NUMBER(38, 0)
)
COMMENT = 'Current filing-detail dimension mirrored from the canonical warehouse gold export.';

CREATE TABLE IF NOT EXISTS TICKER_REFERENCE (
  cik NUMBER(38, 0),
  ticker STRING,
  exchange STRING,
  last_sync_run_id STRING
)
COMMENT = 'Current ticker-reference dimension mirrored from the canonical warehouse gold export.';

-- =====================================================================
-- Branch B — Fundamentals research extension (PR-1)
--
-- 3 PASSTHROUGH tables (high-cardinality, CIK-keyed natural-key MERGE).
-- Loaded by LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN (composite-key proc).
-- NOT NULL applied to MERGE-key columns ONLY (Q5-C decision).
-- =====================================================================

CREATE TABLE IF NOT EXISTS SEC_FINANCIAL_FACT (
  cik              NUMBER(38, 0) NOT NULL,
  accession_number STRING        NOT NULL,
  concept          STRING        NOT NULL,
  fiscal_period    STRING        NOT NULL,
  segment          STRING        NOT NULL,
  fiscal_year      NUMBER(38, 0),
  period_end       DATE,
  form_type        STRING,
  value            FLOAT,
  unit             STRING,
  decimals         NUMBER(38, 0),
  parser_version   STRING,
  ingested_at      TIMESTAMP_TZ
)
COMMENT = 'XBRL us-gaap fact per (cik, accession, concept, fiscal_period, segment). Passthrough from silver sec_financial_fact.';

CREATE TABLE IF NOT EXISTS SEC_THIRTEENF_HOLDING (
  cik                 NUMBER(38, 0) NOT NULL,
  accession_number    STRING        NOT NULL,
  holding_index       NUMBER(38, 0) NOT NULL,
  period_of_report    DATE,
  cusip               STRING,
  issuer_name         STRING,
  security_title      STRING,
  shares_held         FLOAT,
  market_value        FLOAT,
  security_class      STRING,
  put_call            STRING,
  discretion_type     STRING,
  voting_auth_sole    FLOAT,
  voting_auth_shared  FLOAT,
  voting_auth_none    FLOAT,
  parser_version      STRING,
  ingested_at         TIMESTAMP_TZ
)
COMMENT = '13F INFORMATION TABLE holding per (cik, accession, holding_index). Passthrough from silver sec_thirteenf_holding.';

CREATE TABLE IF NOT EXISTS SEC_FINANCIAL_DERIVED (
  cik                  NUMBER(38, 0) NOT NULL,
  accession_number     STRING        NOT NULL,
  fiscal_period        STRING        NOT NULL,
  fiscal_year          NUMBER(38, 0),
  period_end           DATE,
  form_type            STRING,
  revenue              FLOAT,
  gross_profit         FLOAT,
  ebitda               FLOAT,
  ebit                 FLOAT,
  net_income           FLOAT,
  eps_diluted          FLOAT,
  total_assets         FLOAT,
  total_liabilities    FLOAT,
  total_equity         FLOAT,
  cash_and_equivalents FLOAT,
  total_debt           FLOAT,
  operating_cash_flow  FLOAT,
  capex                FLOAT,
  free_cash_flow       FLOAT,
  gross_margin         FLOAT,
  ebitda_margin        FLOAT,
  net_margin           FLOAT,
  roic                 FLOAT,
  roe                  FLOAT,
  roa                  FLOAT,
  parser_version       STRING,
  ingested_at          TIMESTAMP_TZ
)
COMMENT = 'Derived per-period financial metrics. Passthrough from silver sec_financial_derived. Forensic scores live on ACCOUNTING_FLAG (annual constructs).';

-- =====================================================================
-- 3 DIMENSIONAL tables (low-cardinality, surrogate fact_key MERGE).
-- Loaded by the EXISTING LOAD_EXPORTS_FOR_RUN proc.
-- COMPANY/DATE/FORM keys generated in the warehouse build step.
-- AUDIT_FIRM dim deferred to a future PR per Q3-D.
-- =====================================================================

CREATE TABLE IF NOT EXISTS EARNINGS_RELEASE (
  fact_key            NUMBER(38, 0) NOT NULL,
  company_key         NUMBER(38, 0),
  filing_date_key     NUMBER(38, 0),
  period_end_date_key NUMBER(38, 0),
  form_key            NUMBER(38, 0),
  accession_number    STRING,
  cik                 NUMBER(38, 0),
  filing_date         DATE,
  fiscal_year         NUMBER(38, 0),
  fiscal_quarter      NUMBER(38, 0),
  period_end          DATE,
  revenue_gaap        FLOAT,
  net_income_gaap     FLOAT,
  eps_gaap_diluted    FLOAT,
  has_non_gaap        BOOLEAN,
  has_guidance        BOOLEAN,
  parser_version      STRING,
  ingested_at         TIMESTAMP_TZ
)
COMMENT = '8-K earnings release fact per (cik, accession). Dimensional — joins COMPANY + DATE×2 + FORM.';

CREATE TABLE IF NOT EXISTS EXECUTIVE_RECORD (
  fact_key             NUMBER(38, 0) NOT NULL,
  company_key          NUMBER(38, 0),
  fiscal_year_date_key NUMBER(38, 0),
  accession_number     STRING,
  cik                  NUMBER(38, 0),
  fiscal_year          NUMBER(38, 0),
  exec_name            STRING,
  exec_role            STRING,
  total_comp           FLOAT,
  base_salary          FLOAT,
  bonus                FLOAT,
  stock_awards         FLOAT,
  option_awards        FLOAT,
  non_equity_incentive FLOAT,
  parser_version       STRING,
  ingested_at          TIMESTAMP_TZ
)
COMMENT = 'DEF 14A executive compensation fact per (cik, accession, exec_name). Dimensional — joins COMPANY + DATE. Person dim (PARTY) not yet wired.';

CREATE TABLE IF NOT EXISTS ACCOUNTING_FLAG (
  fact_key             NUMBER(38, 0) NOT NULL,
  company_key          NUMBER(38, 0),
  fiscal_year_date_key NUMBER(38, 0),
  form_key             NUMBER(38, 0),
  accession_number     STRING,
  cik                  NUMBER(38, 0),
  fiscal_year          NUMBER(38, 0),
  period_end           DATE,
  form_type            STRING,
  auditor_name         STRING,
  auditor_pcaob_id     STRING,
  auditor_location     STRING,
  icfr_attestation     BOOLEAN,
  auditor_changed      BOOLEAN,
  beneish_m_score      FLOAT,
  altman_z_score       FLOAT,
  piotroski_f_score    NUMBER(38, 0),
  parser_version       STRING,
  ingested_at          TIMESTAMP_TZ
)
COMMENT = '10-K accounting flag fact per (cik, accession). Dimensional — joins COMPANY + DATE + FORM. AUDIT_FIRM dim deferred; auditor_name/auditor_pcaob_id retained as natural keys.';

BEGIN
  EXECUTE IMMEDIATE
    $$CREATE OR REPLACE PIPE $$ || $manifest_pipe_name || $$
       AUTO_INGEST = TRUE
       AWS_SNS_TOPIC = '$$ || $manifest_sns_topic_arn || $$'
       AS
       COPY INTO $$ || $manifest_inbox_table_name || $$
         (source_filename, manifest, environment, workflow_name, run_id, business_date, completed_at)
       FROM (
         SELECT
           METADATA$FILENAME,
           $1,
           $1:environment::STRING,
           $1:workflow_name::STRING,
           $1:run_id::STRING,
           TO_DATE($1:business_date::STRING),
           TO_TIMESTAMP_TZ($1:completed_at::STRING)
         FROM @$$ || $stage_name || $$/manifests/
       )
       FILE_FORMAT = (FORMAT_NAME = $$ || $manifest_file_format_name || $$)
       PATTERN = '.*run_manifest\\.json'$$;
END;
