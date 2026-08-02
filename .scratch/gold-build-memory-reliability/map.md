# Gold-Build Memory Reliability

## Destination

Close out the OOM-failure class in the shared gold-build path (`build_gold()` and its callers)
that has now caused at least five recorded prod incidents, most recently `daily_incremental`'s
first-ever production execution (`daily-incremental-1785336584`, 2026-07-30) exhausting all
3 retries with an identical `OutOfMemoryError` mid-`sec_thirteenf_holding`. Every ticket here
implements a fix already diagnosed by a `/gof-refactor-reviewer` pass this session — this map
carries execution, not open design decisions (see Notes).

## Notes

- **This map carries execution.** Unlike most wayfinder maps, its tickets are implementation
  tasks, not decision points — each finding already has a reviewed root cause and a recommended
  fix. Use `/tdd` and `/code-review` per this repo's standard `/implement` flow when picking up
  a ticket here.
- Domain: `edgar_warehouse/serving/gold_models.py` (`build_gold`, `write_gold_to_storage_manifest`),
  `edgar_warehouse/application/warehouse_orchestrator.py` (`GOLD_AFFECTING_COMMANDS` + the
  build/write/export caller at lines ~462-536), `infra/scripts/deploy-aws-application.sh`
  (`workflow_profile()`, `register_task_definition` memory values).
- Source review: `/gof-refactor-reviewer` pass on 2026-07-30, triggered by the live
  `daily_incremental` OOM incident. Findings cited git evidence of four prior incidents
  (`d885c73`, `37c3171`, `1e05677`, `9bac02d`) before this one — a repeated-change axis, not a
  one-off.
- Related but out of this map's scope: the release-readiness map's full-chain launch gate and
  GO packet tickets assume gold/silver pipelines run to completion; this map is what makes that
  assumption hold for `daily_incremental` specifically. Not touching MDM/graph reliability here.

## Decisions so far

<!-- Closed ticket decisions — one-line gist + link; detail lives in the ticket. -->

- [Stream build_gold() per table instead of materializing the whole gold layer](issues/01-stream-build-gold-per-table.md) — implemented on `claude/gold-build-streaming` (not yet merged/deployed): `iter_gold_tables()` generator + per-table write/export helpers replace the eager whole-dict build; peak-memory reduction reasoned from CloudWatch evidence but not yet empirically confirmed in prod — that's expected to land via ticket 03's redeploy. Also moved `db.record_gold_manifest` to a per-table idempotent upsert inside the loop (this resolved the fog item below about incremental manifest recording — a real behavior change caught during review, not left for later).
- [Link GOLD_AFFECTING_COMMANDS membership to required task-profile sizing](issues/02-link-gold-affecting-commands-to-task-sizing.md) — added `tests/architecture/test_gold_affecting_commands_task_sizing.py`. Surfaced that `GOLD_AFFECTING_COMMANDS` members resolve through **three different real dispatch paths**, not one: (1) `bootstrap-full`/`targeted-resync`/`full-reconcile`/`gold-refresh` (standalone) go through `workflow_profile()`'s case statement — the only path the test's first version actually checked; (2) **`bootstrap`/`daily-incremental` never call `workflow_profile()` at all** — its cases for them are dead code, and their real `RunWarehouseTask` step (the one that OOM'd) is wired directly in `write_warehouse_mdm_gold_definition`, discovered only while deploying ticket 03's fix and requiring the test to be rewritten to generate that function's real JSON instead; (3) `bootstrap-next` is hardcoded inside `load_history`'s state machine, bypassing both. Also found `gold-refresh` itself runs on two profiles depending on caller (standalone → `workflow_profile()`; every composite pipeline's embedded step → `large` directly) — invisible only because the two shared 4096MB before ticket 03.
- [Decide the task-memory fix to unblock the failed daily_incremental execution](issues/03-decide-task-memory-fix-to-unblock-daily-incremental.md) — Raised `large` 4096→8192MB and fixed `run_wh`'s hardcoded medium-ARN dispatch (the real bug ticket 02 also found). Confirmed 2026-08-02 via CloudWatch on the already-terminal `bootstrap-ticket03-verify-1785426021` (SUCCEEDED): `sec_thirteenf_holding`'s `gold_table_completed` fired for the first time ever (6,799,919 rows, no OOM) on the 8192MB `large` profile — the discriminating signal this ticket named as its own success bar.

## Not yet specified

- Whether `bootstrap`/`full_reconcile` (also `medium`, also in `GOLD_AFFECTING_COMMANDS`, per
  ticket 02's finding) have ever actually run at full-universe scale — if not, they carry the
  same latent risk as `daily_incremental` did before this incident, but there's no incident
  evidence yet to ticket a fix against.
- `validate_data_quality.py`'s `_check_gold_vs_silver` still calls `build_gold()` (the
  whole-dict form) directly — it needs random access across the full gold layer (checking
  each table in `_DIRECT_GOLD_SILVER_TABLES` against silver row counts), so ticket 01
  deliberately left it alone. It carries the same eager-materialization memory risk ticket 01
  just fixed for `GOLD_AFFECTING_COMMANDS`, but isn't in that set and has no incident evidence
  yet — not sharp enough to ticket until it actually OOMs or a real need to fix it surfaces.
- Ticket 02's architecture test validates all three real dispatch paths now (see the updated
  Decisions-so-far entry) but still doesn't inspect the composite pipelines' embedded
  `wh_large_arn`/`wh_medium_arn` direct-wiring for `gold-refresh` (see ticket 02's second
  finding). Not sharp enough to ticket yet since nothing is actually at risk today (they all
  use `large`); would sharpen into a ticket if that direct-wiring is ever found drifted.

## Out of scope

- Re-litigating whether `daily_incremental` should be narrowed in scope (CIK/window selection).
  That's release-readiness's ticket 45 (`decide-narrow-daily-incremental-stage0-and-cadence`) —
  a different axis (which companies get processed) from this map's axis (how much memory the
  gold-build step needs regardless of scope).
