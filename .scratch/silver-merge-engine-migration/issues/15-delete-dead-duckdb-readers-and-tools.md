# 15 — Delete the remaining DuckDB readers and tools

**Type:** task

**Status:** resolved in code 2026-09-15.

## Question

Delete, with their tests: `application/silver_event_reducer.py` (Out of scope on the map; leaves
with the engine), `application/commands/migrate_silver_shards.py`, `silver_support/sharded_reader.py`
and `silver_landing_historical_backfill.py` (its last user), the `table_reconciliation` package
(`table-reconcile` hydrates `silver.duckdb`; cutover Ticket 21's delete markers land within a day of
2026-09-14 20:29 ET, so it fails to hydrate before this slice runs — expected), and the five
`scripts/ops` DuckDB diagnostics (`check-issued-by-coverage.py`, `check-neo4j-e2e.py`,
`diagnose-mdm-run.py`, `diagnose-silver-anomalies.py`, `verify-counts.py`). Remove
`MDM_SILVER_DUCKDB` (`--mdm-silver-duckdb`, its default, the MDM task environment and the
`silver_duckdb` definition field) from `deploy-aws-application.sh`; nothing reads it.
`table_reconciliation/contracts.py` is the only production importer of `PROTECTED_TABLE_REGISTRY`
outside `silver_protection.py`.

Also, per [Ticket 16](16-retire-remaining-local-store-couplings.md)'s decisions (2026-09-14): drop
the `compute-windows` reference-snapshot upload and manifest field (`persist_run_manifest`'s
`reference_snapshot_file`, `reference_snapshot_path`, the `_valid_sha256` check) together with the
dead `reduce-identity-refresh` command and the zero-caller manifest readers; and retire
`parse-ownership-bronze` (CLI parser/handler, `_run_parse_ownership_bronze`, its two test files' parts).

**Blocked by:** [Ticket 14](14-move-write-path-off-silver-database.md).

## Answer

Resolved 2026-09-15 in code, in three commits.

- **Part 1 — dead readers and tools** (6,439 lines): `application/silver_event_reducer.py`,
  `commands/migrate_silver_shards.py`, `commands/backfill_silver_landing_historical.py`,
  `silver_support/sharded_reader.py`, `silver_landing_historical_backfill.py`, the
  `table_reconciliation` package (`table-reconcile`), the five `scripts/ops` DuckDB diagnostics and
  their two shell wrappers, and their tests. CLI, command registry, orchestrator dispatch and
  `dataset_path_catalog` unwired. `MDM_SILVER_DUCKDB` removed from `deploy-aws-application.sh`
  (flag, default, MDM task env, `silver_duckdb` summary field) and `aws-dev-application.json`; no
  reader existed on `main` either. `tests/mdm/test_adv_preflight.py` gets a small DuckDB fixture
  reader in place of `ShardedSilverReader` (it leaves with the engine in Ticket 17).
- **Part 2 — `parse-ownership-bronze` retired** (Ticket 16 decision 2): CLI parser/handler, command
  module and registry entry, `_run_parse_ownership_bronze` with its dispatch and scope blocks, and
  its tests. The lookback helpers stay; they have live callers.
- **Part 3 — reference snapshot dropped, with a scope correction to Ticket 16 decision 1.**
  Ticket 16 said `reduce-identity-refresh` had no reader left. Wrong: it is still
  `daily_incremental`'s `PublishCompanyIdentityUpdates` state (`deploy-aws-application.sh`), ran in
  prod within the last 30 days, and its batch-completeness gate ("every declared batch succeeded")
  is a real fan-out-failure signal. So the command, `load_complete_run_manifest`,
  `validate_complete_run_manifest` and the `batch_*` helpers **stay**. Dropped: the
  `reference_snapshot_file` upload (the empty local DuckDB file), the manifest's `reference_snapshot`
  field and its sha256/path check, and `reference_snapshot_path`. The orchestrator records the run
  manifest itself as the write (`layer: identity_refresh_run_manifest`). `schema_version` stays 1:
  both writer and reader ship in one deploy. Ticket 16's answer is corrected in place.
- **Review cleanups** (three-axis `/code-review`; GoF's one finding, scattered command registration
  across 5–7 files with 8 co-changes in three weeks, is deferred until after Ticket 17 when the
  ladders are smallest): stale mentions fixed in `CLAUDE.md`, `CONTEXT.md` (the Identity Reference
  Snapshot term removed), `snowflake_reader.py`, `silver_store.py`, the orchestrator's
  `merge_candidate_into_canonical` docstring (now zero callers), four test docstrings and
  `scripts/ops/backfill-issued-by.py`. `scripts/verify-pr2/` deleted: both scripts were already
  dead on `main` (they import the long-renamed `gold_models` and grep for shard helpers deleted
  weeks ago). The orchestrator uses `run_manifest_path()` instead of a hardcoded path.
- Full suite (integration excluded): 3370 passed; the drop from 3468 is the deleted tests.
