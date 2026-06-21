---
gsd_state_version: 1.0
milestone: v1.6
milestone_name: Production Launch Execution
status: executing
stopped_at: Phase 9 Plan 09-01 Task 4 blocked at sync-graph runtime-role grants
last_updated: "2026-06-21T23:02:00.000Z"
last_activity: 2026-06-21 -- Phase 9 Plan 09-01 Task 4 stopped at bounded sync-graph PrivilegeError
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 11
  completed_plans: 6
  percent: 55
---

# Project State - go-live

## Current Position

Phase: 09 (production-hosted-graph-e2e) — EXECUTING Plan 09-01
Plan: 0 of 2 executed; Plan 09-01 Tasks 1-3 are complete and committed; Task 4 is blocked at bounded `sync-graph --limit 100`; Plan 09-02 covers production AWS MDM E2E and launch matrix reconciliation
Status: Paused at Phase 9 Plan 09-01 Task 4. Production Native App/schema/database-role prerequisites are applied, but local graph sync cannot proceed until the runtime Snowflake role receives the minimum MDM/graph schema grants.
Last activity: 2026-06-21 -- Phase 9 Plan 09-01 Task 4 loaded secrets in one non-printing shell invocation, ran counts, skipped bounded MDM smoke because seeded entity rows exist, and stopped at sync-graph PrivilegeError before strict verify-graph

Progress: 55% (3/6 v1.6 phases complete: Phase 6 AWS, Phase 7 Snowflake/dbt, Phase 8 MDM secrets/connectivity; Phase 9 executing and paused at Plan 09-01 Task 4 runtime-role grants)

## Milestone Context

Execute the production launch sequence documented by v1.5. The milestone exists to flip
the current `NO-GO - Conditional` decision to `GO` only after the five documented blockers
are remediated, owner-approved, and backed by non-secret production evidence.

## Active Worktree

`/Users/aneenaananth/projects/edgartools-platform`

Branch: `codex/go-live-v1.6-phase9` (created by Codex from latest `origin/main`
after PR #80 merged; Claude-owned branches remain untouched)

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

- [Phase 09 planning]: Phase 8 is treated as complete from PR #80 and is not
  re-executed. Phase 9 plans were created on `codex/go-live-v1.6-phase9` for
  Native App prod prerequisites, bounded local graph sync/strict verify, and
  AWS MDM hosted graph E2E. `--skip-preflight` remains non-acceptance and is
  not part of Phase 9 execution.

- [Phase 09 Plan 01 Task 1]: Read-only preflight completed on 2026-06-21 and
  evidence was committed in
  `.planning/workstreams/go-live/phases/09-production-hosted-graph-e2e/evidence/hosted-graph-local.md`.
  Phase 7 native-pull/dbt and Phase 8 MDM evidence preconditions pass; both
  required Phase 8 secrets have AWSCURRENT metadata. Native App installation,
  app role mappings, grants to the app, and `CPU_X64_XS` compute-pool visibility
  pass. The production graph schema/database role privilege target is missing
  or not visible, so execution is paused before production provisioning/writes
  at the Task 2 operator approval checkpoint.

- [Phase 09 Plan 01 Tasks 2-4]: Operator approved production Native App
  provisioning and bounded graph writes. Task 3 production-scoped Native App
  prerequisites were applied and committed: graph schema/database role created,
  Native App grants and application-role grants passed, future table/view grants
  and `CPU_X64_XS` compute-pool visibility passed. Task 4 loaded
  `MDM_DATABASE_URL` and `MDM_SNOWFLAKE_SECRET_JSON` in one non-printing shell
  invocation and unset both values before exit. `mdm counts` passed with seeded
  entity rows already present, so bounded MDM smoke was skipped. Bounded
  `sync-graph --limit 100` stopped with a sanitized `PrivilegeError`: the
  expected runtime role `EDGARTOOLS_PROD_DEPLOYER` lacks usage on
  `EDGARTOOLS_PROD.MDM`, usage/create-table/create-view on
  `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`, and future select on MDM
  tables/views. Strict `verify-graph` did not run.

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

- Blocker 2: FULLY REMEDIATED (2026-06-21, Phase 08 complete via PR #80) —
  `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake` are
  populated and carry AWSCURRENT versions; the production `mdm` Postgres
  database exists, is migrated, has application-role grants applied, and
  `check-connectivity`/`counts` passed against prod without printing secret
  values. See
  `.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md`.

- Blocker 3: FULLY REMEDIATED (2026-06-20/21, Phase 07 complete) -- this entry was stale;
  both SNOW-03 (native-pull) and SNOW-04 (dbt/gold) reached final status PASS. All three
  prod Terraform roots (access/aws, snowflake, access/snowflake) applied against
  production with zero destroys; native-pull objects (stages, manifest tables/pipe/stream,
  stream-processor task) verified live. `EDGARTOOLS_PROD_DEPLOYER` service user created,
  credentials stored in `edgartools-prod/dbt/snowflake`. 16/16 dbt gold models built
  (15 dynamic tables + status view), 47/47 tests passing against real production data
  (including the `financial_derived` YoY tiebreaker/amendment suite). See
  `.planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold/evidence/native-pull.md`
  and `evidence/dbt-gold.md` for full detail.

- Blocker 4: Prod hosted graph E2E has not yet passed against production Snowflake,
  MDM secrets, and Native App compute pool. Phase 8 (MDM secrets population + connectivity
  verification) is complete — see `evidence/mdm-prod-secrets-and-connectivity.md`
  (Postgres credentials rotated, `mdm` database created/migrated/granted, both AWS secrets
  populated, `check-connectivity` and `counts` passing against prod via the
  `application` role). Phase 9 Plan 09-01 Tasks 1-3 are complete, but Task 4 is
  blocked at local bounded `sync-graph` because the production Snowflake runtime
  role lacks the MDM/graph schema grant categories needed to materialize graph
  tables. Blocker 4 remains open until local strict `mdm verify-graph` and
  production AWS MDM E2E both pass. A reusable
  one-click provisioning script,
  `infra/scripts/bootstrap-prod-mdm.sh`, now encapsulates the full rotate→create→migrate→grant→
  populate-secrets→verify sequence for future re-runs (e.g. dev cutover, prod re-provisioning).

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

Last session: 2026-06-21T23:02:00.000Z
Stopped at: Phase 9 Plan 09-01 Task 4 after bounded `sync-graph --limit 100`
returned a sanitized `PrivilegeError`. Production Native App prerequisites are
applied; strict `verify-graph`, AWS MDM E2E, and launch matrix edits have not run.
Resume file: .planning/workstreams/go-live/phases/09-production-hosted-graph-e2e/09-01-PLAN.md
Resume command: `$gsd-execute-phase 9 --ws go-live` from branch
`codex/go-live-v1.6-phase9` after explicit operator approval for the runtime-role
grant remediation. Do not redo Phase 8 or the completed Task 3 Native App grants.

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 05 P02 | 25min | 2 tasks | 2 files |
| Phase 06 P01 | ~35min | 3 tasks | 4 files (2 committed, 2 gitignored) |
