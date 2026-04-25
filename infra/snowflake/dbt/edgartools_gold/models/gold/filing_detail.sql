{{ gold_model_config('FILING_DETAIL') }}

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
