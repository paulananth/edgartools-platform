{{ config(alias='COMPANY', materialized='dynamic_table', target_lag='DOWNSTREAM', snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')) }}

select
  company_key,
  cik,
  entity_name,
  entity_type,
  sic,
  sic_description,
  state_of_incorporation,
  fiscal_year_end,
  last_sync_run_id
from {{ source("edgartools_source", "COMPANY") }}
