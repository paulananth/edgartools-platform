{{ config(alias='FILING_DETAIL', materialized='dynamic_table', target_lag='DOWNSTREAM', snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')) }}

select
  filing_key,
  accession_number,
  cik,
  company_key,
  form,
  form_key,
  filing_date,
  date_key,
  report_date,
  is_xbrl,
  size
from {{ source("edgartools_source", "FILING_DETAIL") }}
