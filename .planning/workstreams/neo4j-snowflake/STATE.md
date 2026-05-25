---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: Neo4j Snowflake Native App Migration
status: planning
stopped_at: Milestone initialized
last_updated: "2026-05-25T00:00:00-04:00"
last_activity: 2026-05-25 -- Milestone v1.3 started
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State - neo4j-snowflake

## Current Position

Phase: Not started
Plan: —
Status: Ready to plan Phase 1
Last activity: 2026-05-25 -- Milestone v1.3 roadmap initialized

Progress: [----------] 0% (Neo4j Snowflake Native App Migration milestone)

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

## Blockers

- Live Marketplace app availability, Snowflake account privileges, and app role grant details must
  be confirmed in Phase 1 before implementation phases.
- `gsd-sdk` was not available on PATH from this shell during milestone initialization, so docs were
  written directly instead of through SDK helpers.

## Pending Todos

None.

## Session Continuity

Last session: 2026-05-25
Stopped at: Milestone initialized
Resume file: .planning/workstreams/neo4j-snowflake/ROADMAP.md
