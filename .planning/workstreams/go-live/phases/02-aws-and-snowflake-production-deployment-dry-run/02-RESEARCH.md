# Phase 2: AWS And Snowflake Production Deployment Dry Run - Research

**Researched:** 2026-06-14
**Domain:** Infrastructure-as-code readiness validation, deployment runbook documentation (AWS ECS/Step Functions + Snowflake native-pull/dbt), no application code changes
**Confidence:** HIGH (most findings are direct, repeatable, read-only command output from this session)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

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

### Claude's Discretion

None. The user made explicit decisions for all selected gray areas.

### Deferred Ideas (OUT OF SCOPE)

None - discussion stayed within phase scope.

</user_constraints>

## Summary

Phase 2 is a documentation-and-evidence phase: produce an exact, runnable production
deployment runbook for the AWS active application (LIVE-02), the Snowflake native S3
pull stack (SNOW-01), and dbt gold (SNOW-02), while updating
`01-LAUNCH-GATE-MATRIX.md` and the two Phase 1 evidence files. Live discovery in this
session confirms **zero production AWS resources exist** (no `edgartools-prod-*` S3
buckets, no prod ECS cluster, no prod Secrets Manager secrets, no prod Terraform
state bucket) and **zero production Snowflake connections/credentials are configured**
in this environment (`snow connection list` shows only unrelated personal
connections). This is consistent with CONTEXT.md D-01/D-02 — Phase 2 cannot and must
not change this; it documents the path to production state, not the state itself.

Three findings materially change what the planner should expect versus the phase
description's framing:

1. **All four prod-side Terraform roots have a version-constraint bug** (`required_version
   = "~> 1.14.7"` / `"~> 1.14.8"`, pessimistic, accepts only `1.14.x`) that blocks
   `terraform init`/`plan`/`validate` with the locally installed Terraform `1.15.5`. The
   dev-side equivalents use `>= 1.14.7` (permissive) and work fine. This is a one-line
   fix per file, is independent of any prod resource state (it changes only the
   accepted-Terraform-version constraint in source, not any provisioned infrastructure),
   and is a prerequisite for D-02's read-only `terraform plan`. **The default, in-scope
   path is a TEMPORARY edit-then-revert within the read-only plan procedure itself —
   nothing is committed.** A separately-committed fix to the 4 `versions.tf` files is
   technically attractive (it's a real bug, zero provisioning side effects) but touches
   source files under `infra/` that are OUTSIDE `.planning/workstreams/go-live/`, and
   Phase 2's CONTEXT.md boundary does not explicitly scope `infra/`-tree source edits —
   per **ISO-01** ("work stays isolated under `.planning/workstreams/go-live/`... unless
   a phase explicitly scopes source-code or runbook changes"), that would require
   explicit user authorization to expand Phase 2's scope. See Pitfall 1 and Pattern 1.
2. **`deploy-snowflake-stack.sh --env prod` is a structural no-op today** — it dies at
   the very first `backend.hcl` existence check (across 3 Terraform roots), before
   touching Snowflake at all. It is fundamentally a 3-root `terraform apply`
   orchestrator with dbt/validation/dashboard as opt-in tails, not primarily a
   validation wrapper. This single fact is itself the proof that SNOW-01 prod execution
   is blocked — no command needs to be "not run."
3. **`edgartools-prod-warehouse`/`edgartools-prod-mdm` ECR repos do not exist** — only
   `edgartools-dev-*` repos exist. D-06's "promote `:dev`/`sha-<hash>` images to `:prod`
   tags within the SAME ECR repos" is ambiguous given this: the only executable
   interpretation within D-01/D-02 scope is tagging `edgartools-dev-warehouse:prod` /
   `edgartools-dev-mdm:prod` (same dev-named repo, new tag) — NOT a separate
   `edgartools-prod-*` repo (which doesn't exist and would require a Terraform apply).
   This is flagged as an open question/assumption for the planner.
4. **`dbt compile` requires LIVE Snowflake credentials**, not placeholders — dbt
   1.11.8 + snowflake adapter 1.11.5 performs a connection check during compile. No
   dev dbt/Snowflake credential secret exists in AWS Secrets Manager in this
   environment, so D-03's dev-precedent dbt run is execution-blocked on
   operator-supplied credentials at runtime — this should be a `checkpoint:human-verify`
   or environment-setup task, not assumed available.

**Primary recommendation:** Structure Phase 2 plans around three runbook documents
(AWS deploy, Snowflake native-pull/dbt, image promotion) plus matrix/evidence updates;
treat the read-only `terraform plan` for `infra/terraform/accounts/prod/` (via the
proven `override.tf` local-backend technique plus a TEMPORARY, reverted
`versions.tf` edit, Pattern 1) as the one piece of *executable* work in this phase —
zero commits required — and otherwise produce commands-with-placeholders +
BLOCKED-row updates for everything that needs real prod state or credentials. If the
planner/user wants the real `versions.tf` bug fixed permanently as part of this
phase, that is an OPTIONAL, separately-authorized task (Pattern 0) requiring an
explicit scope-expansion decision under ISO-01 — not the default path.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| AWS passive infrastructure (VPC, S3, ECR, ECS cluster, empty secrets) | Database/Storage (Terraform-managed) | — | Provisioned once via `terraform apply`; Phase 2 only validates via `terraform plan` |
| AWS active application deploy (ECS task defs, Step Functions state machines) | API/Backend (deploy script) | — | `deploy-aws-application.sh` is the sole runtime-deploy mechanism; Terraform never touches this |
| ECR image promotion (`:dev` → `:prod` tag) | CDN/Static equivalent (artifact registry) | — | Pure registry operation (`docker tag`/`push` or `aws ecr put-image`), no compute |
| Snowflake native S3 pull stack (storage integration, stage, pipe, stream, tasks) | Database/Storage | API/Backend (deploy wrapper) | Terraform-managed Snowflake objects; `deploy-snowflake-stack.sh` orchestrates 3 Terraform roots + manifest task |
| dbt gold dynamic tables + `EDGARTOOLS_GOLD_STATUS` | Database/Storage | — | dbt-managed transformation layer inside Snowflake; runs via `dbt run`/`test --target prod` |
| Launch gate matrix / evidence docs | Documentation (this workstream) | — | Pure planning artifact, not runtime |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LIVE-02 | Operator can deploy/update active AWS application components through existing deploy scripts with explicit image refs, MDM enabled when required, no Terraform-owned runtime commands or secret values. | `deploy-aws-application.sh` flag inventory and resolution-order analysis (Architecture Patterns, Code Examples); ECR promotion procedure for D-06; manifest JSON shape for evidence/aws.md; matrix rows 2,3,4,5 update guidance. |
| SNOW-01 | Operator can deploy/validate the Snowflake native S3 pull stack for production (storage integration, stage, source mirror tables, pipe, stream, procedures, tasks, grants). | `deploy-snowflake-stack.sh` flow analysis showing the `backend.hcl` hard-stop; `native_pull` module resource inventory; matrix row 6 update guidance — stays BLOCKED with documented command. |
| SNOW-02 | Operator can run dbt compile/run/test for the production target and capture non-secret `EDGARTOOLS_GOLD_STATUS`/dynamic-table freshness evidence. | dbt prod target config from `profiles.yml.example`; live-connection-check finding for `dbt compile`; `docs/runbook.md` canonical commands; `edgartools_gold_status.sql` shape for the freshness table; matrix rows 7,8,9 update guidance. |
</phase_requirements>

## Standard Stack

Not applicable — this phase installs no new libraries, frameworks, or packages. All
work uses existing repo scripts (`infra/scripts/*.sh`), existing Terraform roots, and
existing dbt project (`infra/snowflake/dbt/edgartools_gold/`). No `npm install`/`pip
install`/`cargo add` of any kind.

## Package Legitimacy Audit

Not applicable — no external packages are installed in this phase. Skip slopcheck/
registry verification steps.

## Architecture Patterns

### System Architecture Diagram

```
Operator (local shell, AWS/Snowflake CLI profiles)
   |
   |--[1: AWS infra check]--> terraform plan (infra/terraform/accounts/prod/)
   |        Pattern 1 (DEFAULT): temporary, in-procedure edit+revert of
   |        versions.tf ("~> 1.14.x" -> ">= 1.14.x", Pitfall 1) + local-backend
   |        override.tf -- NOTHING COMMITTED, git status clean afterward
   |        OPTIONAL (Pattern 0, requires explicit user authorization per
   |        ISO-01): commit the versions.tf fix for real as its own task
   |        output --> "AWS passive infrastructure outputs" matrix row
   |
   |--[2: image promotion]--> ECR re-tag (:dev/sha-<hash> -> :prod, same repo)
   |        edgartools-dev-warehouse, edgartools-dev-mdm (only repos that exist)
   |        output --> digest capture --> --image-ref / --mdm-image-ref values
   |
   |--[3: AWS active deploy]--> deploy-aws-application.sh --env prod
   |        --image-ref <digest> --mdm-image-ref <digest> --enable-mdm --skip-build
   |        BLOCKED: requires prod passive infra (cluster, roles, secrets) to exist
   |        --> documents command only; writes infra/aws-prod-application.json (future)
   |
   |--[4: Snowflake native-pull]--> deploy-snowflake-stack.sh --env prod ...
   |        DIES at backend.hcl check (3 Terraform roots: access/aws/prod,
   |        snowflake/accounts/prod, access/snowflake/accounts/prod)
   |        --> matrix row 6 stays BLOCKED; document command + required backend.hcl
   |
   |--[5: dbt validation proxy]--> cd infra/snowflake/dbt/edgartools_gold
   |        dbt compile / dbt run / dbt test --target dev  (DEV = logic-validation proxy)
   |        requires LIVE dev Snowflake credentials (DBT_SNOWFLAKE_*)
   |        --> evidence/snowflake.md, labeled dev-precedent
   |        ALSO: document --target prod command with placeholder env vars
   |              --> matrix rows 7,8,9
   |
   `--[6: gold status query]--> SELECT * FROM <DB>.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS
            requires steps 4+5 (prod) to have succeeded first --> stays BLOCKED
```

### Recommended Runbook Document Structure

```
.planning/workstreams/go-live/phases/02-.../
├── 02-RESEARCH.md                       (this file)
├── runbook/
│   ├── aws-deploy.md          # exact deploy-aws-application.sh prod invocation,
│   │                           # image-promotion procedure, manifest shape
│   ├── snowflake-native-pull.md # deploy-snowflake-stack.sh prod invocation +
│   │                           # backend.hcl prerequisite + native_pull resource list
│   └── dbt-gold.md             # dev-precedent dbt run + prod-target placeholder cmds
└── (updates to ../01-.../01-LAUNCH-GATE-MATRIX.md and evidence/{aws,snowflake}.md)
```

(Exact file names/locations are the planner's discretion — CONTEXT.md does not
mandate a `runbook/` subdirectory; the canonical update targets are
`01-LAUNCH-GATE-MATRIX.md`, `evidence/aws.md`, `evidence/snowflake.md`.)

### Pattern 1: Read-only `terraform plan` via temporary versions.tf edit + local-backend override (DEFAULT path)

**What:** Run a fully read-only `terraform plan` against the real AWS account without
configuring the real S3 backend or writing any tfvars, AND without leaving any
uncommitted or committed source changes behind — using a temporary, in-procedure edit
of `versions.tf` (reverted at the end) plus Terraform's override-file mechanism.

**When to use:** This is the DEFAULT, in-scope procedure for the "AWS passive
infrastructure outputs" matrix row (D-02). It requires no scope decision from the
user/planner — everything it touches is reverted before the procedure ends, and `git
status --short` is clean afterward. Use this unless the user/planner has explicitly
authorized Pattern 0 (the committed fix) as an additional, separately-scoped task.

Also applicable to the 3 Snowflake-side prod roots IF SNOW-01 documentation wants a
plan preview (though those roots additionally need real `TF_VAR_snowflake_*` values to
plan meaningfully — AWS-side plan is the practical target for Phase 2).

**Procedure (fully reversible — nothing committed, nothing left uncommitted):**

```bash
cd infra/terraform/accounts/prod

# 1. TEMPORARY fix for Pitfall 1's version-constraint bug — edit in place,
#    will be reverted in step 4. Do NOT commit this change.
#    required_version = "~> 1.14.7"  ->  required_version = ">= 1.14.7"
#    (apply the analogous ">= 1.14.8" edit if running this against the
#    Snowflake-side roots instead)

# 2. Add a local-backend override (NOT committed — delete in step 4).
cat > override.tf <<'EOF'
terraform {
  backend "local" {
    path = "/tmp/edgartools-prod-plan/terraform.tfstate"
  }
}
EOF

# 3. Init and plan with defaults (zero required variables).
terraform init -input=false -no-color
terraform plan -input=false -no-color

# 4. Revert EVERYTHING — restore versions.tf to its original "~> 1.14.7"
#    content, remove override.tf, .terraform/, .terraform.lock.hcl,
#    terraform.tfstate*, and /tmp/edgartools-prod-plan/.
git checkout -- versions.tf
rm -rf override.tf .terraform .terraform.lock.hcl terraform.tfstate* /tmp/edgartools-prod-plan
git status --short   # MUST show clean — confirms nothing committed or left dirty
```

Result observed this session (with the temporary fix applied): `Plan: 37
to add, 0 to change, 0 to destroy` against real AWS account `077127448006`, zero risk
to real state (local backend, never applied), and the temporary edit was fully
reverted (`git status --short` clean) after the experiment. This is the evidence shape
for the "AWS passive infrastructure outputs" matrix row — record the resource COUNT
and that `plan` succeeded, not the full plan body (per D-15 generated-output
redaction discipline, applied analogously to plan output). The evidence entry should
also note that the `versions.tf` version-constraint bug (Pitfall 1) is a real,
unfixed repo issue discovered during this check — recorded as a "required fix" note
for whoever next touches these Terraform roots, NOT as something Phase 2 fixed.

### Pattern 0 (OPTIONAL, requires explicit user authorization): versions.tf constraint fix as its own committed task

**What:** Change `required_version = "~> 1.14.7"` to `">= 1.14.7"` (and `"~> 1.14.8"`
to `">= 1.14.8"` for the two Snowflake-side roots) in all 4 prod-side `versions.tf`
files, matching the existing dev-side pattern — landed as a real, permanent, committed
fix rather than a temporary edit-then-revert.

**When to use:** ONLY if the user/planner explicitly decides to expand Phase 2's scope
to include this small `infra/`-tree source commit. This is a genuine, low-risk repo
bug (one-line-per-file, no provisioning side effects, provider version pins
unaffected) and fixing it for real is technically attractive — Pattern 1's
temporary-edit approach means the bug remains in the repo for the next person who
needs to plan/apply these roots. However:

- The phase boundary in `02-CONTEXT.md` describes Phase 2 as producing "a validated,
  non-secret production deployment runbook" and explicitly lists what it does NOT do
  (provision prod, apply prod Terraform, run state-changing prod deploys, execute prod
  Snowflake DDL) — it does not explicitly say "Phase 2 may commit source fixes under
  `infra/`."
- **ISO-01** ("Work stays isolated under `.planning/workstreams/go-live/` and reviewed
  launch docs unless a phase explicitly scopes source-code or runbook changes") is the
  governing constraint: `infra/terraform/**/prod/versions.tf` is a source file outside
  `.planning/workstreams/go-live/`, and Phase 2's CONTEXT.md does not explicitly scope
  this edit.

Because of this, Pattern 0 is NOT the default. If the planner wants to take this path,
the first task in the Phase 2 plan should be a `checkpoint:human-verify` (or
equivalent) asking the user to explicitly authorize a small scope expansion ("commit a
one-line Terraform version-constraint fix in `infra/terraform/{accounts,
snowflake/accounts,access/aws/accounts,access/snowflake/accounts}/prod/versions.tf` as
part of Phase 2") BEFORE any such commit is made. If the user declines or this
checkpoint is skipped, fall back to Pattern 1 (temporary edit-then-revert), which
requires no authorization and still produces the same plan-output evidence.

**Files that would be edited (one line each), if authorized:**
- `infra/terraform/accounts/prod/versions.tf`: `"~> 1.14.7"` -> `">= 1.14.7"`
- `infra/terraform/snowflake/accounts/prod/versions.tf`: `"~> 1.14.8"` -> `">= 1.14.8"`
- `infra/terraform/access/snowflake/accounts/prod/versions.tf`: `"~> 1.14.8"` -> `">= 1.14.8"`
- `infra/terraform/access/aws/accounts/prod/versions.tf`: `"~> 1.14.7"` -> `">= 1.14.7"`

**Verification:** `terraform validate` (with `-backend=false` or Pattern 1's
`override.tf`) in each of the 4 roots no longer fails with "Unsupported Terraform
Core version."

### Pattern 2: `deploy-aws-application.sh` flag/resolution-order documentation

**What:** Document the exact prod invocation without running it.

```bash
# Source: infra/scripts/deploy-aws-application.sh (read in full this session)
bash infra/scripts/deploy-aws-application.sh \
  --env prod \
  --image-ref "077127448006.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-warehouse@sha256:<DIGEST>" \
  --mdm-image-ref "077127448006.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-mdm@sha256:<DIGEST>" \
  --enable-mdm \
  --skip-build \
  --edgar-identity-secret-arn "<freshly-looked-up-ARN>"
```

Key behaviors to document in the runbook:
- Parameter resolution order: (1) CLI flag, (2) `infra/aws-prod-application.json`
  manifest if present, (3) AWS API discovery / naming convention
  (`edgartools-prod-*`).
- `--skip-build` REQUIRES `--image-ref` (hard `fail` otherwise).
- `--enable-mdm` REQUIRES all 4 MDM secret ARNs resolvable
  (`edgartools-prod/mdm/{postgres_dsn,neo4j,api_keys,snowflake}`) — these are
  Terraform-created empty containers; Phase 3/MDM-01 populates values.
- The script unconditionally (non-fatally) runs `cleanup-ecr-images.sh --env prod
  --apply` before build/deploy — Pitfall 3 below covers the digest-invalidation
  hazard this creates.
- Hard `fail`s today on cluster ARN, ECR URL, all 3 buckets, edgar-identity secret
  ARN, 3 IAM role ARNs, and subnet/SG discovery — **all of these require the prod
  Terraform `runtime`/`network`/`storage` modules to have been applied first**. This
  is the structural reason the "AWS active application deploy" matrix row stays
  BLOCKED pending a future prod `terraform apply` (out of scope for Phase 2 per D-01).

### Pattern 3: ECR image promotion (D-06 interpretation)

**What:** Re-tag existing `:dev`/`:sha-<hash>` images as `:prod` within the SAME repo
(`edgartools-dev-warehouse`, `edgartools-dev-mdm` — the only repos that exist).

```bash
# Confirmed live this session: edgartools-prod-warehouse / edgartools-prod-mdm
# do NOT exist. Only edgartools-dev-warehouse and edgartools-dev-mdm exist.
ECR=077127448006.dkr.ecr.us-east-1.amazonaws.com

# Discover current :dev digest (no docker pull needed — registry API)
WAREHOUSE_DEV_DIGEST=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --image-ids imageTag=dev \
  --query 'imageDetails[0].imageDigest' --output text)

MDM_DEV_DIGEST=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-mdm \
  --image-ids imageTag=dev \
  --query 'imageDetails[0].imageDigest' --output text)

# Re-tag via registry-side manifest copy (no local docker pull/push needed)
MANIFEST=$(aws ecr batch-get-image --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --image-ids imageDigest="$WAREHOUSE_DEV_DIGEST" \
  --query 'images[0].imageManifest' --output text)
aws ecr put-image --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --image-tag prod \
  --image-manifest "$MANIFEST"

# Repeat analogous put-image for edgartools-dev-mdm with $MDM_DEV_DIGEST

# Capture the digest form for --image-ref / --mdm-image-ref (digest is
# immutable and identical regardless of which tag points to it):
echo "${ECR}/edgartools-dev-warehouse@${WAREHOUSE_DEV_DIGEST}"
echo "${ECR}/edgartools-dev-mdm@${MDM_DEV_DIGEST}"
```

This procedure is read-only-safe to PLAN (the `aws ecr describe-images` calls can run
today) but the `put-image`/tag-mutation calls are state-changing — flag as the
"image-ref capture procedure" to document, with the describe-images calls as
immediately runnable evidence (current digests for `:dev` tags) and the `put-image`
step as part of the prod-cutover runbook (operator-executed at deploy time, not
during Phase 2 itself, since D-01 restricts to document-and-validate).

### Pattern 4: dbt dev-precedent + prod-placeholder commands

```bash
# Source: docs/runbook.md lines 430-512, profiles.yml.example (read in full)
cd infra/snowflake/dbt/edgartools_gold

# Dev-precedent (D-03) — requires REAL dev Snowflake credentials (not placeholders;
# dbt 1.11.8 + snowflake adapter 1.11.5 performs a live connection check on compile)
export DBT_SNOWFLAKE_ACCOUNT="<dev-account-locator.region.cloud>"
export DBT_SNOWFLAKE_USER="<dev-user>"
export DBT_SNOWFLAKE_PASSWORD="<dev-password>"
export DBT_SNOWFLAKE_WAREHOUSE="EDGARTOOLS_DEV_REFRESH_WH"
uv run --with dbt-snowflake dbt compile --target dev
uv run --with dbt-snowflake dbt run     --target dev
uv run --with dbt-snowflake dbt test    --target dev

# Prod-target (D-04) — documented as the BLOCKED row's "required fix" command
export DBT_SNOWFLAKE_ACCOUNT="<PROD-account-locator.region.cloud>"
export DBT_SNOWFLAKE_USER="<prod-user>"
export DBT_SNOWFLAKE_PASSWORD="<prod-password>"
export DBT_SNOWFLAKE_ROLE="EDGARTOOLS_PROD_DEPLOYER"
export DBT_SNOWFLAKE_DATABASE="EDGARTOOLS_PROD"
export DBT_SNOWFLAKE_WAREHOUSE="EDGARTOOLS_PROD_REFRESH_WH"
uv run --with dbt-snowflake dbt deps
uv run --with dbt-snowflake dbt run  --target prod
uv run --with dbt-snowflake dbt test --target prod

# Gold status / freshness query (run after prod dbt succeeds — matrix row 9)
snow sql --connection edgartools-prod -q \
  "SELECT * FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS LIMIT 10;"
```

### Anti-Patterns to Avoid

- **Assuming `deploy-snowflake-stack.sh --env prod --run-validation --run-dbt` can be
  run "just for the validation/dbt parts"**: the script `die`s at the `backend.hcl`
  existence check for 3 Terraform roots BEFORE any flag-gated logic runs. There is no
  flag combination that skips the Terraform-apply preamble. Document this as a
  structural blocker, not a flag-tuning problem.
- **Treating `dbt compile --target prod` with placeholder credentials as a viable
  "logic-only" check**: it will fail with a live 404 login error. Don't propose this
  as a Phase 2 deliverable — only `--target dev` with real dev credentials (D-03) is
  runnable, and that itself requires credentials not present in this environment
  (Environment Availability section).
- **Pasting `terraform plan` output, ECR `describe-images` JSON, or dbt compiled SQL
  into evidence files**: per D-15/Phase 1 generated-JSON rule, summarize as
  counts/presence/format only.
- **Defaulting to Pattern 0 (committed versions.tf fix) without an explicit
  authorization checkpoint**: even though the fix is small and low-risk, it is a
  source-tree commit outside `.planning/workstreams/go-live/` that Phase 2's CONTEXT.md
  does not explicitly scope. Per ISO-01, that requires the user to explicitly expand
  Phase 2's scope. Pattern 1 (temporary edit-then-revert, nothing committed) is the
  safe default and produces the same plan-output evidence — use it unless/until the
  user authorizes Pattern 0.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Reading current `:dev` image digest | Custom docker pull + inspect script | `aws ecr describe-images --image-ids imageTag=dev --query 'imageDetails[0].imageDigest'` | Registry API gives the digest without pulling gigabytes of image layers |
| Re-tagging an ECR image | `docker pull` + `docker tag` + `docker push` round trip | `aws ecr batch-get-image` + `aws ecr put-image` | Registry-side copy avoids local Docker/Colima entirely — works from any shell with AWS creds |
| Read-only Terraform plan against real cloud account without real backend | Custom state-stubbing scripts | Terraform's native `override.tf` local-backend override mechanism | Officially supported, automatically cleaned up, zero risk to real state |
| Checking dynamic-table freshness | Custom Snowflake polling script | Existing `EDGARTOOLS_GOLD_STATUS` view (`infra/snowflake/dbt/edgartools_gold/models/gold/edgartools_gold_status.sql`) | Already built, already the canonical verification query in `docs/runbook.md` |

**Key insight:** Every "don't hand-roll" item in this phase is "don't build a new
script — the existing repo scripts/views already do this; only documentation and
evidence capture are missing."

## Common Pitfalls

### Pitfall 1: Prod-side Terraform version-constraint bug blocks `terraform plan`

**What goes wrong:** `terraform init` fails immediately with "Unsupported Terraform
Core version ... This configuration does not support Terraform version 1.15.5" for
ALL FOUR prod-side roots:
- `infra/terraform/accounts/prod/versions.tf`: `required_version = "~> 1.14.7"`
- `infra/terraform/snowflake/accounts/prod/versions.tf`: `"~> 1.14.8"`
- `infra/terraform/access/snowflake/accounts/prod/versions.tf`: `"~> 1.14.8"`
- `infra/terraform/access/aws/accounts/prod/versions.tf`: `"~> 1.14.7"`

**Why it happens:** `~>` is a pessimistic operator — `~> 1.14.7` permits only
`>= 1.14.7, < 1.15.0`. The dev-side equivalents use `>= 1.14.7` (permissive, no upper
bound), which accepts the locally installed `1.15.5`. `git log` shows both dev and
prod `versions.tf` came from the same two commits — this divergence (`>=` in dev vs
`~>` in prod) looks like an unintentional copy-paste inconsistency, not a deliberate
environment pin. No `.terraform-version`/CI pin justifies the prod-side restriction.

**How to avoid:** For the `infra/terraform/accounts/prod/` plan check this phase needs
(D-02), use Pattern 1's temporary edit-then-revert: edit
`required_version = "~> 1.14.7"` → `">= 1.14.7"` (and `"~> 1.14.8"` → `">= 1.14.8"` for
the two Snowflake-side roots if those are also planned), run `terraform
init`/`plan`, then `git checkout -- versions.tf` to revert — `git status --short`
clean afterward, nothing committed. Record the bug itself as a "required fix" note in
`evidence/aws.md` / the matrix row, for a future task/phase to fix permanently.

A permanent, committed fix (Pattern 0) is technically attractive — it's a real,
one-line-per-file bug with no other side effects (the `aws`/`snowflake` provider
version pins, e.g. `= 6.39.0`/`= 2.14.1`, are exact-pins and unaffected) — but it is an
OPTIONAL path requiring explicit user authorization under ISO-01 (see Pattern 0 and
Open Question 3), because it commits a source-tree change outside
`.planning/workstreams/go-live/` that Phase 2's CONTEXT.md does not explicitly scope.
Do not default to committing this fix without that authorization.

**Warning signs:** `terraform init -backend=false` (or with the local-backend
override) fails with "Unsupported Terraform Core version" before reaching any
provider/state logic.

### Pitfall 2: `deploy-snowflake-stack.sh --env prod` dies before touching Snowflake

**What goes wrong:** Someone might plan a task like "run `deploy-snowflake-stack.sh
--env prod --run-validation`" expecting it to do a Snowflake-side dry run. It instead
exits immediately via `die "Missing backend.hcl in ${AWS_ROOT}"` (or the Snowflake
roots) — `infra/terraform/access/aws/accounts/prod/backend.hcl`,
`infra/terraform/snowflake/accounts/prod/backend.hcl`, and
`infra/terraform/access/snowflake/accounts/prod/backend.hcl` only have `.example`
files; none of the 3 are present.

**Why it happens:** The script's main flow is `terraform_init` + `terraform_apply`
across 3 roots FIRST (AWS bootstrap trust → Snowflake storage integration →
Snowflake full apply → Snowflake access apply), with the manifest-task deploy,
`--run-validation`, `--run-dbt`, `--upload-dashboard` all happening AFTER that
preamble. The `backend.hcl` check is the very first action in `main()`.

**How to avoid:** Document this exact failure as the "evidence" for the SNOW-01
matrix row staying BLOCKED — i.e., the BLOCKED status is PROVEN by the script's
own preflight, not by Phase 2 declining to run something. The "required fix" for the
matrix row is: create real `backend.hcl` (3 files, from `.example` + a real
`edgartools-prod-tfstate`-equivalent S3 bucket — which also doesn't exist yet) AND
real `terraform.tfvars` with Snowflake account/org identifiers — both require a
production Snowflake account to exist, which is outside Phase 2 scope.

**Warning signs:** Script exits in <1 second with a `die` message referencing
`backend.hcl` — this is the structural blocker signature, distinct from a credential
or permission error.

### Pitfall 3: ECR cleanup runs automatically and can invalidate just-captured digests

**What goes wrong:** `deploy-aws-application.sh` unconditionally (non-fatally) runs
`cleanup-ecr-images.sh --env <env> --apply` before build/deploy. If an operator
captures `:prod`-tagged image digests, then runs the deploy script, the cleanup step
could delete the `:sha-<hash>` image backing that digest if it falls outside the
"keep 2 newest `:sha-*`" retention window — leaving `--image-ref @sha256:<digest>`
pointing at a now-deleted manifest.

**Why it happens:** `cleanup-ecr-images.sh` retention policy is `:dev` (mutable) +
2 newest `:sha-<hash>` per final-image repo; `:prod`-tagged copies are a 3rd tag on
the SAME digest, but the cleanup script's retention counts are based on `:sha-*` tags
specifically — a `:prod` tag alone may not protect the underlying image from deletion
if its only other tag falls out of the keep-2 window.

**How to avoid:** Document in the runbook: ALWAYS re-resolve `--image-ref`/
`--mdm-image-ref` digests IMMEDIATELY BEFORE the deploy invocation, in the same
session/script run, AFTER any cleanup step has executed — never reuse a digest
captured in an earlier session. This is exactly matrix row 5 ("ECR cleanup deleting
in-flight image digest mitigation") — Phase 2's job is to write this ordering
requirement into the runbook, not to "fix" the cleanup script.

**Warning signs:** `deploy-aws-application.sh --image-ref @sha256:<digest>` fails
with an ECR "image not found" / `ManifestNotFoundException` shortly after a cleanup
step ran with a different digest captured earlier.

### Pitfall 4: `dbt compile` is not purely static — needs live Snowflake credentials

**What goes wrong:** Assuming `dbt compile --target prod` with placeholder/dummy
`DBT_SNOWFLAKE_*` env vars is a safe "logic check" that avoids touching prod. It
fails with `Database Error: 290404 (08001): 404 Not Found: post
<account>.snowflakecomputing.com:443/session/v1/login-request` — dbt-snowflake
1.11.5 opens a real connection during compile (to resolve sources/lineage against
live Snowflake metadata).

**Why it happens:** dbt's `compile` step resolves `{{ source(...) }}` references and
ref graphs against the connected warehouse's information schema in this adapter
version — it is not a pure Jinja-rendering pass.

**How to avoid:** D-03 already anticipates this by using the DEV target with real
dev credentials as the logic-validation proxy. Document clearly that even `dbt
compile --target prod` requires real prod credentials — there is no "lighter" check.
The matrix row 8 ("dbt compile/run/test for production target") required-fix should
say "requires live prod Snowflake credentials for `dbt compile` itself, not just
`run`/`test`."

**Warning signs:** `404 Not Found ... login-request` error during `dbt compile` (not
`dbt run`) is the signature of this issue — distinguishes "credentials missing/wrong"
from "model SQL syntax error" (which would instead show a Jinja/SQL compilation
error referencing a specific model file).

## Code Examples

### Matrix-row-by-row disposition (the 9 BLOCKED rows from `01-LAUNCH-GATE-MATRIX.md`)

| # | Row | Phase 2 Disposition | Evidence/Command |
|---|-----|---------------------|-------------------|
| 1 | AWS passive infrastructure outputs | **Move toward documented-with-plan-proof.** Run Pattern 1 (temporary versions.tf edit + `terraform plan` via `override.tf`, then revert — nothing committed), record resource-add count + output-name list (no values) in `evidence/aws.md`, AND record the `versions.tf` version-constraint bug (Pitfall 1) as a required-fix note. Still not PASS (no real backend/state) but moves from "untested" to "plan validated." If the user has authorized Pattern 0, the committed fix can additionally close out the required-fix note. | `terraform plan` → "Plan: 37 to add, 0 to change, 0 to destroy" + output-name list from `outputs.tf` |
| 2 | Production AWS application manifest (`infra/aws-prod-application.json`) | **Stays BLOCKED.** No live discovery alternative exists (confirmed: no prod ECS cluster, no prod S3 buckets). Required fix unchanged: live discovery or successful prod deploy. | Document `cat`/`jq` summary commands to run once the file exists (same shape as dev: top-level keys, `state_machines` keys, image-ref format) |
| 3 | AWS active application deploy (`deploy-aws-application.sh`) | **Stays BLOCKED**, but document the EXACT command (Pattern 2) including `--enable-mdm`, image-ref placeholders, and the explicit `--edgar-identity-secret-arn` flag per row 4. Required fix: prod passive infra must exist first (depends on row 1's eventual `apply`). | Full command string with placeholders, documented in runbook |
| 4 | Stale `edgar-identity` secret ARN mitigation | **Document runbook requirement**: always pass `--edgar-identity-secret-arn "$(aws secretsmanager describe-secret --secret-id edgartools-prod-edgar-identity --query ARN --output text)"` freshly resolved immediately before deploy, never from a cached/manifest value after any secret recreation. Can be written as a checklist item now (no prod secret exists yet, but the COMMAND PATTERN is documentable). | `aws secretsmanager describe-secret --secret-id edgartools-prod-edgar-identity --query ARN --output text` (will fail today — secret doesn't exist — document as future step) |
| 5 | ECR cleanup deleting in-flight image digest mitigation | **Document runbook ordering requirement** (Pitfall 3) — re-resolve digests after cleanup, immediately before deploy, same session. | `aws ecr describe-images --image-ids imageTag=prod --query 'imageDetails[0].imageDigest'` run AFTER `cleanup-ecr-images.sh --apply` |
| 6 | Snowflake native S3 pull stack (`deploy-snowflake-stack.sh`) | **Stays BLOCKED** — proven by Pitfall 2's structural `backend.hcl` die. Document the exact command + the 3 missing `backend.hcl` files + the `native_pull` module resource list (storage integration, file formats, stage, source tables, pipe, stream, 3 stored procs, 1 task) as the target state. | `deploy-snowflake-stack.sh --env prod --snow-connection edgartools-prod --run-validation --run-dbt` (documented, not run) + resource list from `infra/terraform/snowflake/modules/native_pull/main.tf` |
| 7 | Snowflake deployer direct grants for gold dynamic tables | **Stays BLOCKED** — no prod Snowflake account/connection exists to check grants against. Document the analogous check command (parallel to the resolved `EDGARTOOLS_DEV_DEPLOYER` gap) as the required-fix command. | `SHOW GRANTS TO ROLE EDGARTOOLS_PROD_DEPLOYER;` (documented placeholder query) + reference to `TODOS.md` dev resolution as precedent |
| 8 | dbt compile/run/test for production target | **Stays BLOCKED for prod target**; D-03's DEV-target proxy MAY produce real evidence IF dev Snowflake credentials are supplied at execution time (Environment Availability gap — not resolvable via AWS Secrets Manager in this session). Document both: (a) dev-precedent command (Pattern 4 first block) labeled dev-precedent if run, (b) prod-target placeholder command (Pattern 4 second block) as required fix, noting `dbt compile` itself needs live creds (Pitfall 4). | Pattern 4 commands |
| 9 | `EDGARTOOLS_GOLD_STATUS` and dynamic-table freshness | **Stays BLOCKED** — depends on rows 6+8 (prod) succeeding first. Document the canonical query (from `docs/runbook.md`) and the empty summary-table shape (already present in `evidence/snowflake.md`, "Gold Status And Freshness Summary Shape" section) as the target evidence format. | `SELECT * FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS LIMIT 10;` (documented placeholder; dev-target equivalent COULD be run as a dev-precedent freshness sample if dev credentials are available) |

### `EDGARTOOLS_GOLD_STATUS` view shape (for evidence table headers)

```sql
-- Source: infra/snowflake/dbt/edgartools_gold/models/gold/edgartools_gold_status.sql
-- Columns returned (one row per environment+source_workflow, latest run only):
-- environment, source_workflow, run_id, business_date, status,
-- source_load_status, refresh_status, source_row_count, tables_loaded,
-- last_successful_refresh_at, updated_at
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Manual docker pull/tag/push for ECR re-tagging | Registry-side `aws ecr batch-get-image` + `put-image` | N/A (always available) | Avoids requiring Colima/Docker for image promotion — works from any CI/operator shell with AWS creds |
| Assuming dev `versions.tf` pattern applies uniformly | Prod roots use a stricter (and likely accidental) `~>` constraint | Discovered this session | Must work around (Pattern 1's temporary edit-then-revert, default) or fix permanently (Pattern 0, optional/authorized) before any prod `terraform plan`/`init`/`validate` |

**Deprecated/outdated:** None identified — all scripts/configs examined are current
and actively used for dev.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | D-06's "same ECR repos" means re-tagging `edgartools-dev-warehouse`/`edgartools-dev-mdm` with a `:prod` tag (NOT a separate `edgartools-prod-*` repo, which doesn't exist). | Architecture Patterns Pattern 3, Summary item 3 | If the intended interpretation is a separate prod repo, the entire image-promotion runbook section needs rewriting and would additionally require a Terraform `apply` to create the repo — contradicting D-01/D-02. Surface as Open Question for the planner/user before committing to the runbook. |
| A2 | The `versions.tf` `~>` → `>=` fix is mechanically safe (no other side effects; provider version pins unaffected) — verified empirically this session via a temporary fix + `terraform init`/`plan`, then fully reverted. The DEFAULT path for Phase 2 (Pattern 1) applies this fix temporarily, in-procedure, with no commit. A permanently-committed fix (Pattern 0) is OPTIONAL and requires explicit user authorization per ISO-01, because it is a source-tree commit under `infra/` that Phase 2's CONTEXT.md does not explicitly scope. | Pitfall 1, Pattern 0, Pattern 1 | Low risk overall — Pattern 1 requires no scope decision and was proven end-to-end this session (fix applied, `terraform init`/`plan` succeeded, then `git checkout` reverted cleanly). The only open item is whether the user wants to ALSO authorize Pattern 0 (see Open Question 3) — if they don't, Pattern 1 alone still satisfies D-02. |
| A3 | No dev dbt/Snowflake credential secret exists anywhere accessible to this session (checked AWS Secrets Manager only) — D-03's dev-precedent dbt run cannot proceed without operator-supplied credentials. | Environment Availability, Pitfall 4, matrix row 8 | If credentials ARE available via some other channel (e.g., 1Password, local `~/.snowflake/config.toml` not yet checked for a dev connection), D-03 might be runnable today. Recommend planner add a quick check of `~/.snowflake/connections.toml` / `~/Library/Application Support/snowflake/config.toml` for any `edgartools-dev`-named entry before declaring this fully blocked. |

**If this table is empty:** N/A — see entries above.

## Open Questions

1. **D-06 ECR repo interpretation (A1)**
   - What we know: `edgartools-dev-warehouse` and `edgartools-dev-mdm` exist with
     `:dev` and `:sha-<hash>` tags; `edgartools-prod-warehouse`/`edgartools-prod-mdm`
     do not exist.
   - What's unclear: whether "same ECR repos" in D-06 was written with awareness that
     prod-named repos don't exist (i.e., intentionally meaning "tag the dev repo with
     `:prod`"), or whether the user assumed prod-named repos already existed.
   - Recommendation: Planner should surface this explicitly in the Phase 2 plan's
     first task ("confirm image-promotion target: tag `edgartools-dev-{warehouse,mdm}:prod`
     in place") so the user can confirm/correct before the runbook is written. Given
     D-05 (same-account, prefix-distinguished, no separate ECR), interpretation A1 is
     the only one consistent with D-05+D-01+D-02 together — but it's worth one
     confirming sentence.

2. **Dev Snowflake credential availability for D-03 (A3)**
   - What we know: AWS Secrets Manager has no dbt/Snowflake-deployer credential for
     dev; `snow connection list` has no `edgartools-dev` connection.
   - What's unclear: whether the operator (user) has dev Snowflake credentials
     available locally (e.g., in `~/.snowflake/config.toml`, 1Password, or shell
     history/exports from the `TODOS.md`-documented grants-gap work on 2026-06-13).
   - Recommendation: Planner should add an early task: "operator supplies
     `DBT_SNOWFLAKE_{ACCOUNT,USER,PASSWORD,WAREHOUSE}` for dev as environment
     variables (not committed)" as a `checkpoint:human-verify`-gated prerequisite for
     the D-03 dev-precedent dbt run. If unavailable, the dev-precedent dbt
     run/evidence becomes a documented-but-unexecuted command (same disposition as
     the prod-target command), and matrix row 8 stays fully BLOCKED rather than
     partially evidenced.

3. **Should Pattern 0 (committed versions.tf fix) be authorized as an additional,
   explicitly-scoped task for Phase 2?**
   - What we know: ISO-01 says "Work stays isolated under
     `.planning/workstreams/go-live/` and reviewed launch docs unless a phase
     explicitly scopes source-code or runbook changes." Phase 2's `02-CONTEXT.md`
     phase boundary describes producing a runbook and updating matrix/evidence docs;
     it does not explicitly list "commit a Terraform version-constraint fix under
     `infra/terraform/**/prod/versions.tf`" as in-scope source-code work. The fix
     itself is small, real, and low-risk (one line per file, 4 files, no provisioning
     impact, provider pins unaffected) — verified mechanically this session.
   - What's unclear: whether the user wants to take this opportunity to fix a genuine
     repo bug permanently (Pattern 0) or keep Phase 2 strictly to its documented
     boundary, leaving the bug as a documented "required fix" for whoever next
     provisions these Terraform roots (Pattern 1 alone, no commit).
   - Recommendation: Pattern 1 (temporary edit-then-revert) is sufficient to satisfy
     D-02's read-only `terraform plan` requirement and requires NO authorization —
     treat it as the default plan-of-record. If the planner/user wants Pattern 0 as
     well, add it as an explicitly-authorized, separately-scoped task (e.g., a
     `checkpoint:human-verify` early in the plan: "Authorize committing a 4-file,
     one-line-per-file Terraform version-constraint fix under `infra/terraform/**
     /prod/versions.tf` as part of Phase 2? [yes/no]"). Either answer leaves D-02
     satisfied; only the "is the repo bug fixed for real, with a commit, by the end of
     this phase" outcome differs.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Terraform CLI | `terraform plan` for prod (D-02) | Yes | 1.15.5 | — |
| Prod-side `versions.tf` constraint compatible with 1.15.5 | Same | No (currently `~> 1.14.x`, all 4 prod roots) | — | Pattern 1 (default): temporary in-procedure edit + revert, no commit. Pattern 0 (optional, requires authorization per Open Question 3): commit the fix permanently. |
| `edgartools-prod-tfstate` S3 bucket (real Terraform backend) | Real `terraform apply` for prod (out of scope) | No | — | `override.tf` local-backend technique (Pattern 1) for plan-only |
| AWS profile `aws-admin-prod` / `aws-admin-dev` | All AWS discovery | Yes (both resolve to account `077127448006`, user `cli-access`) | — | — |
| `edgartools-prod-*` S3 buckets, ECS cluster, Secrets Manager secrets | Live discovery for matrix rows 1-2 | No (none exist) | — | None — these require a future prod `terraform apply` + `deploy-aws-application.sh` run, explicitly out of scope (D-01) |
| `edgartools-prod-warehouse`/`edgartools-prod-mdm` ECR repos | D-06 image promotion (if interpreted as separate prod repos) | No | — | Use `edgartools-dev-{warehouse,mdm}` repos with `:prod` tag (Pattern 3 / A1) |
| SnowCLI connection `edgartools-prod` or `edgartools-dev` | `deploy-snowflake-stack.sh` default `--snow-connection`, dbt `--target prod/dev` | No (only 2 unrelated personal connections exist) | — | None for prod (documented placeholder only); for dev (D-03), operator must supply `DBT_SNOWFLAKE_*` env vars directly (A3) |
| `infra/terraform/{access/aws,snowflake,access/snowflake}/accounts/prod/backend.hcl` (3 files) | `deploy-snowflake-stack.sh --env prod` (SNOW-01) | No (only `.example` files) | — | None — script structurally cannot proceed (Pitfall 2); documented command only |
| `uv` + `dbt-snowflake` | All dbt commands | Yes (used successfully this session up to the live-connection step) | dbt 1.11.8 / adapter 1.11.5 | — |
| `snow` CLI | Gold status query, manifest task deploy | Not checked directly this session, but `snow connection list` ran successfully implying `snow` CLI is installed | — | — |

**Missing dependencies with no fallback:**
- Real prod AWS passive infrastructure (S3 buckets, ECS cluster, Secrets Manager
  secrets, ECR repos if A1 resolves to "separate repos") — requires a future prod
  `terraform apply`, explicitly deferred (D-01/D-02).
- Real prod Snowflake account/connection/credentials and the 3 prod `backend.hcl`
  files — requires Snowflake-side provisioning, explicitly deferred.
- `edgartools-prod-tfstate` S3 bucket for a real Terraform backend.

**Missing dependencies with fallback:**
- `versions.tf` constraint (Pitfall 1) — Pattern 1 (default): temporary
  edit-then-revert within the read-only plan procedure, no commit required. Pattern 0
  (optional, pending Open Question 3 authorization): commit the fix permanently as its
  own task.
- Real Terraform backend for plan-only purposes — `override.tf` local-backend
  technique (Pattern 1).
- Dev Snowflake credentials for D-03 — operator-supplied env vars at execution time
  (checkpoint:human-verify), or document-only if unavailable.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | None applicable — this phase produces documentation/runbooks and evidence-file updates, not application code. No pytest/jest suite covers `infra/scripts/*.sh` or Terraform roots. |
| Config file | none |
| Quick run command | `terraform plan` via Pattern 1 (temporary versions.tf edit + `override.tf`, reverted) — the one executable check in this phase |
| Full suite command | n/a |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LIVE-02 | `deploy-aws-application.sh --env prod ...` documented correctly (flags, resolution order, manifest shape) | manual-only (documentation review) | n/a — verified by reading script source and cross-checking against dev manifest shape | n/a |
| SNOW-01 | `deploy-snowflake-stack.sh --env prod` behavior documented (structural blocker proven) | smoke (run the command, expect `die` at backend.hcl) | `bash infra/scripts/deploy-snowflake-stack.sh --env prod --snow-connection edgartools-prod --run-validation 2>&1 \| head -5` — exits non-zero with `backend.hcl` message | n/a (proven this session, not committed as a test) |
| SNOW-02 | dbt prod-target command documented; dev-precedent command documented | manual-only / dev-precedent smoke if credentials available | `uv run --with dbt-snowflake dbt compile --target dev` (requires real dev creds, A3) | n/a |
| (infra) | `terraform plan` succeeds for `accounts/prod` via Pattern 1's temporary versions.tf edit + `override.tf`, with the edit reverted afterward (`git status --short` clean) | smoke | `terraform init -input=false && terraform plan -input=false -no-color` for `accounts/prod` (with temporary versions.tf edit + `override.tf`, Pattern 1); revert via `git checkout -- versions.tf` and `rm -rf override.tf .terraform*` | n/a |

### Sampling Rate
- **Per task commit:** No commits are expected in the default path (Pattern 1 is
  reverted in-procedure). If Pattern 0 is authorized (Open Question 3), run
  `terraform validate` (`-backend=false` or `override.tf`) in each of the 4 fixed
  roots as part of that task's verification.
- **Per wave merge:** Re-run Pattern 1's `terraform plan` for `accounts/prod` to
  confirm the documented resource count is still accurate.
- **Phase gate:** Manual review of updated `01-LAUNCH-GATE-MATRIX.md` rows + evidence
  files for secret-safety (no DSNs/ARNs/tokens) before `/gsd:verify-work`.

### Wave 0 Gaps
- None — no test framework exists for this domain and none is being introduced. The
  "tests" here are the documented bash commands themselves, executed once during
  Phase 2 for the rows that can run (Pattern 1 + row 1), and recorded as evidence.

*(If no gaps: "None — existing test infrastructure covers all phase requirements" —
more precisely here: no test infrastructure exists or is needed; verification is
evidence-file capture of command output.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No auth surfaces added |
| V3 Session Management | No | N/A |
| V4 Access Control | Yes (indirectly) | Snowflake role/grant checks (`EDGARTOOLS_PROD_DEPLOYER` direct-grant verification, matrix row 7) — document the check command, do not modify grants in this phase |
| V5 Input Validation | No | N/A — no user-facing input surfaces |
| V6 Cryptography | No | N/A — no new crypto; existing Secrets Manager / Snowflake keypair auth unchanged |
| V7 Error Handling/Logging | Yes | Evidence files must NOT contain raw connector errors, stack traces, or full ECR/Terraform JSON (carried forward from Phase 1 D-13/D-15) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret leakage via evidence/runbook files (DSNs, ARNs, passwords pasted from command output) | Information Disclosure | Generated-JSON/output summarization rule (D-15): record presence/counts/format only, never raw values. Apply to `terraform plan` output, `aws secretsmanager` ARNs, dbt compiled SQL. |
| Stale image digest reference after ECR cleanup (Pitfall 3) leading to deploy using an unintended/missing image | Tampering / Denial of Service | Always re-resolve digests immediately before deploy, in the same session, after cleanup runs (documented runbook ordering) |
| Privilege escalation via dynamic-table owner-role grants (the `EDGARTOOLS_DEV_DEPLOYER`/`EDGARTOOLS_PROD_DEPLOYER` direct-SELECT pattern) | Elevation of Privilege (inverse — currently a functionality blocker, but the underlying grant model is security-relevant) | Document the exact `SHOW GRANTS TO ROLE EDGARTOOLS_PROD_DEPLOYER` check as matrix row 7's required fix; do not grant broader-than-necessary roles when this is eventually executed (Phase 3+/operator action) |
| Unscoped source-tree commits during a "document-and-validate only" phase (Pattern 0 vs Pattern 1) | Tampering (process-integrity sense — out-of-scope changes landing without authorization) | ISO-01: any committed change outside `.planning/workstreams/go-live/` requires the phase to explicitly scope it. Default to Pattern 1 (no commit); gate Pattern 0 behind an explicit `checkpoint:human-verify` authorization. |

## Sources

### Primary (HIGH confidence)
- `infra/terraform/accounts/prod/{main.tf,variables.tf,providers.tf,outputs.tf,versions.tf,terraform.tfvars.example,backend.hcl.example}` — read in full this session
- `infra/terraform/accounts/dev/versions.tf` — read for comparison (`>= 1.14.7` vs prod's `~> 1.14.7`)
- `infra/terraform/snowflake/accounts/prod/{main.tf,versions.tf}` — read in full
- `infra/terraform/snowflake/modules/native_pull/main.tf` — grepped for resource inventory
- `infra/terraform/access/{aws,snowflake}/accounts/prod/versions.tf` — read for version-constraint confirmation
- `infra/scripts/deploy-aws-application.sh` — read lines 1-1375, 2095-2239 (full flag/resolution-order/manifest-shape analysis)
- `infra/scripts/deploy-snowflake-stack.sh` — read in full (444 lines)
- `infra/scripts/cleanup-ecr-images.sh` — read first 40 lines (retention policy)
- `infra/snowflake/dbt/edgartools_gold/profiles.yml.example` — read in full
- `infra/snowflake/dbt/edgartools_gold/models/gold/edgartools_gold_status.sql` — read in full
- `docs/runbook.md` lines 430-512 — canonical prod dbt commands
- `infra/terraform/modules/warehouse_runtime/{main.tf,outputs.tf}` — grepped for MDM secret name patterns
- Live commands this session: `aws sts get-caller-identity` (both profiles), `aws ecr describe-repositories`/`describe-images`, `aws s3 ls`, `aws ecs list-clusters`/`describe-clusters`, `aws secretsmanager list-secrets`, `snow connection list`, `terraform init`/`plan` (with temporary fix + override.tf, fully reverted)
- `.planning/workstreams/go-live/phases/01-.../01-LAUNCH-GATE-MATRIX.md`, `evidence/{aws,snowflake}.md`, `01-CONTEXT.md`, `02-CONTEXT.md`, `REQUIREMENTS.md`, `STATE.md` — all read in full

### Secondary (MEDIUM confidence)
- `TODOS.md` (grepped, not read in full) — `EDGARTOOLS_DEV_DEPLOYER` grants-gap precedent

### Tertiary (LOW confidence)
- None — no WebSearch/Context7 lookups performed; this phase's domain is entirely
  internal repo scripts/configs, all verified directly via Read/Bash this session.

## Metadata

**Confidence breakdown:**
- Standard stack: N/A — no new packages
- Architecture: HIGH — all scripts/Terraform/dbt configs read in full and
  cross-checked against live AWS/Snowflake discovery this session
- Pitfalls: HIGH — all 4 pitfalls were empirically reproduced (version-constraint
  failure, backend.hcl die, ECR repo non-existence, dbt compile live-connection
  error) and the version-constraint fix was tested end-to-end then reverted

**Research date:** 2026-06-14
**Valid until:** 14 days — AWS/Snowflake resource existence (ECR repos, S3 buckets,
secrets, prod Terraform state) can change quickly if other workstreams/operators act;
re-verify live-discovery findings (Environment Availability table) immediately before
Phase 2 execution if more than a few days have passed.
