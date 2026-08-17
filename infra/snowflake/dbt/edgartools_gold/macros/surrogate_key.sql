{% macro surrogate_key(field_list) %}
{#-
    dbt-gold-silver-rewiring map, Ticket 01: the uniform surrogate-key
    derivation every rewired gold model (Tickets 02-05) calls instead of
    re-deriving a key strategy per table.

    Neither of today's two Python/DuckDB-side derivations survives the
    Snowflake cutover byte-for-byte: DuckDB's `hash()` is an internal,
    undocumented algorithm with no Snowflake equivalent, and the Python
    `_det_key()` helper (first 8 bytes of SHA-256, masked positive) could in
    principle be reproduced with SHA2_BINARY, but there is no reason to pay
    that complexity when nothing outside this pipeline depends on today's
    literal key values (see the ticket's recorded consumer inventory) -- a
    same-shape reset onto Snowflake's own native HASH() is simpler and just
    as deterministic. Masked to the same positive 63-bit range
    (0x7FFFFFFFFFFFFFFF) the existing DuckDB-side keys already use, so
    downstream BIGINT columns keep an identical value range even though the
    literal values themselves are new.
-#}
bitand(hash({{ field_list | join(', ') }}), 9223372036854775807)::bigint
{% endmacro %}
