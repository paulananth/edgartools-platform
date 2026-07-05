{% macro gold_model_config(alias_name) %}
  {{ config(
    alias=alias_name,
    materialized='dynamic_table',
    target_lag='DOWNSTREAM',
    snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')
  ) }}
{% endmacro %}
