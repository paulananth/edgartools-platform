# Verify Snowflake incremental change-processing primitives

Type: research
Status: resolved
Blocked by: none

## Question

Against current official Snowflake documentation, which primitives and limits
must the design account for when ingesting immutable delta files, expressing
row retirement or scoped replacement, refreshing only affected dbt silver/gold
descendants, and proving a run-bound publication barrier?

Determine specifically:

1. `COPY INTO` file-identity/history behavior when a key is overwritten or a
   retry produces corrected content.
2. Streams/tasks/dynamic-table behavior for inserts, updates, deletes, and
   append-only sources.
3. `MERGE` support and transactional boundaries for upsert/delete publication.
4. When dynamic tables refresh incrementally versus full recomputation, how
   that choice is observed, and whether a caller can refresh a bounded affected
   DAG rather than the whole graph.
5. Which native status/history surfaces can support an immutable
   Change-Propagation-Run barrier and aligned Decision Watermark.

Use primary sources only. Save the findings at
`.scratch/change-propagation/research/snowflake-incremental-primitives.md` and
link every material claim to its official source.

## Answer

[Snowflake incremental change-processing primitives](../research/snowflake-incremental-primitives.md)
finds that Snowflake supports immutable-file landing, CDC streams,
transactional `MERGE`, and bounded multi-table dynamic-table refresh, but no
single native primitive provides an atomic, run-bound barrier across them.

Use content-addressed files and explicit lifecycle events; one stream per
consumer; deterministic target-plus-outcome DML transactions; and an externally
selected dynamic-table closure verified at one shared `DATA_TIMESTAMP`.
Persist the actual refresh action and work statistics. The durable
Change-Propagation-Run ledger remains authoritative for Decision Watermark
publication because native histories have retention/latency limits and
multi-table refresh can publish partially.
