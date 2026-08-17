{% macro date_key(date_expr) %}
{#-
    dbt-gold-silver-rewiring map, Ticket 03: the YYYYMMDD integer date-key
    encoding every rewired dimensional model (date_key, filing_date_key,
    period_end_date_key) uses. NOT a hash -- this is plain date arithmetic,
    identical in DuckDB and Snowflake, so unlike surrogate_key() it carries
    no cross-engine portability concern and needs no key-reset decision.
    NULL input propagates to NULL output naturally (year()/month()/day() of
    NULL is NULL in Snowflake), matching gold_models.py's
    _filing_date_to_int(None) -> None.
-#}
(year({{ date_expr }}) * 10000 + month({{ date_expr }}) * 100 + day({{ date_expr }}))::integer
{% endmacro %}
