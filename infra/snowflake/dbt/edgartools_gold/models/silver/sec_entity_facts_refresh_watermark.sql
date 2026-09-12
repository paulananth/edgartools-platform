-- Hand-maintained. Reflects edgar_warehouse.silver_store._DDL's
-- sec_entity_facts_refresh_watermark table (fundamentals-daily-integration
-- map, Ticket 03 / duckdb-retirement-cutover Ticket 17).

{{ silver_model_config('SEC_ENTITY_FACTS_REFRESH_WATERMARK') }}

select
    cik,
    entity_facts_refreshed_at
from {{ source('edgartools_silver_landing', 'SEC_ENTITY_FACTS_REFRESH_WATERMARK') }}
qualify row_number() over (
    partition by cik
    order by parse_sequence desc
) = 1
  and {{ silver_not_retired('sec_entity_facts_refresh_watermark', 'cik') }}
