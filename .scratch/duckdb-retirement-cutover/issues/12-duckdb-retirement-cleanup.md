# 12 — DuckDB Retirement Cleanup

**What to build:** Once [Ticket 11](11-post-cutover-reconciliation-gate.md)'s
human approval confirms the cutover is stable, remove the DuckDB code and
files that no longer have any live caller:

- Delete `silver_store.py`'s and `silver_protection.py`'s DuckDB-specific
  code (the `_DDL` string, DuckDB connection handling, DuckDB-dialect query
  paths) — whatever remains after Tickets 01–08 have already moved each
  consumer off it.
- Delete `edgar_warehouse/silver_support/sharded_reader.py`'s DuckDB-backed
  `ShardedSilverReader` implementation, left pending from
  [Ticket 05](05-cutover-mdm-reader-to-snowflake.md).
- Delete the shared `shard-{0-3}.duckdb` file infrastructure, left pending
  from [Ticket 06](06-retire-bootstrap-batch-sharding.md).
- Apply DuckDB file disposition for the canonical `silver.duckdb`/shard
  objects still in S3: extend the existing
  `expire-noncurrent-silver-canonical-versions` lifecycle-rule precedent —
  bounded retention on the final current version, then archive/delete
  (DuckDB Retirement's Ticket 01 answer).
- Confirm zero `import duckdb` remains anywhere in `edgar_warehouse/`
  (matching this map's Destination: "nothing in the codebase still imports
  `duckdb`").

This is deliberately the **last** ticket — deleting old code before Ticket
09's approval would remove the only known-good fallback if reconciliation
finds a problem.

**Blocked by:** [Ticket 11](11-post-cutover-reconciliation-gate.md)

**Status:** blocked

- [ ] `silver_store.py`/`silver_protection.py`'s DuckDB-specific code is
      deleted
- [ ] `ShardedSilverReader`'s DuckDB implementation is deleted
- [ ] The shared shard-file infrastructure is deleted
- [ ] DuckDB file lifecycle disposition (bounded retention → archive/delete)
      is applied to the S3-hosted canonical objects, following the existing
      `expire-noncurrent-silver-canonical-versions` precedent
- [ ] `grep -r "import duckdb" edgar_warehouse/` and `grep -r "import
      duckdb" tests/` both return zero results
- [ ] `duckdb` is removed from `pyproject.toml`/`uv.lock` if nothing else
      in the repo depends on it
- [ ] Full test suite green — this is the final confirmation that DuckDB
      Retirement's Destination has been reached
