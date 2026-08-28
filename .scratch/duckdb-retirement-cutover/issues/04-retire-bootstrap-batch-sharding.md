# 04 — Retire `bootstrap-batch`'s CIK-Sharded DuckDB Hydrate/Publish Mechanism

**What to build:** DuckDB Retirement's Ticket 04 decided the CIK-sharded
DuckDB hydrate/publish mechanism (`pipeline-throughput-architecture`'s
Ticket 12, a real measured 76s→3.2s optimization at the time) retires
entirely. `bootstrap-batch` already dual-writes to the Snowflake landing
zone today, and that write is per-run Parquet with no shared mutable
object — it carries none of the write contention the shard mechanism exists
to solve.

Remove the shard hydrate/publish machinery from
`warehouse_orchestrator.py`'s `bootstrap-batch` path and the shared
`shard-{0-3}.duckdb` file infrastructure. Reprocessing under the Snowflake
landing zone's append-only + latest-`parse_sequence`-wins collapse still
does useful work (a parser-fix rerun genuinely changes content, it doesn't
just re-emit duplicates) — this ticket removes the DuckDB sharding
mechanism, not the reprocessing capability itself.

`MaxConcurrency` for `bootstrap-batch`'s Distributed Map stops being
contention-bounded (there's no shard file left to promote) and becomes
Fargate-vCPU-quota-bounded instead — the exact new ceiling is deferred to
implementation-time tuning per Ticket 04's own decision; don't guess a
number here, measure it against the real Fargate task profile during this
ticket's work.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `bootstrap-batch`'s CIK-sharded DuckDB hydrate/publish code path is
      removed from `warehouse_orchestrator.py`
- [ ] The shared `shard-{0-3}.duckdb` file infrastructure (S3 keys,
      promotion/merge logic specific to shards) is removed or left dead
      pending [Ticket 10](10-duckdb-retirement-cleanup.md)'s final sweep
- [ ] `bootstrap-batch` still writes to the Snowflake landing zone
      correctly with the sharding code removed (no regression in the
      dual-write path that was already live)
- [ ] `BOOTSTRAP_BATCH_CONCURRENCY`'s new ceiling is measured against real
      Fargate vCPU quota for the task profile in use, not assumed, and the
      new recommended range is documented in CLAUDE.md alongside (or
      replacing) the existing 2–5 guidance, which was sized for the old
      shard-contention constraint
- [ ] Full test suite green
