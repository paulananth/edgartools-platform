---
phase: 06-production-aws-infrastructure-and-application-deploy
plan: 02
subsystem: infra
tags: [ecr, ecs, step-functions, deploy-script, secrets-manager]

# Dependency graph
requires:
  - phase: 06-production-aws-infrastructure-and-application-deploy
    plan: 01
    provides: applied prod passive infrastructure (cluster, buckets, roles, subnets, SGs, secret ARNs) and populated edgar-identity secret
provides:
  - :prod-tagged warehouse and MDM ECR images (registry-side re-tag, in-place within account 077127448006)
  - Live production active deploy (deploy-aws-application.sh --env prod) — 22 Step Functions state machines, 5 ECS task definitions, exit 0
  - infra/aws-prod-application.json (untracked, never committed — D-10)
  - Non-secret Phase 6 Plan 02 evidence section in phase-01 evidence/aws.md
  - Launch gate matrix rows 12/14/15/16/17 flipped to PASS
affects: [07-prod-snowflake-and-dbt-deploy, 08-prod-mdm-and-dashboard-uat]

# Tech tracking
tech-stack:
  added: []
  patterns: [registry-side ECR re-tag via batch-get-image + put-image (no docker pull/push), post-cleanup digest re-resolution immediately before deploy, fresh secret-ARN resolution immediately before deploy, Generated-JSON Summary Rule for sensitive deploy manifests]

key-files:
  created: []
  modified:
    - .planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/aws.md
    - .planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md

key-decisions:
  - "ECR put-image returned ImageAlreadyExistsException for both repos because :prod already pointed at the current :dev digest from a prior session's promotion — treated as the intended idempotent end state, not a failure, after confirming via a follow-up describe-images call."
  - "Supplied --cluster-arn/--cluster-name explicitly since deploy-aws-application.sh has no AWS-API-discovery fallback for the ECS cluster identifier when no prior aws-prod-application.json manifest exists; values were read from terraform output (non-secret resource identifiers)."
  - "Two non-fatal deploy warnings (RDS MDM instance lookup, S3 bucket notification permission) were left unfixed — both out of this plan's scope: the MDM DSN sync is Phase 8/MDM-02 territory, and the bucket-notification warning has no observed data-flow impact."
  - "Corrected an off-by-one in the initial evidence draft: the deploy created 22 Step Functions state machines, not 21 — fixed in both evidence/aws.md and the matrix before committing."

requirements-completed: [LIVE-05]

# Metrics
duration: ~40min (across an interrupted session + cleanup/commit continuation)
completed: 2026-06-19
---

# Phase 6 Plan 2: Active Application Deploy Summary

**First real production application deploy — `:dev` images promoted to `:prod` in place, `deploy-aws-application.sh --env prod` ran successfully (22 state machines, 5 ECS task definitions, exit 0), and the launch gate matrix's active-deploy rows are now PASS.**

## Performance

- **Duration:** ~40 min (deploy + evidence work ran in a session that hit its token/time limit before committing; this continuation verified the live AWS state, corrected one evidence count, and completed the commit/tracking steps)
- **Tasks:** 2 (Task 1: ECR promotion + deploy; Task 2: evidence summary + matrix flips)
- **Files modified:** 2 (evidence/aws.md, 01-LAUNCH-GATE-MATRIX.md); 1 untracked generated artifact (infra/aws-prod-application.json, intentionally never committed)

## Accomplishments
- Confirmed `:prod` tag present on both `edgartools-dev-warehouse` and `edgartools-dev-mdm` ECR images, registry-side re-tag, no docker pull/push
- Verified the EDGAR identity secret ARN and both image digests were resolved fresh, in-session, after the deploy script's internal `cleanup-ecr-images.sh --apply` step ran (matrix rows 16/17 mitigations)
- Confirmed `deploy-aws-application.sh --env prod --enable-mdm --skip-build` exited 0 and produced `infra/aws-prod-application.json` at the repo root
- Verified the manifest structurally (18 top-level keys, 22 state machine names, 5 task definitions) without printing any ARN, digest value, or the JSON body
- Appended a non-secret Phase 6 Plan 02 evidence section to the phase-01 `evidence/aws.md`
- Flipped launch gate matrix rows 12, 14, 15, 16, 17 from BLOCKED to PASS with concrete citations; row 13 (dev→prod bronze sync) correctly left BLOCKED with an updated prerequisite note (prod bronze bucket now exists, sync itself out of scope)
- Caught and fixed a state-machine count discrepancy (21 vs. the actual 22) in the evidence draft before committing

## Task Commits

1. **Task 1: Promote images to :prod and run the production active application deploy** — executed live against AWS (ECR re-tag confirmed idempotent, deploy exit 0); no repo source files changed by this task, so no separate commit
2. **Task 2: Summarize the manifest non-secretly and flip launch gate matrix rows 12-17** — `da888f5` (feat) — includes the count correction (22, not 21)

**Plan metadata:** (this commit) docs: complete 06-02 plan

## Files Created/Modified
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/aws.md` — appended "Phase 6 Plan 02 — Active Application Deploy" section (Task 2)
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md` — rows 12/14/15/16/17 flipped to PASS, row 13 prerequisite note updated (Task 2)
- `infra/aws-prod-application.json` — generated by the deploy script, intentionally left **untracked**, never staged or committed (D-10)

## Decisions Made
- See `key-decisions` in frontmatter above.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Off-by-one state-machine count in evidence draft**
- **Found during:** continuation review, before committing
- **Issue:** The evidence draft and matrix row both said "21 Step Functions state machines"; counting the actual `infra/aws-prod-application.json` `state_machines` object (via Python, without printing values) showed 22 entries.
- **Fix:** Corrected both `evidence/aws.md` and `01-LAUNCH-GATE-MATRIX.md` to say 22, matching the live manifest.
- **Files modified:** `evidence/aws.md`, `01-LAUNCH-GATE-MATRIX.md` (corrected before the same commit that introduced them).
- **Verification:** `python3 -c "import json; ... len(d['state_machines'])"` → 22; both files now read 22.
- **Committed in:** `da888f5`.

---

**Total deviations:** 1 auto-fixed (1 blocking — evidence accuracy correction)
**Impact on plan:** No scope creep; fix was a factual count correction in evidence text, not an infrastructure or code change.

## Issues Encountered
The prior session that ran the actual deploy and drafted the evidence/matrix updates hit its token/time session limit after staging (but before committing) its changes and before writing this SUMMARY.md or updating STATE.md/ROADMAP.md. This continuation verified the staged work against live AWS state (ECR tags, JSON manifest structure, secret ARN) rather than blindly trusting the draft, found and fixed the one count discrepancy above, then completed the commit and tracking-file updates. No AWS actions were re-run; all live verification was read-only.

## User Setup Required
None.

## Next Phase Readiness
- LIVE-05 satisfied; Blocker 1 (prod AWS infrastructure not yet applied) from the v1.5 go/no-go packet is now fully remediated (passive infra from 06-01 + active deploy manifest from this plan).
- Phase 7 (prod Snowflake/dbt deploy) and Phase 8 (prod MDM/dashboard UAT) can reference the live ECS cluster, Step Functions state machines, and secret ARNs (names only — see evidence/aws.md).
- Blocker 2 (MDM secret values) remains open and unchanged — explicitly owned by Phase 8 / MDM-02, not touched by this plan per D-05/D-06.
- Row 13 (dev→prod bronze sync) remains BLOCKED — its prerequisite (prod bronze bucket) now exists, but the sync itself is out of scope for Phase 6.

---
*Phase: 06-production-aws-infrastructure-and-application-deploy*
*Completed: 2026-06-19*

## Self-Check: PASSED

- FOUND: `.planning/workstreams/go-live/phases/06-production-aws-infrastructure-and-application-deploy/06-02-SUMMARY.md`
- FOUND: commit `da888f5` (Task 2 evidence/matrix update with count correction)
- FOUND: `infra/aws-prod-application.json` exists on disk, untracked (`git status --short` confirms `??`)
- FOUND: ECR `:prod` tag confirmed live on both `edgartools-dev-warehouse` and `edgartools-dev-mdm`
