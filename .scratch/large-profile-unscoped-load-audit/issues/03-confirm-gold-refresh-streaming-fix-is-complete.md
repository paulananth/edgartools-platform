# 03 — Confirm gold-refresh's streaming fix is the complete story for the unscoped-load shape

Type: task
Status: open

## Question

`gold-refresh` runs on `large` at every one of its several call sites
(standalone `gold_refresh` workflow, and embedded in `bootstrap-full`/
`targeted-resync`/`full-reconcile`/`load_history`/`bronze_seed_silver_gold`
and others — 6+ distinct `ecs_state(wh_large_arn, "States.Array('gold-refresh'...")`
call sites in `deploy-aws-application.sh`). The gold-build-memory-reliability
map already fixed `build_gold()`'s whole-dict materialization via
`iter_gold_tables()` streaming (ticket 01) and confirmed live via
CloudWatch that `sec_thirteenf_holding`'s build no longer OOMs (ticket 03).

Confirm this is the *complete* picture for the unscoped-load shape
specifically, not just the streaming-materialization shape that map
targeted. Check:
- `write_gold_to_storage_manifest`/`write_gold_to_serving_export` (the two
  callers gold-build-memory-reliability's own notes say made "two more
  full passes over that same dict" before the streaming fix) — confirm
  both are now genuinely per-table incremental, not just the outer
  `build_gold()` call.
- Whether any single gold table's own builder function (`_build_*` in
  `edgar_warehouse/serving/gold_models.py`/`source_dimensional_export.py`)
  does an unscoped full-table read internally that the streaming fix
  wouldn't catch (streaming bounds *which tables* are held in memory at
  once, not necessarily *how much* one table's own builder reads before
  writing).
- Whether `validate_data_quality.py`'s continued use of the non-streaming
  `build_gold()` (the one remaining caller gold-build-memory-reliability's
  notes mention) is itself a live risk on `large`, or runs somewhere with
  enough headroom to not matter.

If this confirms the existing fix is complete, record that explicitly as
the answer — a confirmation is a valid, useful outcome here, not just a
new fix. If a gap is found, fix it the same way MANAGES_FUND/
INSTITUTIONAL_HOLDS were.

## Blocked by

None — can start immediately.
