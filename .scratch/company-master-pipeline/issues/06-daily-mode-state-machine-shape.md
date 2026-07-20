# 06 — Daily mode state machine shape and relationship to existing daily_incremental

Type: grilling
Status: open
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
