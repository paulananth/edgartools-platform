---
phase: 04-operator-dashboard-and-data-issue-triage
plan: 02
subsystem: docs
tags: [triage, runbook, DASH-02, operator, read-only, data-issue, security]

# Dependency graph
requires:
  - phase: 04-01-operator-dashboard-and-data-issue-triage
    provides: Dashboard README rewrite and arch test gate pass
  - phase: 01-production-readiness-inventory-and-launch-gate-contract
    provides: Launch gate matrix Data-Issue Triage Table (rows 90-100) that this guide extends
  - phase: 03-mdm-hosted-graph-e2e-acceptance
    provides: MDM secrets runbook format to mirror

provides:
  - Operator data-issue triage guide covering all 8 DASH-02 layers with read-only diagnostic commands, owners, and escalation paths
  - Runbook at runbook/data-issue-triage.md extending (not duplicating) the launch gate matrix triage table

affects:
  - go-live Phase 5 (go/no-go packet)
  - any operator performing first-inspection triage during or after launch

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Operator runbook format: header disclaimer, numbered layer sections, closing References"
    - "Read-only diagnostic commands only in runbook bash blocks (D-14)"
    - "Placeholder tokens <DB>/<conn>/<role>/<id> for all runtime identifiers"

key-files:
  created:
    - .planning/workstreams/go-live/phases/04-operator-dashboard-and-data-issue-triage/runbook/data-issue-triage.md
  modified: []

key-decisions:
  - "D-05: New runbook/data-issue-triage.md created in the phase runbook/ directory, mirroring Phase 3 mdm-secrets.md format"
  - "D-06: Each layer has 1-2 read-only diagnostic CLI commands in fenced bash blocks so operators can follow start-to-finish"
  - "D-07: All 8 DASH-02 layers covered; MDM/hosted graph/dbt-gold/Native App get priority treatment"
  - "D-14: All diagnostic commands are read-only; mutation verb mentions in prose are reworded to not match the mutation grep gate"

requirements-completed: [DASH-02]

# Metrics
duration: 20min
completed: 2026-06-16
---

# Phase 4 Plan 02: Data Issue Triage Guide Summary

**Operator-facing data-issue triage guide covering all 8 DASH-02 layers with read-only diagnostic CLI commands, owners, and escalation paths, extending the launch gate matrix triage table (rows 90-100) without duplicating it.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-16T00:00:00Z
- **Completed:** 2026-06-16
- **Tasks:** 1
- **Files created:** 1

## Accomplishments

- Created `runbook/data-issue-triage.md` (417 lines) covering all 8 DASH-02 layers: ingestion, bronze/silver, MDM, hosted graph, dbt/gold, Native App, dashboard, permissions
- Each layer section contains symptom, likely source, 1-2 read-only diagnostic commands in fenced bash blocks, owner, and escalation/next-action path
- Guide cross-references (does not duplicate) the launch gate matrix Data-Issue Triage Table via relative cross-phase link
- All content passes the mutation grep gate (0 mutation commands outside prohibition prose) and all secret-safety checks

## Task Commits

1. **Task 1: Author runbook/data-issue-triage.md covering all 8 layers** - `276313b` (docs)

## Files Created/Modified

- `.planning/workstreams/go-live/phases/04-operator-dashboard-and-data-issue-triage/runbook/data-issue-triage.md` — Operator data-issue triage guide, 417 lines, all 8 DASH-02 layers with read-only diagnostics

## Decisions Made

- All mutation verb mentions in Escalation prose (mdm sync-graph, mdm migrate, mdm run, dbt run, get-secret-value --query SecretString) were reworded to avoid triggering the mutation grep gate while preserving the escalation intent. This is correct per D-14: those commands are operator write-operations, not diagnostics; the guide must not include them as runnable commands even in prose paraphrases that could be copy-pasted.
- The `get-secret-value --query SecretString` string was avoided entirely from prose; the Secret-Safety Note rewords the prohibition as "raw-secret-retrieval command" to be unambiguous without repeating the forbidden pattern.

## Deviations from Plan

None — plan executed exactly as written. One inline refinement was required: the first draft of escalation prose for Layers 3, 4, and 5 included the exact forbidden command strings (e.g., `mdm run`, `mdm sync-graph`, `dbt run --select`) which tripped the plan's mutation grep gate. These were reworded to equivalent English descriptions (e.g., "MDM entity population step", "hosted graph synchronization", "full-refresh redeploy") before commit. This is not a deviation from plan intent — the plan explicitly forbids those patterns — it is adherence to the D-14 rule.

## Issues Encountered

None. The mutation check initially returned 5 hits from prose paraphrases of the forbidden command strings. All were reworded before commit to pass the gate cleanly.

## User Setup Required

None — documentation-only plan. No external service configuration required.

## Next Phase Readiness

- DASH-02 triage guide complete and committed to `workspace/go-live`
- Phase 4 Wave 2 plans (04-02 and 04-03) can close independently; both are now complete
- Phase 5 (go/no-go packet) can reference this triage guide as the operator first-inspection runbook
- Remaining Phase 4 blocker: Dashboard UAT (04-03) and evidence/dashboard-security.md rows to fill

## Self-Check: PASSED

- `runbook/data-issue-triage.md` exists at correct path (verified: 417 lines)
- All 8 layer tokens present (ingestion:2, bronze/silver:1, MDM:20, hosted graph:6, dbt/gold:2, Native App:17, dashboard:21, permissions:4)
- `verify-graph`: 8 occurrences
- `mdm counts`: 3 occurrences
- `EDGARTOOLS_GOLD_STATUS`: 4 occurrences
- `describe-secret`: 6 occurrences
- `01-LAUNCH-GATE-MATRIX.md`: 2 occurrences (cross-phase link present)
- Mutation grep gate: 0 hits
- Forbidden patterns: 0 hits (postgresql://, password=, bolt://, neo4j://, Traceback)
- Commit `276313b` exists on `workspace/go-live`

---
*Phase: 04-operator-dashboard-and-data-issue-triage*
*Completed: 2026-06-16*
