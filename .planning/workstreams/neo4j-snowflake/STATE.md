---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: Neo4j Snowflake Native App Migration
status: ready_to_execute
stopped_at: Phase 2 planning complete
last_updated: "2026-05-26T13:31:59.680Z"
last_activity: 2026-05-26 -- Phase 2 planning complete
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 6
  completed_plans: 3
  percent: 25
---

# Project State - neo4j-snowflake

## Current Position

Phase: 2 (Snowflake Graph Sync Contract) - PLANNED
Plan: 3 plans ready
Status: Ready to execute
Last activity: 2026-05-26 -- Phase 2 planning complete

Progress: [##--------] 25% (Phase 1 complete; Phase 2 planned; milestone v1.3 remains in progress)

## Milestone Context

Move Neo4j from an external Neo4j service into the Snowflake Marketplace Neo4j Graph
Analytics Native App. Keep `edgar-warehouse` as the owner of MDM graph sync and verification
commands. Reuse existing source/gold Snowflake models where possible; only graph location and
projection surfaces should change.

## Decisions

- The Neo4j target is the Snowflake Marketplace / Native App flow.
- This milestone is a production migration path with a feasibility and architecture decision first.
- `edgar-warehouse mdm sync-graph` remains the command surface for graph sync.
- External Neo4j is not retained as a parallel validation target for this milestone.
- Graph credentials/configuration should come from Snowflake-managed application roles, grants,
  and connection context rather than external `NEO4J_*` secrets.

- Required proof includes matching node/edge counts, exact relationship parity, query-level graph
  traversal checks, dashboard comparison, and an end-to-end AWS pipeline run.

- The existing MDM Neo4j review dashboard must be updated to inspect the hosted graph target.

- Plan 01-01 documents the Native App runbook with the default application name
  `Neo4j_Graph_Analytics`, application roles `app_user` and `app_admin`, required
  privileges `CREATE COMPUTE POOL` and `CREATE WAREHOUSE`, event sharing, compute selector
  `CPU_X64_XS`, and app warehouse `Neo4j_Graph_Analytics_app_warehouse`.

- Broad upstream example grants such as `ALL PRIVILEGES` require narrowing or explicit
  operator review before use in this platform.

- Plan 01-02 records the accepted architecture decision that the Snowflake Marketplace Neo4j
  Graph Analytics Native App replaces the external Neo4j target for this milestone, while
  `edgar-warehouse mdm sync-graph` remains the graph sync command surface.

- Plan 01-02 defines the graph credential model around Snowflake-managed app roles, database
  roles, table/view grants, warehouse or app warehouse context, and Snowflake connection
  context rather than `NEO4J_*` or `NEO4J_SECRET_JSON` milestone validation dependencies.

- Plan 01-03 defines `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES` as proposed Native App-facing
  graph projection inputs and reconciles current `GRAPH_NODES`/`GRAPH_EDGES` SQL casing with
  Native App projection fields such as `nodeId`, `sourceNodeId`, and `targetNodeId`.

- Phase 2 must review the runbook, architecture decision, graph projection contract, and
  plan-review questions before implementation; live-account items must be validated live,
  documented as operator-required, or explicitly blocked.

- Phase 1 verification passed with 21/21 must-haves verified and no human verification
  required; `DISC-04` is now marked complete in requirements traceability.

- Operator-supplied Snowflake Graph Analytics agent instructions are captured in
  `SNOWFLAKE-GRAPH-ANALYTICS-AGENT-INSTRUCTIONS.md`; Phase 2 should reconcile
  `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`, `GRAPH_NODE_*`, `GRAPH_EDGE_*`, available
  compute pools, and algorithm result tables with the Phase 1 graph projection contract.

- Phase 2 planning produced three executable plans: `02-01` for graph projection SQL,
  `02-02` for the Snowflake graph sync executor, and `02-03` for `edgar-warehouse mdm
  sync-graph` CLI wiring.

## Blockers

- Live Marketplace app availability, Snowflake account privileges, and app role grant details must
  be confirmed in a real Snowflake account before implementation can be treated as production-ready.

## Pending Todos

None.

## Session Continuity

Last session: 2026-05-26T13:31:59.680Z
Stopped at: Phase 2 planning complete
Resume file: .planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract/02-01-PLAN.md
