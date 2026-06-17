# Phase 2: AWS And Snowflake Production Deployment Dry Run - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase produces a validated, non-secret production deployment runbook for
the AWS active application, the Snowflake native-pull stack, and dbt gold —
covering LIVE-02, SNOW-01, and SNOW-02. It documents exact commands, captures
what evidence CAN be produced today (read-only plans, dev-target dbt runs,
script logic checks), and records every remaining gap as a `BLOCKED` row in
the Phase 1 launch gate matrix with owner, required fix, and required rerun
proof. It does not provision a new production AWS account, apply prod
Terraform, run state-changing prod deploys, or execute Snowflake DDL against a
production target.

</domain>

<decisions>
## Implementation Decisions

### Dry-Run Scope

- **D-01:** Phase 2 is document-and-validate only. No `terraform apply` for
  `infra/terraform/accounts/prod/`, no `deploy-aws-application.sh --env prod`
  execution, and no Snowflake DDL execution against a production target. The
  phase produces runbook commands, evidence-file entries for checks that CAN
  run today, and `BLOCKED` matrix rows for everything that requires real prod
  state — consistent with Phase 1 D-12/D-13 (unresolved items are `BLOCKED`
  rows, not evidence entries).
- **D-02:** `infra/terraform/accounts/prod/` readiness is validated via
  read-only `terraform plan` only (no real backend/tfvars exist yet — only
  `.example` files). Actual `terraform apply` for prod is deferred to a future
  operator-driven cutover and is out of scope for this phase.

### dbt / Snowflake Validation

- **D-03:** dbt validation runs `dbt compile` and `dbt run`/`dbt test` against
  the EXISTING DEV Snowflake target as a logic-validation proxy — NOT prod
  execution. Results are recorded in `evidence/snowflake.md` explicitly
  labeled as dev-precedent (per Phase 1 D-18 dev-vs-prod distinction).
- **D-04:** The exact prod-target dbt commands (with placeholders for the
  production Snowflake connection and database) are documented as the
  "required fix" for a `BLOCKED` row pending a production Snowflake
  connection — no prod Snowflake connection currently exists in this
  environment (confirmed via `snow connection list`: only two unrelated
  personal connections, neither named for this project's prod/dev).

### Production AWS Account & Image Strategy

- **D-05:** `aws-admin-dev` and `aws-admin-prod` resolve to the SAME AWS
  account — confirmed live via `aws sts get-caller-identity` for both
  profiles: both return account `077127448006`, IAM user `cli-access`. "Prod"
  is a same-account, prefix-distinguished resource set (separate Terraform
  root `infra/terraform/accounts/prod/`, `:prod`-tagged ECR images, a future
  `infra/aws-prod-application.json`), NOT a separate AWS account. Downstream
  agents must not assume a separate prod account/ECR exists.
- **D-06:** The runbook documents promoting existing `:dev` / `sha-<hash>`
  warehouse and MDM images to `:prod` tags within the SAME ECR repos in
  account `077127448006`, then capturing the resulting digests for
  `deploy-aws-application.sh --image-ref` / `--mdm-image-ref`. No cross-account
  image build/push chain is needed.

### MDM Flag In Documented Deploy Command

- **D-07:** The documented production deploy command
  (`deploy-aws-application.sh --env prod ...`) includes `--enable-mdm`, so
  Phase 3 has a single deployed target to test against rather than a second
  deploy pass. The required MDM Secrets Manager secret names (Postgres DSN,
  API keys, Snowflake settings, legacy/empty graph containers) are listed as
  required-identifier `BLOCKED` items in the Phase 2 evidence/matrix update;
  actual secret creation/population remains Phase 3 (MDM-01) scope.

### Agent Discretion

None. The user made explicit decisions for all selected gray areas.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Go-Live Workstream

- `.planning/workstreams/go-live/PROJECT.md` - Milestone scope, "prepare for go-live" framing, scope boundaries (AWS-only, Terraform-passive, no runtime secrets in Terraform).
- `.planning/workstreams/go-live/REQUIREMENTS.md` - Phase 2 requirements `LIVE-02`, `SNOW-01`, `SNOW-02`.
- `.planning/workstreams/go-live/ROADMAP.md` - Phase 2 goal, dependencies (Phase 1), and success criteria.
- `.planning/workstreams/go-live/STATE.md` - Current go-live state, known inputs, and blockers.
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-CONTEXT.md` - Phase 1 decisions D-01..D-29 (blocker classification, evidence format, secret-safety rules, dev-vs-prod distinction, production identifier checklist) — all still in force for Phase 2.
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md` - The 9 `BLOCKED` rows this phase updates (AWS passive infra outputs, prod app manifest, AWS active deploy, edgar-identity ARN mitigation, ECR cleanup mitigation, Snowflake native-pull stack, Snowflake deployer grants, dbt compile/run/test, `EDGARTOOLS_GOLD_STATUS`/freshness) plus the Required Production Identifiers checklist.
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/aws.md` - Phase 2 fills AWS-side entries here.
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/snowflake.md` - Phase 2 fills Snowflake/dbt-side entries here.

### Project Policy

- `.planning/PROJECT.md` - Locked AWS-only, Terraform-passive, runtime-role, and storage decisions.
- `AGENTS.md` - Repo operating rules, AWS path, tooling, and secret-safety expectations.
- `CLAUDE.md` §"Image management" - Tagging strategy table (`:dev` / `:sha-<hash>` / `:prod`), manual AWS build-and-deploy recipe, dbt dynamic-table full-refresh gap and `EDGARTOOLS_DEV_DEPLOYER` grants caveat relevant to D-03's dev-target dbt run.

### Deployment Scripts And Terraform

- `infra/scripts/deploy-aws-application.sh` - Production deploy entry point: `--env prod`, `--image-ref`, `--mdm-image-ref`, `--enable-mdm`, `--skip-build`, generated app summary output (`infra/aws-prod-application.json`).
- `infra/scripts/deploy-snowflake-stack.sh` - Snowflake native-pull/dbt/dashboard wrapper: `--env`, `--snow-connection`, `--run-validation`, `--run-dbt`.
- `infra/terraform/accounts/prod/` - Passive AWS infra root (modules: network, storage, runtime, pipeline_notifications); only `terraform.tfvars.example` / `backend.hcl.example` exist — no real tfvars/state/backend configured yet.
- `infra/terraform/snowflake/accounts/prod/` - Snowflake-side prod Terraform root (parallel structure to dev).
- `infra/snowflake/dbt/edgartools_gold/` - dbt project for `dbt compile`/`dbt run`/`dbt test` validation (D-03/D-04).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `infra/scripts/deploy-aws-application.sh`: documents the exact prod deploy invocation shape (env, image refs, MDM flags) without running it.
- `infra/scripts/deploy-snowflake-stack.sh`: documents the exact Snowflake validation/dbt invocation shape for prod, reusable as-is once a prod Snowflake connection exists.
- `infra/terraform/accounts/prod/main.tf` + module set (`network`, `storage`, `runtime`, `pipeline_notifications`): `terraform plan` against this root is the read-only check for "AWS passive infrastructure outputs" readiness.
- `infra/snowflake/dbt/edgartools_gold/`: existing dbt project, already proven against dev — reuse for D-03's dev-target compile/run/test proxy.

### Established Patterns

- Evidence files record only commands actually run; unexecuted/blocked items are matrix rows, not evidence entries (Phase 1 D-13, carried forward).
- Dev proof is precedent only — every dev-target result in `evidence/snowflake.md` must be labeled as such (Phase 1 D-18).
- Generated JSON (`infra/aws-*-application.json`) is summarized only — file presence, top-level keys, state-machine names, image-ref format (Phase 1 D-15).
- Image promotion via re-tagging (`:dev`/`sha-<hash>` → `:prod`) within the same ECR repos is the established tagging convention (CLAUDE.md "Tagging strategy").

### Integration Points

- Phase 2 updates `01-LAUNCH-GATE-MATRIX.md` row statuses (from `BLOCKED` toward either a documented-blocker-with-runbook state or `PASS` for checks that succeed read-only/dev-proxy today).
- Phase 2 appends to `evidence/aws.md` (terraform plan summary, image re-tag/digest capture procedure, edgar-identity ARN and ECR-cleanup mitigation checks) and `evidence/snowflake.md` (dev-target dbt compile/run/test results, prod-target command templates).
- Phase 3 (MDM Hosted Graph E2E Acceptance) consumes the Phase 2 documented deploy command (with `--enable-mdm`) and the MDM secret-name `BLOCKED` list as its starting point.

</code_context>

<specifics>
## Specific Ideas

- Confirmed live (read-only `aws sts get-caller-identity`) that `aws-admin-dev`
  and `aws-admin-prod` are the same AWS account (`077127448006`) and same IAM
  user (`cli-access`) — prod is same-account, prefix-distinguished, not a
  separate account/ECR.
- Image promotion path: re-tag existing `:dev`/`sha-<hash>` images as `:prod`
  in the same ECR repos, then capture digests for `--image-ref`/`--mdm-image-ref`.
- dbt validation proxy: run against the dev target, label results as
  dev-precedent, and document the prod-target command (with placeholders) as
  the `BLOCKED` row's required fix.
- Documented deploy command includes `--enable-mdm`; MDM secret names are a
  required-identifier `BLOCKED` list handed to Phase 3.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 2-AWS And Snowflake Production Deployment Dry Run*
*Context gathered: 2026-06-14*
