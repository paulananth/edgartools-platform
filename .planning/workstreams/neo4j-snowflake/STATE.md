---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: Neo4j Snowflake Native App Migration
status: executing
stopped_at: Completed 01-01-PLAN.md
last_updated: "2026-05-26T02:46:57Z"
last_activity: 2026-05-26 -- Completed Plan 01-01 Native App operator runbook
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 3
  completed_plans: 1
  percent: 33
---

# Project State - neo4j-snowflake

## Current Position

Phase: 1 (Snowflake Native App Feasibility And Architecture Decision) — EXECUTING
Plan: 2 of 3
Status: Ready for Plan 01-02
Last activity: 2026-05-26 -- Completed Plan 01-01 Native App operator runbook

Progress: [███-------] 33% (Neo4j Snowflake Native App Migration milestone)

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

## Blockers

- Live Marketplace app availability, Snowflake account privileges, and app role grant details must
  be confirmed during Phase 1 execution before implementation phases.

## Pending Todos

None.

## Session Continuity

Last session: 2026-05-26
Stopped at: Completed 01-01-PLAN.md
Resume file: .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-02-PLAN.md
