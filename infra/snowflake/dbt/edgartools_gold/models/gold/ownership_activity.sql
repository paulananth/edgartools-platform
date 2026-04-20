{{ config(alias='OWNERSHIP_ACTIVITY', materialized='dynamic_table', target_lag='DOWNSTREAM', snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')) }}

select
  fact_key,
  company_key,
  date_key,
  form_key,
  party_key,
  security_key,
  ownership_txn_type_key,
  accession_number,
  owner_index,
  txn_index,
  transaction_code,
  transaction_shares,
  transaction_price,
  shares_owned_after,
  is_derivative
from {{ source("edgartools_source", "OWNERSHIP_ACTIVITY") }}
