{% macro silver_not_retired(target_table, business_key_expr, parse_sequence_expr='parse_sequence') %}
{#-
    change-propagation Ticket 35 / Ticket 05: a retired business key must
    stop being "latest" without a physical DELETE from the append-only
    landing zone. Latest retirement event per key wins; a later landing
    row (higher parse_sequence) reinstates the key.

    Layered on top of silver_model_config's target_lag = '6 hours' -- this
    anti-join is collapse logic, not a refresh-clock substitute.
-#}
not exists (
  select 1
  from (
    select
      business_key,
      parse_sequence,
      row_number() over (
        partition by business_key
        order by parse_sequence desc
      ) as rn
    from {{ source('edgartools_silver_landing', 'SILVER_LANDING_RETIREMENT') }}
    where upper(target_table) = upper('{{ target_table }}')
  ) retired
  where retired.rn = 1
    and retired.business_key = {{ business_key_expr }}
    and retired.parse_sequence > {{ parse_sequence_expr }}
)
{% endmacro %}
