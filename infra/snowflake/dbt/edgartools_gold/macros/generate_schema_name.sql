{#
  Override dbt's default generate_schema_name so that a per-model `+schema`
  config is used verbatim instead of being concatenated with the profile's
  target schema. Without this override, target schema `EDGARTOOLS_GOLD` and
  per-model `+schema: EDGARTOOLS_GOLD` collapse into `EDGARTOOLS_GOLD_EDGARTOOLS_GOLD`.

  Reference: https://docs.getdbt.com/docs/build/custom-schemas
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
