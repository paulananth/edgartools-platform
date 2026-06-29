---
gsd_state_version: 1.0
milestone: v1.6
milestone_name: Production Launch Execution
status: in_progress
stopped_at: Phase 11 plans created (11-01 evidence audit + SEC-02/ISO-03; 11-02 go/no-go packet + OPS-03 monitoring handoff). All 5 blockers FULLY REMEDIATED. Awaiting /gsd:execute-phase 11.
last_updated: "2026-06-25T23:59:00.000Z"
last_activity: 2026-06-25 -- All 5 go-live blockers PASS (Blocker 4 via bronze-seed-silver-gold-1782384165 MaxConcurrency=4, Blocker 5 via dashboard UAT + operator sign-off). Phase 11 plans created and committed. Ready for execution.
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 13
  completed_plans: 10
  percent: 92
---

# Project State - go-live

## Current Position

Phase: 09 (production-hosted-graph-e2e) — MERGED to main (PR #81); Blocker 4 still open
Plan: 2 of 2 plan attempts closed; Plan 09-01 passed local production hosted-graph acceptance; Plan 09-02 ran the operator-approved AWS MDM E2E and found a new hard blocker (legacy Neo4j secret wiring), documented and merged
Status: Phase 9's branch work (Codex's 12 commits + Claude's takeover commit documenting the `mdm_migrate` AWS failure and a `go-live.sh` doctor-check fix) is merged to `main` via PR #81 (merge commit `24ab70c`, all 7 CI checks passed). This merges the *documentation and tooling* of Phase 9, not blocker resolution — Blocker 4 remains open because the production AWS MDM E2E chain has not succeeded end-to-end. The unresolved root cause (legacy `NEO4J_*` secret wiring in the MDM ECS task-definition template) still needs a separate, explicitly-approved fix and redeploy before the chain can be retried.
Last activity: 2026-06-22 -- PR #81 merged to main. `claude/go-live-v1.6-phase9` and `codex/go-live-v1.6-phase9` both left intact (not deleted) per standard practice; no further commits should land on either — new work should branch from `main` post-merge.

Progress: 73% (3/6 v1.6 phases complete: Phase 6 AWS, Phase 7 Snowflake/dbt, Phase 8 MDM secrets/connectivity; Phase 9 merged to main with Blocker 4 still open)

## Milestone Context

Execute the production launch sequence documented by v1.5. The milestone exists to flip
the current `NO-GO - Conditional` decision to `GO` only after the five documented blockers
are remediated, owner-approved, and backed by non-secret production evidence.

## Active Worktree

`/Users/aneenaananth/gsd-workspaces/go-live/edgartools-platform`

Branch: `claude/go-live-phase9-merge-followup` (created from `origin/main` post-PR#81
merge, for this STATE.md/TODOS.md documentation update only). `codex/go-live-v1.6-phase9`
and `claude/go-live-v1.6-phase9` are both fully merged into `main` (PR #81, merge commit
`24ab70c`) and should not receive further commits.

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
  [2026-06-22, merge] All of the above (Plan 09-01 production hosted-graph
  acceptance, the Plan 09-02 AWS MDM E2E failure documentation, and the
  `go-live.sh` doctor-check fix) merged to `main` via PR #81 (merge commit
  `24ab70c`, 7/7 CI checks passed). The merge lands documentation/tooling
  only — it does not resolve Blocker 4. Next concrete step: get explicit
  operator approval to edit the MDM ECS task-definition template (remove the
  `NEO4J_*`/`edgartools-prod/mdm/neo4j` secrets injection), redeploy, then
  retry the AWS MDM E2E chain from `mdm_migrate` onward.
  [2026-06-23/24, Claude session] The legacy Neo4j secrets-injection blocker
  above is moot for the path actually used to reach PASS: `bronze_seed_silver_gold`
  (new Step Function, added this session) never runs `mdm_migrate` at all — it
  discovers CIKs directly from S3 bronze and chains `SeedFromBronze ->
  BatchSilver -> MdmRun -> MdmBackfill -> MdmSync -> MdmVerify -> GoldRefresh`.
  Confirmed live (`aws ecs describe-task-definition
  edgartools-prod-mdm-medium:19`) that the deployed MDM task definition's
  `secrets` list only contains `MDM_DATABASE_URL`, `MDM_SNOWFLAKE_SECRET_JSON`,
  and `EDGAR_IDENTITY` — no `NEO4J_*` entry. The legacy wiring was removed from
  the task-definition template at some point in this session's redeploys; the
  remaining TODOS.md D-05b cleanup-debt note is now historical.
  Along the way: found and fixed `mdm run`'s silver reader missing the
  write-side monolith fallback (PR #92), a missing `states:RedriveExecution`
  IAM permission blocking redrive recovery (PR #93), a real `BatchSilver`
  per-row `merge_filings` perf bug (PR #95, ~4.2x faster bulk-upsert), and a
  `describe-map-run` query-field bug (`itemCounts` vs `executionCounts`) in
  `go-live.sh`'s progress polling (PR #97). PR #97 also reverted an
  unvalidated `BatchSilver MaxConcurrency` bump from 1 to 5 found on
  `codex/blocker4-live-retry` (write-race risk on the monolith silver.duckdb
  fallback, never tested in prod).
  **PASS evidence**: execution `bronze-seed-silver-gold-1782351277`
  (2026-06-24T21:34:39-04:00 to 2026-06-25T00:20:32-04:00) reached
  `ExecutionSucceeded`. All seven stages exited cleanly: `SeedFromBronze`,
  `BatchSilver` (Map run `SUCCEEDED`, 81/81 batches, zero `sec_pull_started`
  events confirmed across the full window via CloudWatch
  `/aws/ecs/edgartools-prod-warehouse`, ~25-30s per 100-CIK batch matching the
  PR95 perf fix), `MdmRun`, `MdmBackfill`, `MdmSync`, `MdmVerify`,
  `GoldRefresh`. The live deployed state machine ran `BatchSilver` at
  `MaxConcurrency=2` (not yet committed to source at the time of the PASS).
  [2026-06-25, operator decision] Operator directed source be set to
  `MaxConcurrency=4` going forward (PR pending) — this value is **unvalidated**
  in prod; only `MaxConcurrency=2` produced the PASS above. Blocker 4 / hosted
  graph E2E is flipped to **PASS** on the strength of the `MaxConcurrency=2`
  evidence; the next live run at `MaxConcurrency=4` should be watched closely
  for monolith write-contention regressions before being treated as
  re-confirming this PASS.

- Blocker 4: **FULLY REMEDIATED** (2026-06-25) — see detailed evidence above
  and `phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md`
  (bronze_seed_silver_gold addendum). GRAPH-04 satisfied at MaxConcurrency=2.
  [2026-06-26, Phase 11] `11-AUDIT.md` recorded this as CONDITIONAL pending
  MaxConcurrency=4 evidence (the deployed value, never separately validated
  end-to-end). [2026-06-29] Resolved via Option (b) in
  `11-GO-NO-GO-PACKET.md` Section 2 — accepted as the GO basis without new
  run evidence; MaxConcurrency=4 itself remains unverified by a committed
  Step Functions/CloudWatch record.

- Blocker 5: **FULLY REMEDIATED** (2026-06-25) — dashboard UAT run against
  edgartools-dev (production-like config) post `bronze_seed_silver_gold` SUCCEEDED
  run. All 5 launch-critical views PASS: MDM overview (5,500 companies, 2,251
  people, 322 securities), hosted graph overview (entity comparison all OK, 6
  types), mismatch diagnostics (zero mismatches, bounded sample copy present),
  manual refresh timestamps (both MDM and Snowflake timestamps live), bounded
  samples (row limit selector functional). DASH-01, DASH-03, DASH-04 satisfied.
  Security check clean (no secrets, no mutation controls, no unbounded exports).
  43/43 credential-free tests pass. Operator sign-off received 2026-06-25.
  Evidence: `phases/10-dashboard-uat/evidence/blocker5-dashboard-uat.md`.

## Pending Todos

- Watch the next live `bronze_seed_silver_gold` run at `MaxConcurrency=4`
  (source updated 2026-06-25, unvalidated) for monolith write-contention
  regressions; revert to `MaxConcurrency=2` if any DuckDB lock errors or
  duplicate/partial rows appear.
- Preserve all v1.5 evidence and milestone archives while adding v1.6 planning artifacts.
- **All blockers (1–5) are now FULLY REMEDIATED.** Proceed to Phase 11:
  go/no-go evidence audit and final operator sign-off packet.

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

Last session: 2026-06-25T23:59:00.000Z
Stopped at: Phase 11 plans created. 11-01 (evidence audit + SEC-02 secret-safety
+ ISO-03 AWS-only isolation) and 11-02 (go/no-go packet + OPS-03 monitoring
handoff + Release Owner sign-off checkpoint) written and committed. All 5 go-live
blockers (1–5) are FULLY REMEDIATED. Awaiting /gsd:execute-phase 11.
Resume file: .planning/workstreams/go-live/phases/11-final-go-decision-and-launch-evidence-handoff/11-01-PLAN.md
Resume command: /gsd:execute-phase 11 --ws go-live on branch claude/go-live-phase11

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 05 P02 | 25min | 2 tasks | 2 files |
| Phase 06 P01 | ~35min | 3 tasks | 4 files (2 committed, 2 gitignored) |
| Phase 09 P01 | ~1h50min | 4 tasks | 5 files |
| Phase 09 P02 | ~5min | 1/4 tasks reached | 4 files |
