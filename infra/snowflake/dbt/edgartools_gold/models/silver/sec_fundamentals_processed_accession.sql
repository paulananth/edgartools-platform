-- Hand-maintained. Reflects edgar_warehouse.silver_store._DDL's
-- sec_fundamentals_processed_accession table (fundamentals-daily-integration
-- map, Ticket 02 / duckdb-retirement-cutover Ticket 17).

{{ silver_model_config('SEC_FUNDAMENTALS_PROCESSED_ACCESSION') }}

select
    mode,
    accession_number,
    processed_at
from {{ source('edgartools_silver_landing', 'SEC_FUNDAMENTALS_PROCESSED_ACCESSION') }}
qualify row_number() over (
    partition by mode, accession_number
    order by parse_sequence desc
) = 1
  and {{ silver_not_retired('sec_fundamentals_processed_accession', "concat_ws('|', mode, accession_number)") }}
