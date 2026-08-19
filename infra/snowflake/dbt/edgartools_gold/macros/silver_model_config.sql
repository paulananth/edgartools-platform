{% macro silver_model_config(alias_name) %}
{#-
    silver-snowflake-migration map, Ticket 13: target_lag was 'DOWNSTREAM'
    (Ticket 01's original design), which only refreshes a dynamic table when
    another Snowflake dynamic/materialized object reads it -- an ad hoc SQL
    client (MDM's SnowflakeSilverReader, Ticket 12) never counts as one, so
    with no real downstream dynamic table yet (gold's own cutover is weeks
    away, Ticket 09's dual-write bound), these 30 tables never auto-refreshed
    on any schedule at all (31 model files total; `sec_guidance_fact_reject`
    is the one deliberate plain VIEW this macro doesn't apply to). Fixed
    target_lag matches the identical tradeoff
    CLAUDE.md already documents for SNOWFLAKE_RUN_MANIFEST_TASK at this same
    layer of this same pipeline (1min -> 15min -> 6hr, credit economy over
    near-real-time freshness) -- 6 hours chosen for the same reason, per
    Ticket 08's cost estimate (~$4/month at this cadence for all 30 tables).
    Revisit if gold's cutover later makes 'DOWNSTREAM' meaningful again.
-#}
  {{ config(
    alias=alias_name,
    materialized='dynamic_table',
    target_lag='6 hours',
    snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')
  ) }}
{% endmacro %}
