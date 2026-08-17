{% macro normalized_text(expr) %}
{#-
    dbt-gold-silver-rewiring map, Ticket 03: SQL equivalent of
    gold_models.py's _normalized_text() (collapse whitespace, trim, lower)
    composed with the "empty means absent" check every call site in the
    Python builders applies before hashing a natural key
    (`if normalized_category else None`, `if geography_natural_key else
    None`). Returns NULL, not '', when the input has no real content.

    Callers must still guard the surrogate_key() call itself with an
    explicit `CASE WHEN <this> IS NULL THEN NULL ELSE surrogate_key(...)
    END` (see disclosure_category_key in adviser_disclosures.sql,
    geography_key in adviser_offices.sql) -- do NOT pass this macro's
    output straight into surrogate_key() expecting a NULL input to
    propagate to a NULL key. Confirmed live that Snowflake's HASH(NULL)
    returns a real, nonzero value, not NULL (see filing_activity.sql's
    form_key comment for the same finding) -- feeding a NULL straight into
    HASH() would silently produce a bogus non-NULL key instead of
    correctly signaling "no natural key value."
-#}
nullif(lower(trim(regexp_replace(coalesce({{ expr }}, ''), '[[:space:]]+', ' '))), '')
{% endmacro %}
