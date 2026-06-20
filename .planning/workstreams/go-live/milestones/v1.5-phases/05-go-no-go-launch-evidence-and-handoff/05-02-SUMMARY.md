---
phase: 05-go-no-go-launch-evidence-and-handoff
plan: 02
subsystem: infra
tags: [snowflake, aws-step-functions, mdm, hosted-graph, streamlit, launch-readiness, todos]

# Dependency graph
requires:
  - phase: 01-production-readiness-inventory-and-launch-gate-contract
    provides: 01-LAUNCH-GATE-MATRIX.md (Data-Issue Triage Table, Owner column, Secret-Safety Rules)
  - phase: 04-operator-dashboard-and-data-issue-triage
    provides: runbook/data-issue-triage.md format precedent
  - phase: 05-go-no-go-launch-evidence-and-handoff (plan 01, conceptual ordering only)
    provides: 05-GO-NO-GO-PACKET.md, runbook/launch-ops.md (cross-referenced, not re-read as input)
provides:
  - runbook/post-launch-monitoring.md — OPS-02 post-launch monitoring checklist covering exactly the 8 OPS-02 systems, each with diagnostic/expected-output/threshold/owner
  - TODOS.md additions — 4 D-05b go-live follow-up items (prod dashboard UAT, prod MDM secrets runbook execution, EDGARTOOLS_PROD_DEPLOYER grants, external Neo4j runtime remnant deprecation)
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Post-launch monitoring checklist EXTENDS (cross-references) the launch gate matrix's Data-Issue Triage Table rather than duplicating its Owner/Next-action columns"
    - "Grep-gate hygiene: forbidden destructive/secret-exposing tokens only appear inside `- `/`> ` prohibition-prose lines, never in plain paragraphs or runnable code fences"
    - "TODOS.md append-only discipline: new entries added after the last existing entry, separated by `---`, matching the existing Title/What/Why/Where format exactly; no existing entries modified or reordered"

key-files:
  created:
    - .planning/workstreams/go-live/phases/05-go-no-go-launch-evidence-and-handoff/runbook/post-launch-monitoring.md
  modified:
    - TODOS.md

key-decisions:
  - "Monitoring checklist documents exactly 8 OPS-02 systems in the order specified by D-04a; no 9th system added"
  - "All runnable diagnostics in the checklist are read-only (list-executions, describe-execution, logs tail, TASK_HISTORY/SHOW TASKS, dbt test, mdm counts, mdm verify-graph, SHOW COMPUTE POOLS, pgrep -f streamlit); no put-secret-value, no get-secret-value --query SecretString, no mdm sync-graph/migrate/run/derive/load, no dbt run/build, no terraform apply/destroy, no aws s3 rm anywhere as a runnable command"
  - "Used `../../` relative path (not the single `../` written in the plan's action text) to link from runbook/post-launch-monitoring.md back to the Phase 1 launch gate matrix, matching the actual precedent set by runbook/launch-ops.md and the plan's own frontmatter key_links note"
  - "TODOS.md follow-up items are appended verbatim to D-05b's 4 specified items only; no additional follow-up items were surfaced during execution"

requirements-completed: [OPS-02]

# Metrics
duration: 25min
completed: 2026-06-18
---

# Phase 5 Plan 2: Post-Launch Monitoring Checklist and TODOS.md Follow-Up Summary

**OPS-02 post-launch monitoring checklist covering all 8 required systems (Step Functions, CloudWatch, Snowflake task history, dbt test, MDM counts, verify-graph, Native App compute pools, dashboard) plus 4 D-05b TODOS.md follow-up items capturing prod go-live gaps.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2 completed
- **Files modified:** 1 created, 1 modified

## Accomplishments

- Authored `runbook/post-launch-monitoring.md` from scratch: exactly the 8 OPS-02 systems in the specified order, each with a read-only Diagnostic, Expected output shape, Escalation threshold, and named Owner mirroring the launch gate matrix's Owner column and Data-Issue Triage Table.
- Cross-referenced the launch gate matrix via the correct `../../` relative path (the file lives inside `runbook/`, one directory deeper than the matrix), matching the precedent already established by `runbook/launch-ops.md` from Plan 05-01, rather than the single `../` literally written in the plan's action text.
- Appended the 4 D-05b follow-up items to repo-root `TODOS.md` in the existing Title/What/Why/Where format, after the last existing entry, with no existing entries modified.
- Verified both artifacts against the plan's exact automated grep gates (PASS + NO_MUTATIONS for the monitoring checklist; PASS + NO_SECRET_CMDS for TODOS.md) before committing each task.

## Task Commits

1. **Task 1: Author runbook/post-launch-monitoring.md** — `d87cd57` (docs) — new file, 8 OPS-02 systems, read-only diagnostics only, cross-references launch gate matrix
2. **Task 2: Append D-05b follow-up items to TODOS.md** — `6fab1df` (docs) — 4 new entries, append-only, existing format preserved

**Plan metadata:** (this commit, see below)

## Files Created/Modified

- `.planning/workstreams/go-live/phases/05-go-no-go-launch-evidence-and-handoff/runbook/post-launch-monitoring.md` — 8 OPS-02 systems each with Diagnostic/Expected output shape/Escalation threshold/Owner, Cross-Reference section, Secret-Safety Note, References section (321 lines)
- `TODOS.md` — 4 new entries appended at end of file (Production dashboard UAT; Production MDM secrets population runbook execution; EDGARTOOLS_PROD_DEPLOYER direct SELECT grants on EDGARTOOLS_SOURCE; External Neo4j runtime remnant deprecation), 69 lines added, 0 lines removed

## Decisions Made

- Followed the `../../` relative-link pattern from the plan's frontmatter `key_links` note and the precedent in `runbook/launch-ops.md`, rather than the single `../` literally written in the plan's Task 1 action text — the action text describes the path relative to the phase directory, not literally relative to the new file's actual location inside `runbook/`.
- Did not surface any additional TODOS.md follow-up items beyond the 4 specified in D-05b — execution did not reveal new follow-up work requiring capture.
- Kept the monitoring checklist's "Cross-Reference" section explicit about extending (not duplicating) the Data-Issue Triage Table, directing operators to that table's "Next action" column for remediation routing.

## Deviations from Plan

None — plan executed exactly as written, including the deliberate `../../` correction which is consistent with (not a deviation from) the plan's own frontmatter `key_links` specification and the established `runbook/launch-ops.md` precedent.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. This is a documentation-only plan; no live commands were run, and no diagnostic command in the checklist was executed against real infrastructure (the checklist documents commands for future operator use).

## Next Phase Readiness

- Both OPS-02 must_have artifacts exist, satisfy all must_haves, and are committed.
- This is the final plan in Phase 5. Phase 5 (and the v1.5 go-live milestone's planning/documentation scope) is now complete: all 5 phases, 12/12 plans.
- Outstanding work is captured in TODOS.md (4 new items) and in `05-GO-NO-GO-PACKET.md`'s NO-GO — Conditional decision (Plan 05-01) — both require real production credentials/infrastructure before they can be closed, which is explicitly out of scope for this milestone's planning/documentation work.

---
*Phase: 05-go-no-go-launch-evidence-and-handoff*
*Completed: 2026-06-18*

## Self-Check: PASSED

All created/modified files confirmed present on disk (`runbook/post-launch-monitoring.md`, `TODOS.md`); both task commit hashes (`d87cd57`, `6fab1df`) confirmed present in `git log --oneline --all`.
