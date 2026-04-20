{{ config(alias='PRIVATE_FUNDS', materialized='dynamic_table', target_lag='DOWNSTREAM', snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')) }}

select
  fact_key,
  company_key,
  date_key,
  private_fund_key,
  accession_number,
  fund_index,
  aum_amount
from {{ source("edgartools_source", "PRIVATE_FUNDS") }}
