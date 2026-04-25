{{ gold_model_config('PRIVATE_FUNDS') }}

select
  fact_key,
  company_key,
  date_key,
  private_fund_key,
  accession_number,
  fund_index,
  aum_amount
from {{ source("edgartools_source", "PRIVATE_FUNDS") }}
