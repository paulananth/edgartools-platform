{% macro gold_model_config(alias_name) %}
  {% if target.type == 'snowflake' %}
    {{ config(
      alias=alias_name,
      materialized='dynamic_table',
      target_lag='DOWNSTREAM',
      snowflake_warehouse=env_var('DBT_SNOWFLAKE_WAREHOUSE')
    ) }}
  {% else %}
    {{ config(
      alias=alias_name,
      materialized=env_var('DBT_DATABRICKS_GOLD_MATERIALIZED', 'table')
    ) }}
  {% endif %}
{% endmacro %}
