# 12 — DuckDB Retirement Cleanup

**CORRECTED SCOPE (2026-09-13):** implementation found this ticket's original premise
false for its two largest items. See "Corrected scope" section below for the full
evidence and what actually shipped. Original text preserved for history:

**What to build (ORIGINAL, now superseded):** Once [Ticket 11](11-post-cutover-reconciliation-gate.md)'s
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

## Corrected scope (2026-09-13)

Before editing any production code, verified each checklist item against live callers
rather than trusting the premise. Two of the five original items do not hold:

1. **`silver_store.py`/`silver_protection.py`'s DuckDB code is NOT dead — it's the live
   merge engine.** `SilverDatabase.merge_financial_facts` (and every sibling merge
   method) executes real DuckDB-specific SQL (temp staging tables, `QUALIFY ROW_NUMBER()
   OVER (...)`, `ON CONFLICT ... DO NOTHING`) on every `bootstrap-fundamentals` write --
   the exact code path that OOM-crashed 3 times in `daily-incremental-retry-1789236915`
   hours before this ticket was picked up. No replacement engine is designed anywhere.
   Split into its own ticket: [Ticket 20](20-decide-silver-store-merge-engine-fate.md).
2. **`ShardedSilverReader` is deliberately kept alive**, not dead code -- its own
   docstring says it exists so `verify-silver-parity`/`verify-resolver-input-parity` have
   a live DuckDB reader to compare against Snowflake, and [Ticket 19](
   19-sec-company-ticker-cross-store-divergence.md) (open) needs exactly that comparison.
   Not touched.
3. **`migrate_silver_shards.py`'s own comments explicitly argue against deleting it** --
   preserves an operator's ability to migrate an older, pre-cutover monolith's real
   historical rows. Not touched.
4. **S3 lifecycle disposition split out**: irreversible against shared prod data, and
   blocked on Ticket 19 (which needs the live DuckDB-vs-Snowflake comparison to still
   exist). Split into [Ticket 21](21-apply-duckdb-file-lifecycle-disposition.md).
5. **`duckdb` cannot come out of `pyproject.toml`/`uv.lock`** -- still a hard runtime
   dependency of the still-live merge engine. Blocked on Ticket 20's resolution.

**What actually shipped in this ticket:** one confirmed-dead pair of functions,
`_publish_shard_if_remote`/`_publish_shard_if_remote_with_retry` (`warehouse_orchestrator.py`)
— zero real callers anywhere (verified via grep, not assumed), the write-side counterpart
to a shard-hydration read path that parity tooling still legitimately uses. Both
already-`@unittest.skip`-marked tests explaining exactly this shape
(`tests/architecture/test_sibling_path_symmetry.py`) were deleted alongside, per their own
skip-reason text ("Delete this test alongside the dead function in Ticket 12, not
before"). `tests/unit/test_publish_shard_if_remote.py` (11 cases, entirely scoped to the
deleted function) deleted. `tests/unit/test_sharding.py` updated to drop its now-invalid
patch target. Also corrected a stale/false docstring claim in
`_publish_silver_database_if_remote` that said `merge_candidate_into_canonical` was fully
dead -- it has a live caller in `application/silver_event_reducer.py:165` that the
original claim never checked. Removed now-unused `tempfile`/`merge_candidate_into_canonical`
imports.

**Blocked by:** [Ticket 11](11-post-cutover-reconciliation-gate.md) — resolved 2026-09-12 (GO)

**Status:** resolved (2026-09-13) — narrow, verified-safe slice shipped; remaining scope
split into [Ticket 20](20-decide-silver-store-merge-engine-fate.md) (merge-engine fate,
blocks the `duckdb` dependency removal) and [Ticket 21](21-apply-duckdb-file-lifecycle-disposition.md)
(S3 lifecycle disposition, blocked on Ticket 19). Note: Ticket 09's original concern
(bulk-write methods with no SQLite equivalent) is now folded into Ticket 20 rather than
this ticket, since those methods turned out to be the live merge engine, not dead code.

- [x] `_publish_shard_if_remote`/`_publish_shard_if_remote_with_retry` (confirmed zero
      live callers) deleted, along with their now-obsolete tests
- [ ] `silver_store.py`/`silver_protection.py`'s DuckDB-specific code — NOT deleted, moved
      to [Ticket 20](20-decide-silver-store-merge-engine-fate.md) (live merge engine, not
      dead code)
- [ ] `ShardedSilverReader`'s DuckDB implementation — NOT deleted, deliberately kept for
      Ticket 19's parity check
- [ ] The shared shard-file *read* infrastructure — NOT deleted, still used by
      `mdm/cli.py`'s parity-check path; the *write* side (`_publish_shard_if_remote`) is
      deleted (see above)

      **Update 2026-09-14:** silver-merge-engine-migration
      [Ticket 08](../../silver-merge-engine-migration/issues/08-delete-sharded-reader-and-parity-tooling.md)
      deleted the parity commands, `mdm/cli.py`'s DuckDB reader path and the shard-hydrate
      helpers. Ticket 19 and Ticket 21 name `table-reconcile`, which never used them.
      `ShardedSilverReader` now survives only for `backfill-silver-landing-historical` and
      leaves with it in that map's Ticket 09.
- [ ] DuckDB file lifecycle disposition — moved to
      [Ticket 21](21-apply-duckdb-file-lifecycle-disposition.md), blocked on Ticket 19
- [ ] `grep -r "import duckdb" edgar_warehouse/` / `tests/` returning zero results —
      moved to [Ticket 20](20-decide-silver-store-merge-engine-fate.md), not achievable
      until the merge-engine question resolves
- [ ] `duckdb` removed from `pyproject.toml`/`uv.lock` — moved to
      [Ticket 20](20-decide-silver-store-merge-engine-fate.md)
- [x] Full test suite green for the slice that did ship
