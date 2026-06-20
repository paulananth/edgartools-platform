---
gsd_state_version: 1.0
milestone: v1.6
milestone_name: Production Launch Execution
status: blocked
stopped_at: SNOW-03 PASSED (real production native-pull apply); SNOW-04 dependency cleared but dbt deps/run/test not yet executed
last_updated: "2026-06-19T23:30:00.000Z"
last_activity: 2026-06-19 -- Claude (on claude/go-live-v1.6-phase7) ran the real production Snowflake native-pull apply with operator-supplied ACCOUNTADMIN access; fixed 6 versions.tf constraints, a bad tfvars.example default, imported 3 shared IAM roles, namespaced 3 inline policies, switched auth to password, resolved a dashboard-object ordering race; created and verified EDGARTOOLS_PROD_DEPLOYER end-to-end; stored credentials in new secret edgartools-prod/dbt/snowflake. dbt deps/run/test deliberately not run (separate further state change).
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 4
  completed_plans: 4
  percent: 33
---

# Project State - go-live

## Current Position

Phase: 07 (Production Snowflake Native Pull And Gold) — SNOW-03 PASS, SNOW-04 dependency cleared
Plan: 2 of 2 executed, then retried on branch takeover
Status: SNOW-03 now PASSES — real production `terraform apply` ran across all 3 Snowflake-side roots (access/aws, snowflake, access/snowflake), zero destroys, native_pull_ready=true. SNOW-04's blocking dependency on SNOW-03 is cleared and a verified production deployer user/credentials now exist, but `dbt deps/run/test` has deliberately not been run yet (separate further state change against production gold tables, not assumed approved by this continuation).
Last activity: 2026-06-19 -- Real production Snowflake native-pull apply completed and verified; see evidence/native-pull.md and evidence/dbt-gold.md for full detail.

Progress: 33% (2/6 phases have plan-execution summaries; SNOW-03 unblocked, SNOW-04 ready to retry pending explicit approval to run dbt)

## Milestone Context

Execute the production launch sequence documented by v1.5. The milestone exists to flip
the current `NO-GO - Conditional` decision to `GO` only after the five documented blockers
are remediated, owner-approved, and backed by non-secret production evidence.

## Active Worktree

`/Users/aneenaananth/gsd-workspaces/go-live/edgartools-platform`

Branch: `claude/go-live-v1.6-phase7` (taken over from Codex's `codex/go-live-v1.6-phase7`
at user's explicit instruction on 2026-06-19; tip commit `b67acfd` unchanged, branch
re-rooted and pushed to origin under the new name per the CLAUDE.md HARD RULE that
Claude and Codex must never commit to the same branch going forward)

## Decisions

- Treat go-live as v1.5 and keep phase numbering local to this isolated workstream.
- Keep AWS as the only active deployment path.
- Use existing deploy and verification scripts before adding automation.
- `edgar-warehouse mdm verify-graph` remains the hosted graph acceptance gate.
- Dashboard launch evidence is operator inspection evidence; it does not replace CLI acceptance.
- No secrets, DSNs, tokens, raw connector errors, Terraform state, or sensitive generated deployment values may be committed.
- [Phase 05]: Post-launch monitoring checklist documents exactly 8 OPS-02 systems with read-only diagnostics only; cross-references the launch gate matrix Data-Issue Triage Table rather than duplicating it
- [Phase 05]: TODOS.md D-05b follow-up items appended append-only: prod dashboard UAT, prod MDM secrets runbook execution, EDGARTOOLS_PROD_DEPLOYER grants, external Neo4j runtime remnant deprecation
- [Milestone v1.6]: Continue phase numbering from v1.5; do not delete v1.5 phase
  evidence because the archived roadmap and go/no-go packet still link to those files.

- [Milestone v1.6]: Research is optional and disabled by workstream default; production
  launch execution should prefer existing runbooks and evidence gates over new architecture.

- [Phase 06 Plan 01]: terraform apply tfplan run from the exact saved/approved plan file
  (no re-plan) per D-04; first real production state change in the go-live workstream
  (42 added, 0 changed, 0 destroyed). Only edgartools-prod-edgar-identity received a
  put-secret-value call; the 4 MDM secret containers remain empty shells deferred to
  Phase 8 / MDM-02.

- [Phase 06 Plan 01]: AWS Secrets Manager CLI calls require an explicit `--region us-east-1`
  flag in this environment — the default AWS CLI profile region (`us-east-2`) caused a
  transient ResourceNotFoundException on the first put-secret-value attempt despite the
  secret existing.

- [Phase 07]: Plans 07-01 and 07-02 correctly stopped at BLOCKED evidence rather than
  fabricating prod Snowflake credentials or running dbt against an unconfirmed source
  layer. 5-whys root cause for both: production Snowflake Terraform backend/tfvars files
  (6 total, across the access/aws, snowflake, and access/snowflake prod stacks) have never
  been provisioned by a human operator — this is the first phase to touch the Snowflake
  side of prod, and SNOW-04 (dbt/gold) is purely dependency-blocked on SNOW-03
  (native-pull) rather than an independent failure.

- [Phase 07 takeover]: User explicitly instructed taking over `codex/go-live-v1.6-phase7`
  on 2026-06-19. Re-rooted as `claude/go-live-v1.6-phase7` from the same tip commit
  (`b67acfd`, no content change) in the Claude go-live worktree and pushed to origin.
  Codex's original branch/worktree left untouched (not deleted, not rebased) per the
  HARD RULE — only the new Claude-owned branch will receive further commits.

## Known Inputs

- Dev hosted graph E2E succeeded through strict Snowflake-hosted verification.
- Dashboard UAT passed locally after loading MDM configuration from AWS Secrets Manager without printing the DSN.
- v1.5 shipped a secret-safe launch gate matrix, production runbooks, go/no-go packet,
  rollback procedures, and post-launch monitoring checklist.

- `neo4j-snowflake` Phase 4 still has hosted graph dashboard documentation and final evidence closeout work recorded in its state.
- Phase 1 produced `01-LAUNCH-GATE-MATRIX.md`, four `evidence/*.md` templates, and `01-VERIFICATION.md` under the go-live workstream.
- Phase 1 verification passed for LIVE-01, SEC-01, ISO-01, and ISO-02; production readiness itself remains blocked until later phases capture prod proof.
- Root `.planning` is multi-workstream; this workstream should not rewrite existing workstream artifacts.

## Blockers

- Blocker 1: FULLY REMEDIATED (2026-06-19, Phase 06 complete) — prod passive AWS
  infrastructure (VPC, S3, KMS, ECR, ECS cluster/logs, SNS, 5 secret containers,
  edgar-identity secret value) is applied (06-01), and the active application deploy
  manifest (`infra/aws-prod-application.json`, 22 state machines, 5 ECS task defs)
  exists and is summarized in phase-01 `evidence/aws.md` (06-02). LIVE-04 and LIVE-05
  satisfied.

- Blocker 2: Production MDM Secrets Manager values are not populated for
  `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake`.

- Blocker 3: Prod Snowflake native pull and dbt gold deployment have not yet run.
- Blocker 4: Prod hosted graph E2E has not yet passed against production Snowflake,
  MDM secrets, and Native App compute pool.

- Blocker 5: Prod dashboard UAT has not yet run against a production or
  production-like read-only configuration.

## Pending Todos

- Preserve all v1.5 evidence and milestone archives while adding v1.6 planning artifacts.

## Pre-Planning Branch Audit (2026-06-13)

Before Phase 1 planning, verified `workspace/go-live` is current with `main`
(0 commits behind, 3 ahead = go-live planning docs only). Audited all local
branches: every branch with unmerged-looking commits had already landed in
`main` via squash-merged PRs (#49-#65). Deleted 5 confirmed-merged, no-longer-
checked-out local branches as cleanup: `codex/complete-phase-8-dashboard-uat`,
`codex/neo4j-snowflake-phase3`, `feature/phase6-02-fundamentals-relationship-tests`,
`fix/period-end-pk-collision-stage1`, `mdm/snowflake-postgres-cutover-live`.
Remaining branches are either `main`/`workspace/go-live` or checked out in
other active worktrees (left untouched). No code merge into go-live was
needed — it was already current.

## Session Continuity

Last session: 2026-06-19T22:05:00.000Z
Stopped at: Branch ownership taken over from Codex (`codex/go-live-v1.6-phase7` ->
`claude/go-live-v1.6-phase7`, tip `b67acfd` unchanged). Phase 7 plans executed;
SNOW-03 and SNOW-04 remain BLOCKED on missing prod Snowflake Terraform local inputs.
Resume file: None
Resume command: Provide the missing prod Terraform local input files outside git, then create a Phase 7 retry/gap plan before starting Phase 8, from branch `claude/go-live-v1.6-phase7`.

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 05 P02 | 25min | 2 tasks | 2 files |
| Phase 06 P01 | ~35min | 3 tasks | 4 files (2 committed, 2 gitignored) |
