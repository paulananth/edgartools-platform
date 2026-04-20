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
from {{ source("edgartools_source", "SNOWFLAKE_REFRESH_STATUS") }}
qualify row_number() over (
  partition by environment, source_workflow
  order by updated_at desc, run_id desc
) = 1
