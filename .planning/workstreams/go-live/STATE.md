---
gsd_state_version: 1.0
milestone: v1.6
milestone_name: Production Launch Execution
status: blocked
stopped_at: Phase 9 Plan 09-02 blocked at missing generated production application summary
last_updated: "2026-06-22T00:30:15.000Z"
last_activity: 2026-06-22 -- Phase 9 Plan 09-02 status-only preflight failed before AWS status listing because infra/aws-prod-application.json is absent
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 11
  completed_plans: 8
  percent: 73
---

# Project State - go-live

## Current Position

Phase: 09 (production-hosted-graph-e2e) — BLOCKED after Plan 09-02 Task 1
Plan: 2 of 2 plan attempts closed; Plan 09-01 passed local production hosted-graph acceptance; Plan 09-02 is blocked before the AWS E2E approval checkpoint
Status: Phase 9 Plan 09-02 cannot enumerate production MDM Step Functions because `infra/aws-prod-application.json` is absent in this checkout. The planned `--status-only` command exited 1 at the local file guard before Step Functions status output. No production AWS MDM E2E executions started, and launch matrix Blocker 4 PASS rows were not updated.
Last activity: 2026-06-22 -- `bash infra/scripts/run-aws-mdm-e2e.sh --env prod --aws-profile sec_platform_deployer --aws-region us-east-1 --status-only` failed on missing generated production application summary. Evidence recorded in `.planning/workstreams/go-live/phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md`.

Progress: 73% (3/6 v1.6 phases complete: Phase 6 AWS, Phase 7 Snowflake/dbt, Phase 8 MDM secrets/connectivity; Phase 9 Plan 09-01 complete and Plan 09-02 blocked)

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

- [Phase 09 Plan 01 Task 4 grant remediation]: Operator approved and the
  minimum runtime-role grants for `EDGARTOOLS_PROD_DEPLOYER` were applied:
  usage on `EDGARTOOLS_PROD.MDM`, current/future select on MDM tables/views,
  usage on `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`, and create-table/create-view
  on the graph schema. The Task 4 wrapper was rerun with both secrets loaded
  in one non-printing shell invocation and unset after use. `sync-graph --limit
  100` progressed past the prior `PrivilegeError` and now stops with sanitized
  `SnowflakeObjectMissing`; metadata checks show zero current tables/views in
  `EDGARTOOLS_PROD.MDM`. Strict `verify-graph`, AWS MDM E2E, and launch matrix
  edits remain not run.

- [Phase 09 Plan 01 first-time load]: Operator approved a first-time production
  MDM Snowflake mirror load after the source-object gap. The load created 19
  `EDGARTOOLS_PROD.MDM` mirror tables with 135 total rows from the existing
  Snowflake Postgres MDM database, then bounded `sync-graph --limit 100`
  materialized 10 nodes and 0 edges into `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`.
  Strict `verify-graph --native-app-compute-pool CPU_X64_XS` passed with SQL
  parity and Native App checks enabled after `app_user`/`app_admin` application
  roles were granted to `EDGARTOOLS_PROD_DEPLOYER`. First-time load/deploy
  runbook: `docs/prod-mdm-snowflake-graph-first-load.md`.

- [Phase 09 Plan 02 Task 1]: Production AWS MDM E2E is blocked before the
  approval checkpoint because `infra/aws-prod-application.json` is absent in
  this checkout. The planned status-only command exited 1 at the local
  file-existence guard before Step Functions status output, so no AWS E2E
  execution started and no launch matrix PASS rows were updated.

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

- Blocker 4: PARTIALLY REMEDIATED (2026-06-22, Phase 09 Plan 09-01) — local
  production hosted-graph acceptance now passes against production Snowflake,
  MDM secrets, and the Native App compute pool. Phase 8 remains the source of
  truth for populated prod MDM secrets and Postgres connectivity. Phase 9 Plan
  09-01 applied production Native App/runtime prerequisites, documented the
  first-time `EDGARTOOLS_PROD.MDM` mirror load, completed bounded `sync-graph
  --limit 100`, and passed strict `mdm verify-graph` with SQL parity,
  compute_pool, graph_info, BFS, and WCC checks enabled. GRAPH-04 remains
  BLOCKED because Plan 09-02 cannot run status/E2E without the generated
  `infra/aws-prod-application.json` summary. Blocker 4 remains open until Phase
  9 Plan 09-02 production AWS MDM E2E passes and launch matrix rows are
  reconciled there. A reusable one-click provisioning script,
  `infra/scripts/bootstrap-prod-mdm.sh`, still encapsulates the Phase 8
  rotate/create/migrate/grant/populate/verify sequence for future re-runs.
  [2026-06-22, Claude takeover from Codex on `claude/go-live-v1.6-phase9`,
  re-rooted from Codex's tip, no content change] `infra/aws-prod-application.json`
  was present in this worktree; status-only preflight now passes cleanly
  (exit 0, all 21 state machines resolved, all NO_RUNS) — the Plan 09-02
  precondition above is satisfied. Operator approved the bounded production
  AWS MDM E2E command; it **FAILED at the first stage, `mdm_migrate`**: the ECS
  task could not start because its task definition injects a secret from
  `edgartools-prod/mdm/neo4j`, which this workstream forbids ever populating
  (Neo4j is deprecated, superseded by the Snowflake-hosted graph). Root cause:
  legacy `NEO4J_*` secrets wiring in the MDM ECS task-definition template
  (`deploy-aws-application.sh`), previously tracked only as TODOS.md D-05b
  cleanup debt, now confirmed a hard production blocker. See
  `phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md` for the
  5-whys and sanitized failure detail (no raw cause/ARNs/account ID). Fix
  requires editing the task-definition template and redeploying the
  already-applied Phase 6 ECS task definitions — production-impacting,
  not done this session pending explicit operator approval. Blocker 4
  remains open.

- Blocker 5: Prod dashboard UAT has not yet run against a production or
  production-like read-only configuration.

## Pending Todos

- Restore or regenerate `infra/aws-prod-application.json` outside git, then rerun Phase 9 Plan 09-02 from the status-only preflight.
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

Last session: 2026-06-22T00:30:15.000Z
Stopped at: Phase 9 Plan 09-02 Task 1. Plan 09-01 passed. Plan 09-02
status-only preflight failed because `infra/aws-prod-application.json` is
absent; no Step Functions status output appeared, no AWS E2E execution started,
and launch matrix edits were not made.
Resume file: .planning/workstreams/go-live/phases/09-production-hosted-graph-e2e/09-02-PLAN.md
Resume command: `$gsd-execute-phase 9 --ws go-live` from branch
`codex/go-live-v1.6-phase9`. Do not redo Phase 8, Task 3 Native App grants,
runtime-role grant remediation, first-time mirror load, or local strict
verify-graph. Restore/regenerate `infra/aws-prod-application.json` outside git,
then continue Plan 09-02 from Task 1.

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 05 P02 | 25min | 2 tasks | 2 files |
| Phase 06 P01 | ~35min | 3 tasks | 4 files (2 committed, 2 gitignored) |
| Phase 09 P01 | ~1h50min | 4 tasks | 5 files |
| Phase 09 P02 | ~5min | 1/4 tasks reached | 4 files |
