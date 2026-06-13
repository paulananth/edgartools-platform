{% macro yoy_growth(current_col, prior_col) %}
    case
        when {{ prior_col }} is not null and {{ prior_col }} <> 0
        then ({{ current_col }} - {{ prior_col }}) / {{ prior_col }}
    end
{% endmacro %}
