# 04 — Bronze/Silver isolation mechanism

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

Today's `bootstrap-batch` has no way to capture *only* company-identity data
separately from ownership (Form 3/4/5) and ADV — all three are dispatched
together via `get_parser()` within one task
(`edgar_warehouse/application/warehouse_orchestrator.py`,
`_run_submissions_bronze_then_silver`). 13F and `entity-facts` are already
excluded from that dispatch and live in the separate `bootstrap-fundamentals`
command/task.

Once tickets 01 and 02 settle exactly what data this pipeline captures,
decide the mechanism: a new CLI scope flag on `bootstrap-batch` (e.g.
`--capture-scope company-identity`), a new dedicated command (parallel to how
`bootstrap-fundamentals` already exists as a separate Branch B command), or
something else. Consider: should this new capture path share the existing
silver DuckDB shard model, or does company-identity's different cadence
(daily-refreshable, not a one-time historical backfill) argue for its own
storage/checkpoint shape?

## Blocked by

01, 02

## Answer

Add a new `--mode company-identity` to the existing `bootstrap-fundamentals`
command (not a new `bootstrap-batch` flag, not a wholly new command) —
`bootstrap-fundamentals` is already structured as a mode-dispatch Branch B
command (`per-filing`/`entity-facts`/`thirteenf`), each mode a self-contained
capture path sharing the unified SEC silver DuckDB and existing CIK-windowing
logic. The new mode runs `_sync_reference_data` (once globally, not per-CIK)
plus `_capture_submissions_main`'s metadata capture for the CIK window (per
ticket 01's answer). No new storage/checkpoint shape — shares the same
silver DuckDB and Silver-Once Idempotency (parser_version/sha256-based skip)
that already makes daily re-runs cheap; the daily cadence is an
orchestration/scheduling concern, not a storage-format one.
