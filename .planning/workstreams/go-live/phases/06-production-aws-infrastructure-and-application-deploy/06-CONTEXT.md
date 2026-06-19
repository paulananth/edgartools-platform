# Phase 6: Production AWS Infrastructure And Application Deploy - Context

**Gathered:** 2026-06-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 6 is the **first real, state-changing production action** of the entire
go-live workstream. v1.5 was readiness documentation and dry-run evidence
only; v1.6 starts executing the actual launch sequence, and Phase 6 is its
first step. This phase:

1. Bootstraps the real Terraform S3 state backend (`edgartools-prod-tfstate`)
   — confirmed live via `aws s3api head-bucket` that it does not exist yet.
2. Runs a real `terraform apply` for `infra/terraform/accounts/prod/` (passive
   infrastructure: VPC, subnets, security groups, S3/KMS, ECR, ECS
   cluster/logs, empty secret containers) — Plan 06-01.
3. Fixes the known `versions.tf` `required_version = "~> 1.14.7"` constraint
   bug directly on this branch (an explicit ISO-01 source-code exception,
   same pattern as Phase 4's dashboard README rewrite).
4. Populates the `edgartools-prod-edgar-identity` secret value (the
   `EDGAR_IDENTITY` user-agent string — not a credential, contains only a
   product name + contact email, same as the existing dev value pattern).
5. Runs the active AWS application deploy
   (`infra/scripts/deploy-aws-application.sh --env prod`) with explicit image
   refs and `--enable-mdm`, and captures/summarizes
   `infra/aws-prod-application.json` — Plan 06-02.
6. Updates `01-LAUNCH-GATE-MATRIX.md` rows for AWS passive infra, prod app
   manifest, and active deploy.

Phase 6 does **not**: populate any MDM secret values (postgres_dsn, neo4j,
api_keys, snowflake — that's Phase 8 / MDM-02), run the dev-bronze-to-prod-
bronze S3 sync beyond what the matrix's existing documented procedure
specifies, or touch Snowflake (Phase 7).

</domain>

<decisions>
## Implementation Decisions

### State Backend Bootstrap (D-01, D-02)

- **D-01:** Plan 06-01 creates the `edgartools-prod-tfstate` S3 bucket itself
  via explicit `aws s3api create-bucket` + `put-bucket-versioning` +
  `put-bucket-encryption` (SSE), evidenced as its own first step, **before**
  `terraform init -backend-config=backend.hcl`. Confirmed live (2026-06-19,
  `aws s3api head-bucket --bucket edgartools-prod-tfstate` → 404) that this
  bucket does not exist — this is not a dry-run assumption.
- **D-02:** Add S3-native state locking to `backend.hcl`
  (`use_lockfile = true` — Terraform 1.10+, no DynamoDB table needed).
  `versions.tf`'s existing `~> 1.14.7` constraint (once fixed per D-07) is
  well above the 1.10 minimum, so no separate version bump is needed for
  locking itself.

### First-Apply Approval Gate (D-03, D-04)

- **D-03:** The executor runs `terraform plan -out=tfplan`, shows the user
  the resource-add/change/destroy counts and resource list, and **waits for
  an explicit user go-ahead message** before running `terraform apply
  tfplan`. This is the project's first-ever real prod `terraform apply` —
  no auto-apply, even for a purely-additive plan.
- **D-04:** Apply uses the **saved plan file** (`terraform apply tfplan`),
  never a fresh re-plan at apply time. What the user approves is byte-
  identical to what executes — no drift window between review and apply.

### Secret Container Strategy (D-05, D-06)

- **D-05:** Terraform creates all 5 secret containers as **fresh, empty
  shells** — no `edgar_identity_secret_arn` override variable, no override
  for the 4 MDM secret variables. Confirmed live (2026-06-19,
  `aws secretsmanager describe-secret --secret-id
  edgartools-prod-edgar-identity` → `ResourceNotFoundException`) that none of
  these exist yet — consistent with "create fresh."
- **D-06:** Phase 6 is the **only** phase that populates a secret value
  directly: immediately after Terraform creates
  `edgartools-prod-edgar-identity`, Plan 06-01 or 06-02 runs
  `aws secretsmanager put-secret-value` with the `EDGAR_IDENTITY` user-agent
  string (e.g. `"EdgarTools Platform thepaulananth@gmail.com"` — same shape
  as the existing dev value in CLAUDE.md). This value is not sensitive (no
  password/token/key — it's a public-facing SEC EDGAR User-Agent header) and
  is required for the active app deploy in 06-02 to function. **Guardrail:**
  no other secret (the 4 MDM containers) gets a `put-secret-value` call in
  Phase 6 — those remain empty shells per the matrix's existing
  MDM-02/Phase-8 ownership.

### Pipeline Notifications (D-07, D-08)

- **D-07:** Set `pipeline_notifications_enabled = true` in the real (never
  committed) `terraform.tfvars` for this apply — enabled from the first prod
  apply, not deferred.
- **D-08:** `pipeline_failure_subscriber_email = "thepaulananth@gmail.com"`.

### versions.tf Bug Fix Ownership (D-09)

- **D-09:** Phase 6 fixes the `required_version = "~> 1.14.7"` constraint bug
  in `infra/terraform/accounts/prod/versions.tf` **directly**, as an explicit
  ISO-01 source-code exception — same precedent as Phase 4's dashboard
  README rewrite (`04-CONTEXT.md` D-01/D-02). The fix is a hard blocker for
  any real apply (per launch gate matrix row 12) and is in scope because
  Phase 6 is the phase that runs that apply. Commit lands on the go-live
  branch like any other Phase 6 commit — no separate non-go-live commit.

### Secret Safety (consistent with all prior phases)

- **D-10:** No secrets, DSNs, passwords, tokens, raw connector exceptions,
  Terraform state, or sensitive generated deployment values in any committed
  Phase 6 file. `infra/aws-prod-application.json` is summarized only (file
  presence, top-level keys, state-machine names, digest-vs-tag image-ref
  format) per Phase 1 D-15 — never committed in full. The `EDGAR_IDENTITY`
  value itself (D-06) is set via AWS CLI directly into Secrets Manager; it is
  never pasted into any committed file, even though it isn't a high-
  sensitivity secret.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 6 requirements and goal
- `.planning/workstreams/go-live/ROADMAP.md` — Phase 6 goal, requirements
  (LIVE-04, LIVE-05), plans 06-01/06-02, and success criteria 1-4.
- `.planning/workstreams/go-live/REQUIREMENTS.md` — full LIVE-04/LIVE-05
  definitions and v1.6 traceability table.
- `.planning/workstreams/go-live/PROJECT.md` — v1.6 milestone goal (flip
  NO-GO to GO), Active Milestone Goals, and Scope Boundaries (AWS/Snowflake-
  only, no Terraform-owned runtime secrets).

### Launch gate matrix (rows Phase 6 updates)
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`
  rows 12 ("AWS passive infrastructure outputs" — includes the versions.tf
  bug note), 13 ("Production bronze data reuse from dev bronze" — documented
  S3-to-S3 sync procedure, copy-only, no `--delete`), 14 ("Production AWS
  application manifest"), 15 ("AWS active application deploy"), 16 ("Stale
  edgar-identity secret ARN mitigation"), 17 ("ECR cleanup deleting in-flight
  image digest mitigation").

### Runbook precedent (mirror/extend for Phase 6)
- `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md`
  — full documented deploy command, ECR image-promotion procedure (D-05/D-06
  re-tagging within the same account), MDM secret name list, parameter
  resolution order, `--skip-build`/`--enable-mdm` hard-fail conditions,
  edgar-identity ARN freshness requirement, ECR-cleanup ordering requirement.
  Phase 6 executes what this runbook documented as dry-run; do not
  re-derive the command shape from scratch.

### v1.5 go/no-go packet (what Phase 6 starts resolving)
- `.planning/workstreams/go-live/phases/05-go-no-go-launch-evidence-and-handoff/05-GO-NO-GO-PACKET.md`
  Blocker 1 ("Prod AWS infrastructure not yet applied") — Phase 6 is its
  remediation. Read before writing the Phase 6 plan so the plan's
  success criteria map directly onto this blocker's resolution.

### Terraform source (what gets applied/fixed)
- `infra/terraform/accounts/prod/main.tf`, `variables.tf`, `outputs.tf`,
  `providers.tf`, `versions.tf` (D-09 fix target),
  `mdm_secret_moves.tf`, `terraform.tfvars.example`, `backend.hcl.example`
  (D-01/D-02 — bucket name `edgartools-prod-tfstate`, key
  `accounts/prod/terraform.tfstate`, region `us-east-1`, add
  `use_lockfile = true`).

### Deployment script (Plan 06-02)
- `infra/scripts/deploy-aws-application.sh` — production deploy entry point.
  Exact flags documented in `runbook/aws-deploy.md` section 2: `--env prod`,
  `--image-ref`, `--mdm-image-ref`, `--enable-mdm`, `--skip-build`,
  `--edgar-identity-secret-arn`.

### Project policy
- `CLAUDE.md` §"Image management" — tagging strategy (`:dev`/`sha-<hash>`/
  `:prod`), `EDGAR_IDENTITY` env var shape
  (`"EdgarTools Platform <email>"`) used as the D-06 secret value template.
- `CLAUDE.md` "Executing actions with care" — governs the D-03 approval-gate
  decision; this phase is the canonical example of a hard-to-reverse,
  real-infrastructure action requiring explicit confirmation.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `infra/scripts/deploy-aws-application.sh` — already supports every flag
  Phase 6 needs (`--env prod`, `--image-ref`, `--mdm-image-ref`,
  `--enable-mdm`, `--skip-build`, `--edgar-identity-secret-arn`). No script
  changes needed — Phase 6 invokes it as documented.
- `infra/terraform/accounts/prod/` — all `.tf` files exist and were
  `terraform plan`-validated in Phase 2 (22/22 output names, resource-add
  count confirmed read-only). Only `versions.tf` needs the D-09 fix; no
  other `.tf` changes anticipated.

### Established Patterns
- ECR image promotion: re-tag existing `:dev`/`sha-<hash>` images as `:prod`
  within the same repos (`edgartools-dev-warehouse`, `edgartools-dev-mdm`)
  in account `077127448006` — no separate prod account/ECR (Phase 2 D-05/D-06).
  `runbook/aws-deploy.md` section 1 has the exact re-tag commands.
- Generated JSON summarization: `infra/aws-prod-application.json` gets a
  non-secret summary in `evidence/aws.md` (file presence, top-level keys,
  state-machine names, image-ref format) — never committed whole (Phase 1
  D-15, carried forward).
- Dev-precedent annotation convention does NOT apply to Phase 6 evidence —
  this phase produces real prod evidence, not a dev-proxy run.

### Integration Points
- Phase 6 updates `01-LAUNCH-GATE-MATRIX.md` rows 12-17 from `BLOCKED` toward
  `PASS` (or a more specific blocked state with new evidence, if something
  fails).
- Phase 7 (Snowflake) depends on Phase 6's AWS storage/export bucket outputs.
- Phase 8 (MDM secrets) depends on Phase 6's empty MDM secret containers
  existing (created, not populated).

</code_context>

<specifics>
## Specific Ideas

- Bucket bootstrap order: create `edgartools-prod-tfstate` (with versioning +
  encryption) → add `use_lockfile = true` to a real `backend.hcl` (copied
  from `.example`) → `terraform init -backend-config=backend.hcl` →
  `terraform plan -out=tfplan` → show plan to user → wait for explicit
  go-ahead → `terraform apply tfplan`.
- `EDGAR_IDENTITY` secret value to put: `"EdgarTools Platform
  thepaulananth@gmail.com"` (same shape as the existing dev env var in
  CLAUDE.md's required env vars table).
- `pipeline_failure_subscriber_email = "thepaulananth@gmail.com"`,
  `pipeline_notifications_enabled = true` in the real tfvars.
- versions.tf fix: correct the `required_version = "~> 1.14.7"` constraint
  (exact corrected value to be determined during planning/research — the
  matrix row notes it was "currently only worked around via a temporary,
  reverted edit per Pattern 1" in Phase 2, so the prior dry-run already
  identified the right value; planner should check Phase 2 evidence for
  the specific fix that was reverted).

</specifics>

<deferred>
## Deferred Ideas

- MDM secret value population (postgres_dsn, neo4j, api_keys, snowflake) —
  explicitly Phase 8 / MDM-02, not Phase 6.
- Snowflake native-pull stack deploy — Phase 7.
- Any state-changing action beyond passive infra apply + active app deploy +
  edgar-identity secret value — out of Phase 6 scope per ROADMAP.md.

None — no todos matched Phase 6 scope in cross_reference_todos check.

</deferred>

---

*Phase: 6-production-aws-infrastructure-and-application-deploy*
*Context gathered: 2026-06-19*
