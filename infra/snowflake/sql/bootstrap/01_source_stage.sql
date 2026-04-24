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
