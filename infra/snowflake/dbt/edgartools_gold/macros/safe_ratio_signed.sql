{% macro safe_ratio_signed(numerator_col, denominator_col) %}
    case
        when {{ numerator_col }} is not null
         and {{ denominator_col }} is not null
         and {{ denominator_col }} > 0
        then {{ numerator_col }} / {{ denominator_col }}
    end
{% endmacro %}
