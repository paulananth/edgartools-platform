{{ gold_model_config('TICKER_REFERENCE') }}

select
  cik,
  ticker,
  exchange,
  last_sync_run_id
from {{ source("edgartools_source", "TICKER_REFERENCE") }}
