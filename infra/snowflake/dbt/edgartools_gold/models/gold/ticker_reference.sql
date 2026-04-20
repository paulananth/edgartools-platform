{{ config(alias='TICKER_REFERENCE', materialized='dynamic_table', target_lag='DOWNSTREAM', snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')) }}

select
  cik,
  ticker,
  exchange,
  last_sync_run_id
from {{ source("edgartools_source", "TICKER_REFERENCE") }}
