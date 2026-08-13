# Design the Snowflake-Native Silver Layer's Model Structure

Type: grilling
Status: claimed
Blocked by: none

## Question

How does data flow from bronze through Snowflake-native silver to gold once
Python's SEC-document parsing (unavoidable — see map Notes) lands rows in a
new Snowflake landing zone instead of a local `silver.duckdb`?

Specify: the landing-zone schema (raw parsed rows, pre-clean/dedupe) versus
final silver table shape; which existing silver tables (per
`edgar_warehouse/silver_store.py`) map to incremental dbt models versus
snapshot-style models, given SEC filings are additive/immutable once
captured (per CLAUDE.md's "SEC data idempotency" policy — silver's
clean/dedupe logic must still express that same immutability guarantee in
dbt/Snowflake terms); how bronze's existing native-S3-pull-into-SOURCE
pattern does or doesn't extend to silver's landing zone (silver's raw input
requires Python parsing first, unlike SOURCE's already-structured parquet);
and where the CIK-scoped/company-scoped partitioning that today's shard
manifest (`edgar_warehouse/application/sharding/`) provides gets expressed,
if at all, once Snowflake's storage model replaces file-based sharding.

This is the map's priority ticket — `load_history`'s retry6 is blocked on
this ticket reaching a locked answer, not on the full migration being
built.
