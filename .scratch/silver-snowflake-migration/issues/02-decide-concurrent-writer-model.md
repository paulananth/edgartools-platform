# Decide the Concurrent-Writer Model for Snowflake-Native Silver

Type: grilling
Status: claimed
Blocked by: 01

## Question

Does Snowflake's native `MERGE`/transactions fully replace today's app-level
ETag-optimistic-concurrency promotion-and-retry mechanism
(`_publish_silver_database_with_retry`, built specifically after a
2026-07-22 incident where concurrent Distributed Map batches all tried to
publish the same monolithic file and only the first ever won), or does
dbt's own incremental-model refresh semantics introduce a comparable new
conflict class under concurrent writers that needs its own handling?

Once answered: does `MaxConcurrency:1` — currently forced on `load_history`'s
`WindowedBootstrap` specifically to avoid the promotion race this
architecture exists to eliminate — get safely relaxed, and if so to what,
and under what evidence (mirrors `pipeline-throughput-architecture` ticket
12's live-tested-not-assumed discipline for exactly this class of question).
