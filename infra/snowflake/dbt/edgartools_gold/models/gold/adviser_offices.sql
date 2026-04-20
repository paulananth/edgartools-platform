{{ config(alias='ADVISER_OFFICES', materialized='dynamic_table', target_lag='DOWNSTREAM', snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')) }}

select
  fact_key,
  company_key,
  date_key,
  geography_key,
  accession_number,
  office_index,
  office_name,
  is_headquarters
from {{ source("edgartools_source", "ADVISER_OFFICES") }}
