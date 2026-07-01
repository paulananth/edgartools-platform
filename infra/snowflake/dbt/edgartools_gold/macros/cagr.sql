-- cagr(current_col, prior_col, years): compound annual growth rate over N fiscal years.
--
-- Semantics: FY-to-FY only. Both endpoints must be strictly positive for the result
-- to be non-null. This is broader than a same-sign check by design (D-02): a
-- negative-to-negative span (e.g. net_income -100 -> -50) is mathematically computable
-- but yields a misleadingly positive CAGR for a still-unprofitable company — the same
-- class of problem Phase 2's ROE negative-equity null guard (Damodaran) already
-- established as a precedent in this codebase. Nulling on ANY non-positive endpoint
-- keeps the semantic promise of "growth between two healthy states" honest.
--
-- Negative-base defense: power() with a fractional exponent over a negative base
-- produces implementation-defined or NaN results in Snowflake (behavior is
-- undocumented). The strict-positive guard also eliminates this as defense-in-depth.
-- Do NOT weaken to a same-sign or non-zero check.
--
-- Float exponent: uses 1.0 / {{ years }} (not 1 / {{ years }}). Snowflake integer
-- division truncates 1/3 and 1/5 to zero, making power(x, 0) = 1 and every CAGR
-- silently return 0. The literal 1.0 forces floating-point division.
{% macro cagr(current_col, prior_col, years) %}
    case
        when {{ current_col }} is not null
         and {{ prior_col }} is not null
         and {{ current_col }} > 0
         and {{ prior_col }} > 0
        then power({{ current_col }} / {{ prior_col }}, 1.0 / {{ years }}) - 1
    end
{% endmacro %}
