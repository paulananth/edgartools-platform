# 06 — Daily mode state machine shape and relationship to existing daily_incremental

Type: grilling
Status: resolved
Blocked by: 03, 04

## Question

Design the daily incremental mode. Today's `daily_incremental` state machine
is a single non-batched task (`RunWarehouseTask`) followed by the standard
monolithic MDM chain (MdmRun → MdmBackfill → MdmExport → MdmSync → MdmVerify
→ GoldRefresh) — all domains bundled, no entity-type scoping.

Decide:

1. Does Company Identity's daily mode run as a **new, separate** EventBridge
   schedule/state machine (leaving `daily_incremental` untouched, continuing
   to handle ownership + ADV as it does today), with an explicit ordering
   guarantee that it completes before `daily_incremental` starts each day?
2. Or does `daily_incremental` itself get restructured into
   Company → Ownership → ADV phases, matching the bulk-mode split — making
   this pipeline a phase *within* a redesigned `daily_incremental` rather
   than a wholly separate schedule?

This decision should also resolve the map's "Not yet specified" item on
`daily_incremental`'s future shape.

## Blocked by

03, 04

## Answer

Option 2: `daily_incremental` is restructured into a Company phase followed
by the existing pipeline, not a wholly separate schedule. Decisive factor:
`edgartools-prod-daily-incremental` has **zero executions ever** in prod
(confirmed via `aws stepfunctions list-executions`) — there is no live
production cadence at risk from restructuring it, so the "keep
`daily_incremental` untouched" argument for Option 1 doesn't apply here.

- **Shape:** the new company-identity stage reuses ticket 05's exact
  windowed capture (same `ComputeWindows` + windowed-Map machinery, same
  per-window `bootstrap-fundamentals --mode company-identity
  --cik-offset/--cik-limit` command, same `MaxConcurrency=1`, same strict
  failure handling), positioned before the existing `RunWarehouseTask`
  (`daily-incremental` warehouse command) / MDM chain. This is a real
  structural addition to `daily_incremental` — it currently has no
  `ComputeWindows`/window-batching machinery at all (it's a single
  non-batched task) — not a one-line insert.
- **Why reuse the full windowed universe scan rather than scope to "today's
  filers":** a single unwindowed task processing the full tracked universe
  sequentially (potentially 12,000+ CIKs, each requiring a `submissions.json`
  fetch) would take hours, not minutes, per CLAUDE.md's own "Long-load
  5-whys" — this is exactly the throughput problem windowing/distribution
  exists to solve. Scoping to "CIKs that filed today" was considered and
  declined: it would require exposing that CIK list as a new shared
  Step-Functions artifact (today it's resolved inside
  `daily-incremental`'s own task execution, not as a separate state) — more
  new machinery than reusing ticket 05's already-designed windowed capture.
  Re-scanning unchanged CIKs daily is acceptably cheap now: the EXCEPT-based
  delta fix (TODOS.md "windowed publish OOM 5-whys") means unchanged rows
  never reach the merge, and SEC's own `submissions.json` fetch is already
  cache-hit-if-unchanged via the existing bronze idempotency check.
- **MDM/graph and gold-refresh:** unchanged from `daily_incremental`'s
  existing shape — the same single `mdm run --entity-type all` → backfill →
  export → sync → verify → gold-refresh chain already resolves companies
  (`run_all()` calls `run_companies()`) and refreshes gold once, now that
  company silver data lands before it in the same execution.
- **Scope of the restructure:** `daily_incremental` only. `bootstrap`
  (recent-filings-only mode) shares the same generator function
  (`write_warehouse_mdm_gold_definition`) but is explicitly untouched — the
  map's destination does not name it, and this ticket's question was scoped
  to `daily_incremental` specifically.

This resolves the map's "Not yet specified" item on `daily_incremental`'s
future shape: it is restructured into phases (Option 2), consistent with
ticket 05's bulk-mode decision, rather than left untouched behind a
separate new schedule (Option 1).
