-- Create the MDM Snowflake Postgres instance with Snowflake CLI credentials.
--
-- Templated by environment via Snow CLI's Jinja substitution (-D flags).
-- Required variables: instance_name, network_policy, comment_env.
-- The referenced network_policy must already exist (see
-- mdm_create_network_policy.sql) before this script runs.
--
-- Run with (dev):
--   snow sql --connection snowconn --filename infra/snowflake/postgres/mdm_create_instance.sql \
--     -D "instance_name=EDGARTOOLS_DEV_MDM" \
--     -D "network_policy=edgartools_dev_mdm_postgres_policy" \
--     -D "comment_env=dev"
--
-- Run with (prod):
--   snow sql --connection edgartools-prod --filename infra/snowflake/postgres/mdm_create_instance.sql \
--     -D "instance_name=EDGARTOOLS_PROD_MDM" \
--     -D "network_policy=edgartools_prod_mdm_postgres_policy" \
--     -D "comment_env=prod"
--
-- Update the compute family, storage size, and network policy values above
-- before running in a new environment. Capture the generated snowflake_admin
-- and application credentials out of band; Snowflake does not show them
-- again after creation.

CREATE POSTGRES INSTANCE {{ instance_name }}
  COMPUTE_FAMILY = 'BURST_S'
  STORAGE_SIZE_GB = 50
  AUTHENTICATION_AUTHORITY = POSTGRES
  POSTGRES_VERSION = 16
  HIGH_AVAILABILITY = FALSE
  NETWORK_POLICY = '{{ network_policy }}'
  COMMENT = 'EdgarTools MDM Snowflake Postgres runtime database ({{ comment_env }})';

DESCRIBE POSTGRES INSTANCE {{ instance_name }};
