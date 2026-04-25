{{ gold_model_config('ADVISER_OFFICES') }}

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
