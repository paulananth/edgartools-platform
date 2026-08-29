{% macro gold_model_config(alias_name) %}
{#-
    change-propagation Ticket 39, live prod 2026-08-29: every EDGARTOOLS_GOLD
    dynamic table was TARGET_LAG=DOWNSTREAM, SCHEDULING_STATE=ACTIVE, but
    DYNAMIC_TABLE_REFRESH_HISTORY for COMPANY and TICKER_REFERENCE showed
    REFRESH_TRIGGER=MANUAL only (last success 2026-08-28 via
    REFRESH_AFTER_LOAD). DOWNSTREAM refreshes a table only when another
    dynamic table reads it -- gold leaves have none, so lag never fired.
    Same trap silver-snowflake-migration Ticket 13 already fixed for
    EDGARTOOLS_SILVER. Match silver's 6 hour lag. REFRESH_AFTER_LOAD stays
    as an extra explicit trigger after a run manifest; it does not replace
    the lag clock. Ticket 39's completion barrier still fail-closes on a
    stale data_timestamp regardless of this lag.
-#}
  {{ config(
    alias=alias_name,
    materialized='dynamic_table',
    target_lag='6 hours',
    snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')
  ) }}
{% endmacro %}
