---
phase: 01-snowflake-native-app-feasibility-and-architecture-decision
plan: 01
subsystem: snowflake-native-app
tags: [snowflake, neo4j, native-app, marketplace, runbook]

requires: []
provides:
  - Native App operator feasibility and install runbook
  - Least-privilege Snowflake application role and data grant checklist
  - Live-account validation checklist for Marketplace app activation
affects:
  - Phase 1 Plan 01-02 architecture decision
  - Phase 1 Plan 01-03 graph projection contract
  - Phase 2 Snowflake graph sync contract

tech-stack:
  added: []
  patterns:
    - Workstream-local operator runbook
    - Snowflake application roles plus database roles for Native App access

key-files:
  created:
    - .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md
  modified: []

key-decisions:
  - "Use the Snowflake Marketplace Neo4j Graph Analytics Native App as the Phase 1 target assumption."
  - "Require review or narrowing before using broad upstream example grants such as ALL PRIVILEGES."
  - "Reject external Neo4j Bolt credential flow for this milestone's Native App validation path."

patterns-established:
  - "Operator runbooks should document the Snowflake role, privilege, validation command, and expected outcome for each Native App step."
  - "Phase 1 artifacts remain inside .planning/workstreams/neo4j-snowflake and do not mutate implementation code."

requirements-completed: [DISC-01, SNOW-01, ISO-01, ISO-02]

duration: 1h 27m
completed: 2026-05-26
---

# Phase 1 Plan 01: Native App Runbook Summary

**Snowflake Marketplace Neo4j Graph Analytics runbook with least-privilege app grants, compute validation, event sharing, and live-account checks**

## Performance

- **Duration:** 1h 27m
- **Started:** 2026-05-26T01:19:56Z
- **Completed:** 2026-05-26T02:46:57Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `01-NATIVE-APP-RUNBOOK.md` for the Neo4j Graph Analytics Native App install and activation path.
- Documented required application privileges, consumer roles, database role grants, compute pool selector checks, app warehouse expectations, event sharing, and failure modes.
- Kept the artifact workstream-local and explicitly rejected external Neo4j credentials and non-AWS deployment assumptions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Draft the Native App operator runbook** - `e8f08bb` (docs)

## Files Created/Modified

- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md` - Operator feasibility, installation, privilege, compute, warehouse, and validation runbook.

## Decisions Made

- Used `Neo4j_Graph_Analytics` as the documented default application name until a live operator chooses otherwise.
- Treated `Neo4j_Graph_Analytics.app_user` and `Neo4j_Graph_Analytics.app_admin` as separate consumer-role grants so algorithm users do not need app administration rights.
- Required broad example grants such as `ALL PRIVILEGES` to be narrowed or separately reviewed before use in this platform.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required by this documentation-only plan.

## Known Stubs

None. Operator placeholders such as `EDGARTOOLS_<ENV>` and `<privileged_role>` are intentional runbook parameters, not unimplemented behavior.

## Threat Flags

None. This plan added planning documentation only and did not introduce new network endpoints, auth code paths, file access patterns, or schema changes.

## Verification

- `test -f .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md` passed.
- `rg -n "Neo4j_Graph_Analytics\\.app_user|Neo4j_Graph_Analytics\\.app_admin|CREATE COMPUTE POOL|CREATE WAREHOUSE|CPU_X64_XS|Neo4j_Graph_Analytics_app_warehouse" .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md` passed.
- `rg -n "Azure|Container Apps|NEO4J_URI|NEO4J_PASSWORD" .planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md` returned only explicitly rejected assumptions.
- Required section heading and source URL checks passed.

## Next Phase Readiness

Ready for Plan 01-02 to record the architecture decision for direct migration to the Snowflake Native App target and Snowflake-managed graph access.

## Self-Check: PASSED

- Created file exists: `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md`.
- Task commit exists: `e8f08bb`.
- Verification commands above passed.

---
*Phase: 01-snowflake-native-app-feasibility-and-architecture-decision*
*Completed: 2026-05-26*

