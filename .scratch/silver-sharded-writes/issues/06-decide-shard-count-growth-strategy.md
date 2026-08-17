# Decide Shard-Count Growth Strategy

Type: grilling
Status: open
Blocked by: 01

## Question

**Scope note (post ticket 05):** the map's destination narrowed to just
`load_history`'s `WindowedBootstrap` and `bootstrap_fundamentals.py`'s three
Stage 1B modes — `daily_incremental`/`bootstrap` are out of scope, as is
per-table shard-boundary risk beyond `sec_raw_object`/`sec_company_filing`
(both resolved to full replication in ticket 05). This ticket is unaffected
in substance by the narrowing — shard count is a property of the CIK-range
scheme itself, not of which commands write through it.

The current scheme has 4 shards (`shard-{0..3}.duckdb`), routed by CIK
range. Is 4 adequate for the foreseeable universe size (currently 51,888
companies), or should this map plan for growth now? Depends on ticket 01's
findings about the routing scheme's mechanics: does adding a 5th shard
require a full re-split of all existing data (expensive, matches
`migrate_silver_shards.py`'s one-time-op framing), or can new CIK ranges be
carved out incrementally without touching already-sharded data? If the
former, decide whether to over-provision shard count now (cheaper to do
once, before primary commands depend on the current count) or accept a
future resharding effort as a separate, later problem.

## Deliverable

A decision: target shard count for this rollout, and whether resharding
capability is in scope for this effort or explicitly deferred.
