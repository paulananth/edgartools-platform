-- Create the Snowflake-native manifest stream and per-run refresh status table.
--
-- Required session variables:
--   set database_name = 'EDGARTOOLS_DEV';
--   set source_schema_name = 'EDGARTOOLS_SOURCE';
--   set deployer_role_name = 'EDGARTOOLS_DEV_DEPLOYER';
--   set manifest_inbox_table_name = 'SNOWFLAKE_RUN_MANIFEST_INBOX';
--   set manifest_stream_name = 'SNOWFLAKE_RUN_MANIFEST_STREAM';
--   set status_table_name = 'SNOWFLAKE_REFRESH_STATUS';

USE ROLE IDENTIFIER($deployer_role_name);
USE DATABASE IDENTIFIER($database_name);
USE SCHEMA IDENTIFIER($source_schema_name);

CREATE TABLE IF NOT EXISTS IDENTIFIER($status_table_name) (
  environment STRING NOT NULL,
  source_workflow STRING NOT NULL,
  run_id STRING NOT NULL,
  business_date DATE,
  manifest_completed_at TIMESTAMP_TZ,
  source_load_status STRING NOT NULL,
  refresh_status STRING NOT NULL,
  status STRING NOT NULL,
  source_row_count NUMBER(38, 0),
  tables_loaded NUMBER(38, 0),
  error_message STRING,
  last_successful_refresh_at TIMESTAMP_TZ,
  updated_at TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (environment, source_workflow, run_id)
)
COMMENT = 'Per-run Snowflake mirror status for EdgarTools source loads and gold refreshes.';

BEGIN
  EXECUTE IMMEDIATE
    'CREATE OR REPLACE STREAM ' || $manifest_stream_name || '
       ON TABLE ' || $manifest_inbox_table_name || '
       APPEND_ONLY = TRUE';
END;
