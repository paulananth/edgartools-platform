{{ gold_model_config('COMPANY') }}

select
  company_key,
  cik,
  entity_name,
  entity_type,
  sic,
  sic_description,
  state_of_incorporation,
  fiscal_year_end,
  last_sync_run_id
from {{ source("edgartools_source", "COMPANY") }}
