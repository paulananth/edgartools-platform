{{ config(alias='ADVISER_DISCLOSURES', materialized='dynamic_table', target_lag='DOWNSTREAM', snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')) }}

select
  fact_key,
  company_key,
  date_key,
  disclosure_category_key,
  accession_number,
  event_index,
  is_reported
from {{ source("edgartools_source", "ADVISER_DISCLOSURES") }}
