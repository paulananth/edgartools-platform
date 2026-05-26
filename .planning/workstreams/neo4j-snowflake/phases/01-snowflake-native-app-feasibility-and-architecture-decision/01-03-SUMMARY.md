---
phase: 01-snowflake-native-app-feasibility-and-architecture-decision
plan: 03
subsystem: snowflake-native-app
tags: [snowflake, neo4j, native-app, graph-projection, plan-review]

requires:
  - phase: 01-01
    provides: Native App operator feasibility and install runbook
  - phase: 01-02
    provides: Snowflake Native App graph target architecture decision
provides:
  - Graph projection contract for Native App-facing MDM node and edge inputs
  - Phase 2 plan-review checklist for privileges, projection, verification, and credential migration
affects:
  - Phase 2 Snowflake Graph Sync Contract
  - Phase 3 Hosted Graph Verification And E2E Cutover
  - Phase 4 Dashboard Hosted Graph Migration

tech-stack:
  added: []
  patterns:
    - Workstream-local graph projection contract
    - Source-grounded plan-review checklist

key-files:
  created:
    - .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-GRAPH-PROJECTION-CONTRACT.md
    - .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-PLAN-REVIEW-QUESTIONS.md
  modified: []

key-decisions:
  - "Phase 2 must reconcile current `GRAPH_NODES`/`GRAPH_EDGES` SQL with Native App-facing `nodeId`, `sourceNodeId`, and `targetNodeId` expectations."
  - "MDM relationship source of truth remains `mdm_relationship_type` plus `mdm_relationship_instance`."
  - "Phase 2 must not start until the runbook, ADR, and graph projection contract are reviewed."

patterns-established:
  - "Graph projection contracts cite current source tables, generated SQL, and tests before prescribing implementation changes."
  - "Live-account unknowns are labeled as planning risks rather than treated as validated implementation facts."

requirements-completed: [DISC-04, SNOW-01, ISO-01, ISO-02]

duration: 38min
completed: 2026-05-26
---

# Phase 1 Plan 03: Graph Projection Contract Summary

**Snowflake Native App graph projection contract and Phase 2 plan-review checklist**

## Performance

- **Duration:** 38 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `01-GRAPH-PROJECTION-CONTRACT.md` with required sections for purpose, current MDM source of truth, existing Snowflake graph SQL, proposed schema, node and edge input contracts, Native App projection example, verification mapping, ownership/cleanup, and Phase 2 handoff.
- Mapped the current MDM graph source of truth from `mdm_relationship_type` and `mdm_relationship_instance`, including `source_entity_id`, `target_entity_id`, `properties`, `source_system`, `source_accession`, `graph_synced_at`, `is_active`, `idx_rel_instance_dedup`, and seeded relationship types.
- Reconciled the existing `GRAPH_NODES`/`GRAPH_EDGES` generated SQL shape with the Native App-facing `nodeId`, `sourceNodeId`, and `targetNodeId` spelling required by the milestone contract.
- Created `01-PLAN-REVIEW-QUESTIONS.md` to gate Phase 2 planning around Marketplace availability, event sharing, privileges, database role grants, app roles, compute-pool selector availability, projection naming, verification, and removal of external `NEO4J_*` milestone assumptions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define the Snowflake graph projection contract** - `2bfdde3` (docs)
2. **Task 2: Capture plan-review convergence questions** - `664752b` (docs)

## Files Created/Modified

- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-GRAPH-PROJECTION-CONTRACT.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-PLAN-REVIEW-QUESTIONS.md`

## Decisions Made

- Phase 2 can choose tables, views, or compatibility views for `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES`, but must deliberately preserve or update existing `tests/mdm/test_snowflake_graph_migration.py` assertions.
- `graph_synced_at` remains a required field in the contract until Phase 2 explicitly decides whether it is the Snowflake materialization watermark or is replaced by a Snowflake-specific status model.
- Live account details, including Marketplace availability and compute-pool selector support, remain operator-validation items and are not claimed as already applied.

## Deviations

- The first delegated executor stalled without durable output. The orchestrator closed that agent and executed this plan inline on the main worktree, preserving the required atomic commits.

## Verification

- `test -f 01-GRAPH-PROJECTION-CONTRACT.md`
- `rg -n "Existing MDM Graph Source Of Truth|Existing Snowflake Graph Migration Surface|MDM_GRAPH_NODES|MDM_GRAPH_EDGES|GRAPH_NODES|GRAPH_EDGES|NODEID|SOURCENODEID|TARGETNODEID|nodeId|sourceNodeId|targetNodeId|mdm_relationship_type|mdm_relationship_instance|idx_rel_instance_dedup|graph_synced_at|defaultTablePrefix|relationshipTables" 01-GRAPH-PROJECTION-CONTRACT.md`
- `test -f 01-PLAN-REVIEW-QUESTIONS.md`
- `rg -n "Marketplace|event sharing|CREATE COMPUTE POOL|CREATE WAREHOUSE|database role|future table|app role|compute-pool selector|NEO4J_\\*" 01-PLAN-REVIEW-QUESTIONS.md`
- `git diff --check`

## Self-Check: PASSED

- All plan tasks were completed.
- Required artifacts were created under the `neo4j-snowflake` workstream.
- No source code, Terraform, generated deployment JSON, or sibling workstream artifacts were edited.
- Requirement coverage: `DISC-04`, `SNOW-01`, `ISO-01`, and `ISO-02`.
