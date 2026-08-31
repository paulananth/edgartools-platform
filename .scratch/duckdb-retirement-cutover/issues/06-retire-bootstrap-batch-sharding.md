# 06 — Retire `bootstrap-batch`'s CIK-Sharded DuckDB Hydrate/Publish Mechanism

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

**Status:** done

- [x] `bootstrap-batch`'s CIK-sharded DuckDB hydrate/publish code path is
      removed from `warehouse_orchestrator.py` — `_execute_warehouse_bronze_capture`'s
      `_using_shard_path`/`_active_shard_index` branch (the `command_name ==
      "bootstrap-batch"` shard-detection, `_read_shard_manifest`/
      `_hydrate_shard_for_window`/`open_silver_shard` hydrate-open sequence, and the
      `_publish_shard_if_remote_with_retry` publish branch) is deleted outright. Every
      command, `bootstrap-batch` included, now unconditionally hydrates/opens/publishes the
      one monolith silver database via `_hydrate_silver_database_from_storage`/
      `_open_silver_database`/`_publish_silver_database_with_retry` — the same path every
      other command already used. `_planned_pipeline_writes` lost its now-always-`None`
      `shard_index` parameter and its dead `silver_shard` manifest-layer branch along with it.
- [x] The shared `shard-{0-3}.duckdb` file infrastructure is **left dead pending Ticket
      12's final sweep**, deliberately, not removed here — `_read_shard_manifest`,
      `_hydrate_shard_for_window`, and `open_silver_shard` are still real, live call targets
      for other, unrelated consumers: `edgar_warehouse/mdm/cli.py` and
      `edgar_warehouse/silver_landing_company_backfill.py` (via `_hydrate_all_shards`) both
      still iterate every shard directly (`edgar_warehouse/mdm_entity_backfill.py` was
      checked too but is already Snowflake-only per its own docstring — not a shard
      consumer), and `load_history`'s own CIK-batch interleaving
      (`_write_cik_universe_batches`/`_shard_partition_ciks`/`band_for_cik`) still reads the
      shard manifest for scheduling, unrelated to `bootstrap-batch`'s write path. Only
      `bootstrap-batch` itself stops being one of this mechanism's callers, exactly as
      DuckDB Retirement's own Ticket 04 (wayfinder decision) scoped it: "this ticket only
      decides that bootstrap-batch itself should stop being one of that mechanism's
      callers." `_publish_shard_if_remote`/`_publish_shard_if_remote_with_retry` do become
      fully dead in production now (their one production call site is gone), but are left
      defined — they're small, isolated, and still covered by their own dedicated tests
      (`tests/unit/test_publish_shard_if_remote.py`,
      `tests/architecture/test_sibling_path_symmetry.py`) that Ticket 12's sweep can delete
      alongside the function bodies in one pass.
- [x] `bootstrap-batch` still writes to the Snowflake landing zone correctly with the
      sharding code removed — the landing-zone write (`write_landing_export`, driven by the
      same `landing_export` buffer regardless of which silver database was opened) was never
      inside the removed block; it's unconditional in `_execute_warehouse_bronze_capture`
      after the try block completes, untouched by this change. Confirmed via the full test
      suite, not just by inspection.
- [x] `BOOTSTRAP_BATCH_CONCURRENCY`'s new ceiling — **measured, and it is not what this
      ticket's own framing above assumed.** `deploy-aws-application.sh` was checked directly
      (not assumed): `BOOTSTRAP_BATCH_CONCURRENCY` actually only ever reaches `MaxConcurrency`
      for ONE of `bootstrap-batch`'s three ECS/Step-Functions callers —
      `write_silver_mdm_gold_definition`'s `BatchSilver` Map (`silver_mdm_gold`,
      `--artifact-policy skip`, live default 3). The task profile for that Map is confirmed
      `medium` (`register_task_definition medium 1024 4096` — 1 vCPU/task), and the account's
      live Fargate On-Demand vCPU quota is confirmed 30 vCPU (`aws service-quotas
      get-service-quota --service-code fargate --quota-code L-3032A538`, 2026-08-31) — a
      genuine, measured 30-task theoretical ceiling from the vCPU-quota angle alone, exactly
      as this ticket's framing predicted. **But that number turns out not to be the real
      binding constraint.** `write_bronze_seed_silver_gold_definition`'s own `strict_batch_map`
      — a *different* `bootstrap-batch` caller, writing the identical monolith `silver.duckdb`
      object via the identical `_publish_silver_database_with_retry`/ETag-guarded-promote
      mechanism `bootstrap-batch` now also uses — documents in its own committed comment that
      concurrent monolith-object promotion "hit \[PromotionConflictError\] repeatedly at
      MaxConcurrency=4," which is why it was lowered to 2 on 2026-07-22. Retiring the shard
      mechanism removes a real, if indirect, conflict-avoidance property: 4 separate shard
      files gave concurrent `BatchSilver` batches roughly a 1-in-4 chance of colliding with
      each other; one shared monolith object gives every concurrent batch a collision with
      every other one. Documented in CLAUDE.md's `BOOTSTRAP_BATCH_CONCURRENCY` bullet:
      recommend holding the current default (3) rather than raising toward either the old
      2–5 range's upper end or the 30-vCPU ceiling, since the closest available production
      evidence for this exact write pattern shows conflicts becoming frequent right around
      where this caller's default already sits. Raising it further is left as explicit
      future work for an operator, gated on either re-measuring monolith-promotion-conflict
      frequency at higher concurrency directly, or reintroducing some form of writer
      partitioning for this specific Map — not attempted in this ticket.
- [x] Full test suite green — 2854 passed, 5 skipped (matches this branch's pre-existing
      baseline; the 2 excluded Postgres-integration tests are unrelated to this change).
      mypy: zero new errors on `warehouse_orchestrator.py` (25 pre-existing both before and
      after, confirmed via a `git stash` diff against the same baseline).

**Three-axis review (Standards/Spec/GoF, CLAUDE.md hard rule):** Standards — clean, no
violations. Spec — implementation matches the checklist fully; one real finding: this
ticket file's own draft note in the second checklist item misattributed a still-live
shard-infra caller to `mdm_entity_backfill.py` (that module is already Snowflake-only per
its own docstring, unrelated to `bootstrap-batch`'s cutover this ticket); the real second
caller is `edgar_warehouse/mdm/cli.py` — fixed above. GoF — one real finding:
`tests/architecture/test_sibling_path_symmetry.py`'s
`test_monolith_and_shard_retry_wrappers_reference_the_same_env_vars` now guards a dead
sibling (`_publish_shard_if_remote_with_retry`, zero remaining production callers after
this ticket) against a live one (`_publish_silver_database_with_retry`), which would force
edits to dead code every time the monolith retry wrapper's env vars change with no live
divergence risk left to actually catch. Fixed by skipping that one test with a reason
pointing at this ticket and Ticket 12 (which should delete it alongside the dead function),
leaving the class's other test (`merge_candidate_into_canonical` presence check) untouched
since it's stable and not at the same risk.
