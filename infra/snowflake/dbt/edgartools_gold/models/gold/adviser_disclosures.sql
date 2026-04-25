{{ gold_model_config('ADVISER_DISCLOSURES') }}

select
  fact_key,
  company_key,
  date_key,
  disclosure_category_key,
  accession_number,
  event_index,
  is_reported
from {{ source("edgartools_source", "ADVISER_DISCLOSURES") }}
