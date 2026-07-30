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

- [Stream build_gold() per table instead of materializing the whole gold layer](issues/01-stream-build-gold-per-table.md) — implemented on `claude/gold-build-streaming` (not yet merged/deployed): `iter_gold_tables()` generator + per-table write/export helpers replace the eager whole-dict build; peak-memory reduction reasoned from CloudWatch evidence but not yet empirically confirmed in prod — that's expected to land via ticket 03's redeploy.

## Not yet specified

- Whether the same streaming fix (ticket 01) should also change how `db.record_gold_manifest`
  aggregates the end-of-run manifest — today it's a single call over the full manifest list;
  a fully incremental `build_gold` may want incremental manifest recording too. Not sharp enough
  to ticket until ticket 01 is underway and the actual caller shape is being rewritten.
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

## Out of scope

- Re-litigating whether `daily_incremental` should be narrowed in scope (CIK/window selection).
  That's release-readiness's ticket 45 (`decide-narrow-daily-incremental-stage0-and-cadence`) —
  a different axis (which companies get processed) from this map's axis (how much memory the
  gold-build step needs regardless of scope).
