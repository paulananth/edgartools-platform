-- Create the MDM Snowflake Postgres instance with Snowflake CLI credentials.
--
-- Run with:
--   snow sql --connection snowconn --filename infra/snowflake/postgres/mdm_create_instance.sql
--
-- Update the instance name, compute family, storage size, and network policy
-- before running. Capture the generated snowflake_admin and application
-- credentials out of band; Snowflake does not show them again after creation.

CREATE POSTGRES INSTANCE EDGARTOOLS_DEV_MDM
  COMPUTE_FAMILY = 'BURST_S'
  STORAGE_SIZE_GB = 50
  AUTHENTICATION_AUTHORITY = POSTGRES
  POSTGRES_VERSION = 16
  HIGH_AVAILABILITY = FALSE
  NETWORK_POLICY = 'edgartools_dev_mdm_postgres_policy'
  COMMENT = 'EdgarTools MDM Snowflake Postgres runtime database';

DESCRIBE POSTGRES INSTANCE EDGARTOOLS_DEV_MDM;
