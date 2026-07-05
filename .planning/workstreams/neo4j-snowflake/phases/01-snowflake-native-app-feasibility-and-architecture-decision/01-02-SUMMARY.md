---
phase: 01-snowflake-native-app-feasibility-and-architecture-decision
plan: 02
subsystem: snowflake-native-app
tags: [snowflake, neo4j, native-app, architecture-decision, mdm]

requires:
  - phase: 01-01
    provides: Native App operator feasibility and install runbook
provides:
  - Architecture decision record for Snowflake Native App graph target migration
  - Snowflake-managed graph credential and configuration model
  - Downstream Phase 2 through Phase 4 contract for graph sync, verification, and dashboard migration
affects:
  - Phase 1 Plan 01-03 graph projection contract
  - Phase 2 Snowflake graph sync contract
  - Phase 3 hosted graph verification and E2E cutover
  - Phase 4 dashboard hosted graph migration

tech-stack:
  added: []
  patterns:
    - Workstream-local architecture decision record
    - Snowflake app roles, database roles, grants, and connection context as graph access model

key-files:
  created:
    - .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-ARCHITECTURE-DECISION.md
  modified: []

key-decisions:
  - "The Snowflake Marketplace Neo4j Graph Analytics Native App replaces external Neo4j for this milestone."
  - "edgar-warehouse mdm sync-graph remains the graph sync command surface."
  - "Milestone validation must not depend on NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, or NEO4J_SECRET_JSON."
  - "Graph access moves to Snowflake-managed app roles, database roles, table/view grants, warehouse/app warehouse context, and Snowflake connection context."

patterns-established:
  - "Phase architecture decisions must name current runtime inputs and exact downstream code paths before implementation plans change source."
  - "Legacy external graph credential references are allowed only as current-state mapping or rejected/out-of-scope language."

requirements-completed: [DISC-02, DISC-03, ISO-01, ISO-02]

duration: 4min
completed: 2026-05-26
---

# Phase 1 Plan 02: Architecture Decision Summary

**Snowflake Native App graph target ADR mapping legacy Neo4j Bolt credentials to Snowflake-managed app-role, grant, warehouse, and connection-context access**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-26T02:50:33Z
- **Completed:** 2026-05-26T02:54:09Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `01-ARCHITECTURE-DECISION.md` with the exact required ADR sections and accepted milestone-planning status.
- Mapped current `_neo4j_client()`, `NEO4J_*`, `NEO4J_SECRET_JSON`, MDM command handlers, Snowflake export settings, warehouse settings, Snowflake access grants, and AWS MDM deployment/E2E touchpoints.
- Recorded the direct migration decision: Native App replaces external Neo4j, `edgar-warehouse mdm sync-graph` remains the command surface, and no external Neo4j parallel validation target is planned.
- Defined downstream Phase 2, Phase 3, and Phase 4 obligations without changing implementation source, Terraform, dashboard files, generated JSON, or sibling workstreams.

## Task Commits

Each task was committed atomically:

1. **Task 1: Record the migration architecture decision** - `d02325c` (docs)

## Files Created/Modified

- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-ARCHITECTURE-DECISION.md` - ADR for direct migration to the Snowflake Native App target and Snowflake-managed graph access.

## Decisions Made

- Snowflake Marketplace Neo4j Graph Analytics Native App is the milestone graph target.
- The current external Neo4j credential path is legacy for this milestone and must be replaced in later phases by Snowflake app roles, database roles, grants, warehouse/app warehouse context, and Snowflake connection context.
- Existing AWS/Snowflake MDM database, export, serving export root, and Snowflake access grant settings remain in scope where valid.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

During verification, neutral current-state wording containing `external Neo4j` was tightened so the plan-level rejection scan was unambiguous. This stayed within the planned ADR file.

## User Setup Required

None - no external service configuration required by this documentation-only plan.

## Known Stubs

None. Operator names such as `Neo4j_Graph_Analytics` and future schema/table names are documented as planning assumptions or open questions, not unimplemented runtime behavior.

## Threat Flags

None. This plan added planning documentation only and did not introduce new network endpoints, auth code paths, file access patterns, or schema changes.

## Verification

- `test -f .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-ARCHITECTURE-DECISION.md` passed.
- `rg -n "Accepted for milestone planning|Current Runtime Mapping|edgar-warehouse mdm sync-graph|_neo4j_client|NEO4J_URI|NEO4J_USER|NEO4J_USERNAME|NEO4J_PASSWORD|NEO4J_DATABASE|NEO4J_SECRET_JSON|MDM_SNOWFLAKE_|DBT_SNOWFLAKE_|SERVING_EXPORT_ROOT|SNOWFLAKE_EXPORT_ROOT|no external Neo4j parallel validation" .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-ARCHITECTURE-DECISION.md` passed.
- `rg -n "non-AWS|non-AWS app runtime|dual-write|external Neo4j" .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-ARCHITECTURE-DECISION.md` passed, with matches confined to target/exclusion statements, rejected alternatives, stale-credential cleanup, and an open deprecation question.
- Acceptance checks for D-02, D-03, D-04, D-05, Snowflake-managed access, Phase 2/3/4 obligations, rejected alternatives, and preserved AWS/Snowflake settings passed.

## Next Phase Readiness

Ready for Plan 01-03 to define the graph projection contract and plan-review checklist using this ADR as the graph target, command ownership, and credential-model source of truth.

## Self-Check: PASSED

- Created file exists: `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-ARCHITECTURE-DECISION.md`.
- Task commit exists: `d02325c`.
- Stub scan found no TODO, FIXME, placeholder, coming soon, not available, or hardcoded empty-value patterns in the created ADR.
- Verification commands above passed.

---
*Phase: 01-snowflake-native-app-feasibility-and-architecture-decision*
*Completed: 2026-05-26*
