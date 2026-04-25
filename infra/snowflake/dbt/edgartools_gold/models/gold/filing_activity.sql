{{ gold_model_config('FILING_ACTIVITY') }}

select
  fact_key,
  company_key,
  filing_key,
  date_key,
  form_key,
  accession_number,
  cik,
  form,
  filing_date,
  report_date,
  is_xbrl
from {{ source("edgartools_source", "FILING_ACTIVITY") }}
