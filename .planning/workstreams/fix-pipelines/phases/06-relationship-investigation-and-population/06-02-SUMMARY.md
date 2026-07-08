---
phase: 06-relationship-investigation-and-population
plan: 02
subsystem: infra
tags: [step-functions, ecs, snowflake-postgres, secrets-manager, mdm, aws]

# Dependency graph
requires:
  - phase: 06-01
    provides: INSTITUTIONAL_HOLDS CIK-range batching (unrelated file, sequenced first per wave 1)
provides:
  - Written 5-whys root cause for the 2026-07-06 dev `bootstrap` Step Function failure
  - GO verdict (with satisfied pre-flight condition) for 06-03's first-ever `load_history` run
affects: [06-03-load-history-run]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "5-whys via AWS Step Functions describe-execution + get-execution-history + CloudWatch
       Logs + Secrets Manager version history, cross-referenced against git commit timing"

key-files:
  created:
    - .planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-02-BOOTSTRAP-FAILURE-FINDINGS.md
  modified: []

key-decisions:
  - "Root cause is an external/operational timing gap (non-atomic go-live.sh Postgres-provision
     -> secret-bootstrap sequencing), not a code/config bug in this repo -- already resolved by
     an operator secret rotation on 2026-07-06T12:30:44 ET, ~1 hour after the failure."
  - "GO verdict for load_history issued with condition 1 (fresh mdm-check-connectivity
     pre-flight) already satisfied live during this investigation, not deferred to 06-03."

patterns-established:
  - "For AWS CLI investigation from Git Bash on Windows, log-group/log-stream names starting
     with '/' get mangled by MSYS path conversion -- prefix the command with
     MSYS_NO_PATHCONV=1 for any aws logs/secretsmanager/etc. call with a leading-slash
     resource name."

requirements-completed: [EDGE-09, EDGE-10, EDGE-11]

coverage:
  - id: D1
    description: "5-whys root-cause chain for the 2026-07-06 bootstrap failure, from ECS exit
      code 1 down to a stale Secrets Manager DSN caused by a non-atomic deploy-stage sequencing
      gap"
    verification:
      - kind: other
        ref: "AWS CLI evidence trail: stepfunctions describe-execution/get-execution-history for
          sweep-bootstrap-1783349590, CloudWatch Logs stream
          warehouse-medium/edgar-warehouse/beeabce5644f49fa9b94b8d7bd573b7c, secretsmanager
          list-secret-version-ids + get-secret-value for edgartools-dev/mdm/postgres_dsn"
        status: pass
    human_judgment: false
  - id: D2
    description: "load_history readiness GO verdict, with the mdm-check-connectivity
      pre-flight condition satisfied live rather than deferred"
    verification:
      - kind: other
        ref: "stepfunctions start-execution for edgartools-dev-mdm-check-connectivity
          (preflight-06-02-1783525375) -> SUCCEEDED"
        status: pass
    human_judgment: false

duration: 16min
completed: 2026-07-08
status: complete
---

# Phase 6 Plan 2: 2026-07-06 Bootstrap Failure Root-Cause Summary

**Root-caused the 2026-07-06 dev `bootstrap` Step Function failure to a stale MDM Postgres DSN
in Secrets Manager (pointing at a decommissioned instance hostname from a non-atomic
provision-then-rotate deploy sequencing gap), already self-resolved by an operator secret
rotation ~1 hour after the failure; issued and live-verified a GO for 06-03's first-ever
`load_history` run.**

## Performance

- **Duration:** ~16 min
- **Started:** 2026-07-08T15:29:09Z (approx, immediately after 06-01 completion)
- **Completed:** 2026-07-08T15:45:37Z
- **Tasks:** 2 completed
- **Files modified:** 1 (findings doc; both tasks target the same single artifact per plan
  frontmatter's `files_modified`)

## Accomplishments

- Retrieved and analyzed the full failure trail for `sweep-bootstrap-1783349590` (4/4 retries
  failed, `ExecutionFailed` at 2026-07-06 11:30:16 ET): `describe-execution`,
  `get-execution-history`, and the CloudWatch Logs traceback from the last failed ECS task
  (`beeabce5644f49fa9b94b8d7bd573b7c`), pinpointing an unhandled
  `sqlalchemy.exc.OperationalError` / `psycopg2.OperationalError: ... Connection timed out` in
  `edgar_warehouse/mdm/universe.py:30` (`get_tracked_ciks`).
- Traced the "why now" question (why did the same instance's connectivity fail in this specific
  ~37-minute window but not before/after) through AWS Secrets Manager version history for
  `edgartools-dev/mdm/postgres_dsn`: the version active during the failure resolved to the
  exact host in the crash traceback; a new version created at 12:30:44 ET (~1h after the last
  failed retry) points at a different host — proving the underlying Snowflake Postgres instance
  endpoint changed and the secret was stale during the failure window.
- Corroborated the root cause with independent evidence: 5 separate MDM Postgres operations
  (`mdm-check-connectivity`, `mdm-run`, `mdm-backfill-relationships`, `mdm-sync-graph` x2) all
  SUCCEEDED on the current DSN in the hours after the rotation, and a same-day unrelated commit
  (`ba367f7`, "adopt orphaned seed-universe state machine") confirms active dev-environment
  remediation work was underway that day (the "dev Step Functions sweep").
- Determined no code fix was needed — the fix (secret rotation) had already landed
  operationally before this investigation began — and wrote the load_history readiness
  verdict: **GO**, with condition 1 (fresh `mdm-check-connectivity` pre-flight) satisfied live
  during this investigation (`preflight-06-02-1783525375`, SUCCEEDED) rather than left as a
  deferred TODO for 06-03.
- Confirmed `load_history` has zero prior executions in dev (`list-executions` returns empty),
  matching 06-CONTEXT.md's D-01 framing, and that its four-stage wiring
  (`Stage1Parallel → Stage1BEntityFacts → Stage1BPerFiling → Stage1BThirteenF → MdmRun`) is
  independently proven by `tests/architecture/test_load_history_state_machine.py`.

## Task Commits

Both tasks target the same single declared artifact
(`06-02-BOOTSTRAP-FAILURE-FINDINGS.md`), so they were committed together in one commit rather
than two artificial partial-file commits — the file's content genuinely spans both tasks'
scope (symptom→whys→root-cause from Task 1, resolution+readiness-verdict from Task 2) and no
intermediate state would be meaningful to preserve separately.

1. **Task 1 + Task 2: 5-whys root-cause + resolution/readiness verdict** - `99f68eb` (docs)

**Plan metadata:** (this commit, `docs(06-02): complete...`)

## Files Created/Modified

- `.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-02-BOOTSTRAP-FAILURE-FINDINGS.md` -
  Problem statement, 5 numbered whys, root cause, resolution disposition, and GO load_history
  readiness verdict (with pre-flight condition already satisfied).

## Decisions Made

- Classified the root cause as **transient/external** (an infra-deploy-sequencing timing gap),
  not a code/config bug — `go-live.sh`'s Postgres-provision stage and secret-bootstrap stage
  are two separate, non-atomic steps, and the instance was apparently re-provisioned under a
  new hostname between the two stages running, leaving the secret stale for a window that
  included this `bootstrap` execution.
- No code change was made in this repo, because there is no reproducible code defect to fix —
  the corrective action (secret rotation) already happened operationally before this
  investigation.
- Chose to run a live `mdm-check-connectivity` pre-flight execution during this investigation
  (rather than only documenting it as a TODO for 06-03) since it is cheap (~1 min) and
  significantly strengthens the GO verdict with current, not just historical, evidence.

## Deviations from Plan

None - plan executed exactly as written. Both tasks' acceptance criteria were met without
needing Rule 1-4 deviations: no bugs were found in application code requiring a fix, no missing
critical functionality was discovered, and no blocking issue arose during the investigation
itself (only the pre-existing MSYS path-conversion friction on this Windows Git Bash
environment for leading-slash AWS resource names, which was worked around inline with
`MSYS_NO_PATHCONV=1` and did not require a plan or scope change).

## Issues Encountered

- AWS CLI calls with a log-group-name / log-stream-name / secret-id starting with `/` (e.g.
  `/aws/ecs/edgartools-dev-warehouse`) failed with `InvalidParameterException` under Git Bash on
  Windows due to MSYS's automatic POSIX-path-to-Windows-path conversion mangling the leading
  slash. Resolved by prefixing those specific `aws` invocations with `MSYS_NO_PATHCONV=1`. No
  code or plan impact — purely a local tooling workaround, documented here for future sessions
  on this same Windows dev machine.

## User Setup Required

None - no external service configuration required. (The MDM Postgres DSN fix referenced in
this investigation was already applied by a prior operator action, not something this plan
introduced.)

## Next Phase Readiness

- 06-03 (bounded `load_history` run) is cleared to proceed: GO verdict issued, zero prior
  executions confirmed, wiring correctness independently test-proven, and the root cause of the
  only prior sibling failure is understood, resolved, and re-verified live (not merely
  historically) immediately ahead of this plan's completion.
- Standing condition for 06-03 (and any future re-deploy before it): if `go-live.sh`'s
  "Snowflake Postgres / graph prerequisites" stage is re-run, the "MDM + graph: secret
  bootstrap" stage must be re-run immediately after it in the same session to avoid
  reintroducing the exact staleness gap documented here.
- No blockers.

---
*Phase: 06-relationship-investigation-and-population*
*Completed: 2026-07-08*

## Self-Check: PASSED

- FOUND: `.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-02-BOOTSTRAP-FAILURE-FINDINGS.md`
- FOUND: commit `99f68eb`
