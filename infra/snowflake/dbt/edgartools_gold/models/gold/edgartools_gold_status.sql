with ranked_status as (
  select
    environment,
    source_workflow,
    run_id,
    business_date,
    status,
    source_load_status,
    refresh_status,
    source_row_count,
    tables_loaded,
    last_successful_refresh_at,
    updated_at,
    row_number() over (
      partition by environment, source_workflow
      order by updated_at desc, run_id desc
    ) as status_rank
  from {{ source("edgartools_source", "SERVING_REFRESH_STATUS") }}
)

select
  environment,
  source_workflow,
  run_id,
  business_date,
  status,
  source_load_status,
  refresh_status,
  source_row_count,
  tables_loaded,
  last_successful_refresh_at,
  updated_at
from ranked_status
where status_rank = 1
