# 02 — Audit bootstrap-full/targeted-resync/full-reconcile/bootstrap/daily-incremental/bootstrap-next for the unscoped-load shape

Type: task
Status: open

## Question

These six commands (`bootstrap-full`, `targeted-resync`, `full-reconcile`,
`bootstrap`, `daily-incremental`, `bootstrap-next`) all resolve to `large`
via `command_task_profile()` and funnel through shared
`warehouse_orchestrator.py` code paths (bronze/silver capture,
`SOURCE_EXPORT_COMMANDS` gold build). Audit for the MANAGES_FUND-shape
risk — unscoped full load of a shared table/dataset before scoping is
known — that is **not already covered** by an existing resolved map.

Known-covered ground (don't re-litigate, but do confirm each still
actually applies to the current code, since maps can go stale):
- `gold-refresh`'s `build_gold()` full-materialization risk — fixed by
  `iter_gold_tables()` streaming (gold-build-memory-reliability, ticket 01).
- `daily_incremental`'s task-sizing gap that caused the original
  `sec_thirteenf_holding` OOM — fixed (gold-build-memory-reliability,
  ticket 03; task-profile-consolidation).
- `bootstrap-next`'s artifact-fetch throttle/idempotency gaps — fixed
  (artifact-throttle 5-whys, bronze-recovery-with-no-DB-row 5-whys, both
  in CLAUDE.md).

What's genuinely unaudited for *this specific* shape (an unscoped ORM/DB
hydration before scoping — the MANAGES_FUND pattern, not a DuckDB/S3
buffering pattern): whether any of these six commands' silver-write or
MDM-adjacent code paths (e.g. `mdm_entity_backfill.py`'s
`BackfillMdmEntityIds` step, wired into both `daily_incremental` and
`bootstrap`) load an unbounded set of rows/entities before knowing which
subset the current run actually touches. Check
`edgar_warehouse/mdm_entity_backfill.py` specifically — it's the one
MDM-Postgres-adjacent piece embedded in these six commands' state
machines and has never been checked against this shape.

If a genuine gap is found, fix it the same way MANAGES_FUND/
INSTITUTIONAL_HOLDS were (batch-scope, release-between-batches,
red-before-green test). If nothing new is found, record that explicitly
with the evidence checked — a clean bill of health is a valid, useful
answer here.

## Blocked by

None — can start immediately.
