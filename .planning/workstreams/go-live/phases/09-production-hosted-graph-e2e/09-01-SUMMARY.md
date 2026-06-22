---
phase: 09-production-hosted-graph-e2e
plan: 01
subsystem: mdm
tags: [snowflake, native-app, mdm, hosted-graph, prod]

# Dependency graph
requires:
  - phase: 07-production-snowflake-native-pull-and-gold
    provides: production Snowflake/dbt readiness
  - phase: 08-production-mdm-secrets-and-connectivity
    provides: production MDM secrets, migration, grants, and connectivity
provides:
  - Production Native App graph prerequisites for EDGARTOOLS_PROD
  - First-time EDGARTOOLS_PROD.MDM mirror load evidence and runbook
  - Bounded production sync-graph pass
  - Strict production verify-graph pass with Native App checks enabled
affects: [09-production-hosted-graph-e2e, 10-production-dashboard-uat, 11-final-go-decision-and-launch-evidence-handoff]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - secret-safe production evidence capture
    - bounded graph materialization
    - first-time Snowflake MDM mirror bootstrap from Snowflake Postgres

key-files:
  created:
    - docs/prod-mdm-snowflake-graph-first-load.md
    - .planning/workstreams/go-live/phases/09-production-hosted-graph-e2e/09-01-SUMMARY.md
  modified:
    - .planning/workstreams/go-live/phases/09-production-hosted-graph-e2e/evidence/hosted-graph-local.md
    - .planning/workstreams/go-live/STATE.md
    - .planning/workstreams/go-live/ROADMAP.md

key-decisions:
  - "Phase 8 remains complete and was not rerun; Phase 9 consumed existing production MDM secrets only inside non-printing shell invocations."
  - "Production Native App and runtime grants were applied only after operator approval, targeting EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION."
  - "The missing EDGARTOOLS_PROD.MDM mirror was resolved through an explicitly approved first-time load from the existing Snowflake Postgres MDM database."
  - "Blocker 4 remains open until Phase 9 Plan 09-02 passes production AWS MDM E2E and reconciles the launch matrix."

patterns-established:
  - "Secret-safe evidence records statement categories, counts, and check statuses, not raw connector output or full generated JSON."
  - "Hosted graph acceptance is bounded sync-graph followed by strict verify-graph with Native App checks enabled."

requirements-completed: [GRAPH-03, SEC-02, ISO-03]

# Metrics
duration: ~1h50min
completed: 2026-06-22
---

# Phase 9 Plan 1: Production Hosted Graph Local Verification Summary

**Production Snowflake-hosted MDM graph path now passes bounded local materialization and strict Native App verification.**

## Performance

- **Duration:** ~1h50min across approval checkpoints
- **Started:** 2026-06-21T22:35:10Z
- **Completed:** 2026-06-22T00:24:51Z
- **Tasks:** 4
- **Files modified:** 5

## Accomplishments

- Confirmed Phase 7 Snowflake/dbt and Phase 8 MDM readiness before any graph writes.
- Applied production Native App graph prerequisites and runtime-role grants after operator approval.
- Documented and executed the approved first-time `EDGARTOOLS_PROD.MDM` mirror load.
- Ran bounded `sync-graph --limit 100`; it materialized 10 nodes and 0 edges.
- Ran strict `verify-graph --native-app-compute-pool CPU_X64_XS`; SQL parity and Native App checks passed.

## Task Commits

1. **Task 1: Preflight Phase 7/8 completion, secret metadata, and Native App metadata** - `aa632d0` (docs).
2. **Task 2: Operator approval checkpoint** - `a610aa0` (docs).
3. **Task 3: Apply prod Native App graph grants and compute-pool readiness** - `d8e5b7c` (docs).
4. **Task 4: Run bounded local MDM smoke if needed, sync graph, and strict verify** - `94c10c1`, `4ef41ba`, `3bb099c`, `8bb5ceb`, `0e3a748` (docs).

**Plan metadata:** this summary commit.

## Files Created/Modified

- `docs/prod-mdm-snowflake-graph-first-load.md` - first-time production MDM Snowflake mirror load and graph deploy runbook.
- `.planning/workstreams/go-live/phases/09-production-hosted-graph-e2e/evidence/hosted-graph-local.md` - full secret-safe evidence, including failed checkpoints and final pass.
- `.planning/workstreams/go-live/STATE.md` - current position advanced to Plan 09-02.
- `.planning/workstreams/go-live/ROADMAP.md` - Plan 09-01 marked complete and next step updated.

## Decisions Made

- Keep Phase 8 as the source of truth and do not rerun production MDM secret bootstrap.
- Use `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION` as the production graph schema.
- Grant only the additional runtime and Native App application-role access required for local graph sync and strict verification.
- Treat the local strict verify pass as GRAPH-03 proof, while keeping Blocker 4 open until AWS MDM E2E passes in 09-02.

## Deviations from Plan

The original plan anticipated `sync-graph` would be able to read existing `EDGARTOOLS_PROD.MDM` mirror objects. It instead found an empty mirror schema after runtime-role grants were fixed.

Operator-approved deviations:

1. Applied minimum runtime grants for `EDGARTOOLS_PROD_DEPLOYER` after the first bounded sync failed with a privilege class.
2. Performed the first-time `EDGARTOOLS_PROD.MDM` mirror load after the second bounded sync found no current source objects.
3. Granted Native App `app_user` and `app_admin` application roles to the runtime role after strict verify proved the graph tables but could not see all app context.

These deviations were required to reach the documented acceptance gate and remained within the AWS/Snowflake-only, bounded, secret-safe scope.

## Issues Encountered

All Plan 09-01 issues were resolved:

- Native App graph schema and database role were initially missing or not visible; production-scoped grants fixed this.
- Runtime role lacked MDM and graph privileges; minimum runtime grants fixed this.
- `EDGARTOOLS_PROD.MDM` had no current source tables/views; the approved first-time mirror load fixed this.
- Runtime role lacked local Native App application-role visibility; app-role grants fixed this.

## User Setup Required

None for Plan 09-01. Production changes were applied during execution after explicit approvals.

## Next Phase Readiness

Ready for Phase 9 Plan 09-02:

- Do not redo Phase 8.
- Do not redo Plan 09-01 Native App grants, runtime grants, first-time mirror load, or local strict verify.
- Run production AWS MDM E2E through the Snowflake-hosted graph path.
- Reconcile Blocker 4 launch matrix rows only after AWS E2E passes.

---
*Phase: 09-production-hosted-graph-e2e*
*Completed: 2026-06-22*

## Self-Check: PASSED

- VERIFIED: `hosted-graph-local.md` records preflight, grants, bounded sync-graph, first-time mirror load, and strict verify-graph sections.
- VERIFIED: strict verify passed with SQL parity and Native App compute_pool, graph_info, BFS, and WCC checks enabled.
- VERIFIED: targeted evidence/runbook scan found no credential leak patterns, raw connector traces, raw Native App logs, or full generated JSON.
- VERIFIED: Plan 09-01 summary exists and Phase 9 now resumes at Plan 09-02.
