{{ config(alias='OWNERSHIP_HOLDINGS', materialized='dynamic_table', target_lag='DOWNSTREAM', snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')) }}

select
  fact_key,
  company_key,
  date_key,
  party_key,
  security_key,
  accession_number,
  owner_index,
  shares_owned_after,
  ownership_direct_indirect
from {{ source("edgartools_source", "OWNERSHIP_HOLDINGS") }}
