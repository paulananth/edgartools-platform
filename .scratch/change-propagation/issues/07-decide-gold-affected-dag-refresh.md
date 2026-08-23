# Decide gold affected-DAG refresh and status semantics

Type: grilling
Status: open
Blocked by: 01, 02, 05

## Question

How should a completed silver publication identify, refresh, and attest only
the affected dbt gold dependency closure while retaining correct current-state
and retirement semantics?

Decide the affected-table/model mapping, whether dbt selection or Snowflake
dynamic-table refresh is authoritative, handling of the three approved
external Explore inputs, status/history evidence for incremental versus full
recomputation, failure/retry boundaries, and the gold publication identity
bound into the Decision Watermark. Resolve how the legacy Python full-snapshot
and `EDGARTOOLS_SOURCE` paths retire without duplicating the existing dbt-gold
rewiring tickets.
