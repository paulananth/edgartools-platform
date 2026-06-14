---
phase: 02-aws-and-snowflake-production-deployment-dry-run
plan: 01
subsystem: infra
tags: [terraform, aws, ecr, secrets-manager, ecs, step-functions, deploy-runbook]

# Dependency graph
requires:
  - phase: 01-production-readiness-inventory-and-launch-gate-contract
    provides: Launch gate matrix (01-LAUNCH-GATE-MATRIX.md) and evidence/aws.md structure with the 5 AWS-side BLOCKED rows
provides:
  - Pattern-1 plan-validated terraform plan evidence for infra/terraform/accounts/prod/ (37 to add, 0 to change, 0 to destroy; 22/22 output names)
  - Read-only image-digest-format capture for edgartools-dev-warehouse:dev and edgartools-dev-mdm:dev
  - runbook/aws-deploy.md - non-secret production AWS deploy + ECR image-promotion runbook (228 lines)
  - Refined AWS-side matrix rows 1-5 in 01-LAUNCH-GATE-MATRIX.md linking to the new runbook and evidence
affects: [02-02 (Snowflake-side dry-run plan), Phase 3 (live production execution)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pattern 1: temporary versions.tf relaxation + local-backend override.tf for read-only terraform plan against accounts/prod, fully reverted before commit"
    - "ECR image promotion interpretation A1: re-tag edgartools-dev-{warehouse,mdm} images :prod in place (same-account, no separate prod ECR per D-05)"

key-files:
  created:
    - .planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md
  modified:
    - .planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/aws.md
    - .planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md

key-decisions:
  - "ECR image-promotion uses interpretation A1 (in-place :prod re-tag on edgartools-dev-{warehouse,mdm}) as the only interpretation consistent with D-05+D-01+D-02"
  - "versions.tf ~> 1.14.7 pessimistic constraint recorded as a required-fix note (not fixed) - blocks terraform init under installed Terraform 1.15.5 until relaxed"
  - "All 5 AWS-side matrix rows remain BLOCKED (no waiver/third status per D-06); row text now links to plan-validated evidence and the new runbook instead of being purely aspirational"

patterns-established:
  - "Command-evidence block structure (fenced bash + Result line + non-secret bullet facts + BLOCKED reference) reused for Phase 2 evidence entries"

requirements-completed: [LIVE-02]

# Metrics
duration: 25min
completed: 2026-06-14
---

# Phase 2 Plan 1: AWS Production Deploy Runbook and Terraform Plan Evidence Summary

**Pattern-1-validated `terraform plan` (37 to add, 0 to change, 0 to destroy; 22/22 outputs) for `infra/terraform/accounts/prod/`, plus a new 228-line non-secret `runbook/aws-deploy.md` documenting the exact `deploy-aws-application.sh --env prod` command, ECR `:dev`->`:prod` image-promotion procedure (interpretation A1), and the structural BLOCKED reasons for AWS-side matrix rows 1-5.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-06-14T20:26:00Z (approx, prior session)
- **Completed:** 2026-06-14T20:51:08Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- Ran the full Pattern 1 read-only `terraform plan` procedure against `infra/terraform/accounts/prod/` (temporary `versions.tf` relaxation + local-backend `override.tf`, `terraform init`/`plan`, full revert), reproducing `Plan: 37 to add, 0 to change, 0 to destroy` against account `077127448006` with `git status --short` confirmed clean afterward.
- Recorded all 22 output names from `outputs.tf` in `evidence/aws.md`, plus a required-fix note for the `versions.tf` `~> 1.14.7` pessimistic constraint bug (unfixed, documented for a future task).
- Captured read-only ECR image-digest-format evidence (`sha256:<64-hex>`) for `edgartools-dev-warehouse:dev` and `edgartools-dev-mdm:dev` without recording digest values.
- Authored `runbook/aws-deploy.md`: ECR image-promotion procedure (interpretation A1, in-place `:prod` re-tag), the exact production deploy command with `--image-ref`/`--mdm-image-ref`/`--enable-mdm`/`--skip-build`/`--edgar-identity-secret-arn` (freshly resolved), the script's parameter resolution order, the 4 required MDM secret names, the pre-deploy ECR-cleanup digest re-resolution ordering requirement (Pitfall 3), and the generated-manifest summary rule.
- Refined AWS-side matrix rows 1-5 in `01-LAUNCH-GATE-MATRIX.md` to link to the new evidence/runbook while keeping all 5 rows `BLOCKED` (D-06: no waiver status). Checked off the "Production AWS profile and AWS account label" required identifier with the D-05 same-account note, and added the 4 MDM secret-name sub-items as unchecked required identifiers.

## Task Commits

Each task was committed atomically:

1. **Task 02-01-01: Run Pattern 1 terraform plan and record AWS infra evidence** - `61fdfa5` (docs)
2. **Task 02-01-02: Write aws-deploy runbook and update AWS-side matrix rows** - `46abb45` (docs)

**Plan metadata:** (this commit)

## Files Created/Modified
- `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md` - New 228-line non-secret production AWS deploy + ECR image-promotion runbook
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/aws.md` - Appended "Phase 2 Read-Only Checks Actually Run" (Pattern 1 plan result + output names + account label + revert-clean confirmation + versions.tf required-fix note), "Image-Promotion Digest Capture (read-only)" sub-section, and "Required MDM Secret Names" section
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md` - Refined rows 1-5 (linked to new evidence/runbook, all remain BLOCKED), checked off the AWS profile/account-label required identifier with D-05 note, added 4 MDM secret-name sub-items

## Decisions Made
- ECR image promotion documented strictly as interpretation A1 (re-tag existing `edgartools-dev-{warehouse,mdm}` images with `:prod` in the same repo/account) since `edgartools-prod-warehouse`/`edgartools-prod-mdm` repos do not exist and creating them is out of scope (Terraform `apply`, D-01).
- `versions.tf` `~>` constraint bug recorded as a required-fix note only - Pattern 1 explicitly requires edit-then-revert, not a permanent fix, in Phase 2.
- Matrix Status values kept to `BLOCKED`/`PASS` only per D-06 - no new "plan-validated" status word was introduced; instead the Required Fix / Required Rerun Proof cell text was expanded with links to the plan-validated evidence and runbook.

## Deviations from Plan

None - plan executed exactly as written. Both tasks completed with the exact Pattern 1 procedure, the exact ECR describe-images reads, and the exact runbook content/structure specified in the plan, with no Rule 1-4 auto-fixes required.

## Known Stubs

None - this plan produces documentation/evidence artifacts only (runbook + evidence + matrix updates); no application code, data sources, or UI components were created.

## Issues Encountered
- An environment-level (sandbox) ENOSPC/output-capture quirk caused `Command output was lost` errors on Bash commands that exited non-zero (e.g. `grep -q` with no match). Worked around by using `grep -c ... || true` patterns instead of `grep -q ... && echo`. This was a tooling workaround only - no project files were affected and `df -h` confirmed 10Gi+ free disk throughout.
- Final secret-safety grep scan (pattern `arn:aws:|password|AKIA[0-9A-Z]{16}|-----BEGIN|SecretString|postgresql://|snowflakecomputing\.com`, case-insensitive) found 5 matches across the 3 touched files (1 in `evidence/aws.md`, 0 in `runbook/aws-deploy.md`, 4 in `01-LAUNCH-GATE-MATRIX.md`). All 5 were inspected with line context and confirmed to be pre-existing Phase 1 rule-statement prose (e.g. "It omits passwords, tokens, DSNs... secret ARNs", "Secrets may be loaded into runtime environment variables with ... --query SecretString --output text") - none are leaked secret values, and none were introduced by this plan's edits.

## Threat Flags

None - no new security-relevant surface (network endpoints, auth paths, file-access patterns, or schema changes) was introduced. The runbook documents existing deploy-script flags and ECR/Secrets Manager read patterns already covered by the plan's threat model (T-02-04, T-02-04b, T-02-04c) and Phase 1's secret-safety rules (D-13/D-15).

## User Setup Required

None - no external service configuration required. This plan is documentation/evidence only; no production state was changed (per D-01, document-and-validate only phase).

## Next Phase Readiness
- AWS-side Phase 2 artifacts (terraform-plan evidence, ECR digest-format capture, deploy runbook, refined matrix rows 1-5) are complete and ready for the Snowflake-side dry-run plan (02-02) and eventual Phase 3 live execution.
- Remaining AWS-side blockers (all still `BLOCKED` per the matrix, by design - D-01 scope): a real `terraform apply` against `infra/terraform/accounts/prod/` (after fixing the `versions.tf` `~>` constraint), the production AWS application manifest, the production deploy itself, the stale `edgar-identity` ARN mitigation proof, and the ECR-cleanup digest re-resolution proof - each now has documented exact commands/ordering in `runbook/aws-deploy.md` ready for Phase 3 operators.
- No blockers for proceeding to plan 02-02 (Snowflake-side dry-run), which is independent of this plan's AWS-only scope.

---
*Phase: 02-aws-and-snowflake-production-deployment-dry-run*
*Completed: 2026-06-14*

## Self-Check: PASSED

- FOUND: `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/02-01-SUMMARY.md`
- FOUND: `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md`
- FOUND commit: `61fdfa5` (Task 02-01-01)
- FOUND commit: `46abb45` (Task 02-01-02)
- FOUND commit: `8351018` (this summary commit)
