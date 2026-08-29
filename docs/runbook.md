# EdgarTools Platform — End-to-End Setup Runbook

This guide walks from zero to the AWS/Snowflake gold layer.

## Quick Path — install.sh (recommended)

`infra/scripts/install.sh` (renamed from `go-live.sh`; wayfinder
snowflake-account-cutover map, Ticket 05) is the maintained, stage-driven
wizard that runs everything below in the correct order, with preview-first
safety and per-stage confirmation. Prefer this over the manual walkthrough
further down — the manual section exists for troubleshooting a specific
stage, not as the primary path, and can silently drift from what the
script actually does (this repo has been bitten by that kind of drift more
than once; see CLAUDE.md's manifest-pipeline and bootstrap-SQL 5-whys
sections).

```bash
# Read-only environment checks (AWS CLI, SnowCLI, Terraform, Docker, config)
bash infra/scripts/install.sh doctor --env-name prod --snow-connection edgartools-prod \
  --aws-account-id <12-digit-account-id>

# Print the ordered stage plan and exact commands, preview-only -- nothing runs
bash infra/scripts/install.sh plan --env-name prod --snow-connection edgartools-prod \
  --aws-account-id <12-digit-account-id>

# Interactive TUI wizard (default command) -- prompts for environment/connection,
# then walks every stage with a yes/no confirmation before each real command
bash infra/scripts/install.sh

# Non-interactive: preview only, or add --apply to enable per-stage confirmation and execution
bash infra/scripts/install.sh deploy --env-name prod --snow-connection edgartools-prod \
  --aws-account-id <12-digit-account-id> [--apply]

# Write a sanitized report of what ran (or would run)
bash infra/scripts/install.sh report --env-name prod --snow-connection edgartools-prod \
  --aws-account-id <12-digit-account-id>
```

The stage sequence (18 stages as of the snowflake-account-cutover map):
AWS Terraform state bucket → Neo4j Native App install → AWS passive
infrastructure → AWS access roles/policies → ECR image publish → ECS task
definitions/Step Functions → Snowflake native-pull foundation → an
unscoped `seed-universe` run → Snowflake MDM export targets → dbt gold →
Snowflake loader role ownership → Streamlit dashboard → Snowflake Postgres
/ graph prerequisites → `bronze_seed_silver_gold` → standalone gold-refresh
(with an automated `gold-verify-live` row-count gate) → MDM+graph
connectivity/sync/verification → AWS MDM E2E checks → a bounded data
smoke test. Run `bash infra/scripts/install.sh plan --env-name <slug>
--snow-connection <name> --aws-account-id <id>` against your target
environment for the exact, current commands — the list above is a
summary, not a substitute for the live plan output.

`--env-name` is a free-form operator-chosen slug (e.g. `prod`, `eu-prod`),
not a closed `dev`/`prod` enum, and `--snow-connection` is always required
explicitly (never derived from `--env-name` — see CLAUDE.md's "SnowCLI
connection naming" note for why).

## Architecture Overview

```
SEC EDGAR API → edgar-warehouse Python CLI → AWS S3 (Parquet, bronze)
  → Snowflake storage integration (EDGARTOOLS_SOURCE)
  → dbt run → EDGARTOOLS_GOLD dynamic tables (9 tables + 1 status view)
  → Streamlit dashboard
```

Layers:
- **Source**: SEC EDGAR API (live pull by the warehouse CLI)
- **Bronze**: AWS S3 Parquet exports written by `edgar-warehouse`
- **Silver** (internal): DuckDB intermediate processing inside the warehouse container
- **Gold**: Snowflake `EDGARTOOLS_GOLD` dynamic tables managed by dbt

---

## Prerequisites

### Accounts

| Account | Notes |
|---------|-------|
| AWS (admin access) | ECS, ECR, S3, CodeBuild, Secrets Manager |
| Snowflake (Enterprise+) | Dynamic tables require Enterprise edition or higher |
| GitHub (read/write) | Source repository access |

### CLI Tools

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12+ | python.org or `pyenv install 3.12` |
| pip / uv | latest | bundled or `pip install uv` |
| git | any | pre-installed |
| GitHub CLI (`gh`) | >= 2.0 | `winget install GitHub.cli` |
| Docker Desktop | >= 24 | docker.com |
| AWS CLI | v2 | aws.amazon.com/cli |
| Terraform | **1.14.8 or later in the 1.14.x line** | terraform.io |
| SnowCLI (`snow`) | latest | `pip install snowflake-cli-labs` |
| Bash | any | native on Linux/Mac; WSL on Windows |
| dbt-snowflake | >= 1.7 | `pip install dbt-snowflake` |

### Clone the Repository

```bash
git clone https://github.com/paulananth/edgartools-platform
cd edgartools-platform
pip install -e ".[s3,snowflake]"
pip install dbt-snowflake
```

### Environment Variables

Set these before running any steps. The exact names are used by scripts and dbt.

| Variable | Used By | How to Get |
|----------|---------|------------|
| `AWS_PROFILE` or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Terraform, CLI, ECR | Use an admin profile for Terraform; use `sec_platform_deployer` for application rollout and executions |
| `SNOWFLAKE_ACCOUNT` | Scripts, dbt | Snowflake admin — format: `ORGNAME-ACCOUNTNAME` |
| `SNOWFLAKE_USER` | Scripts, dbt | Snowflake admin |
| `SNOWFLAKE_PASSWORD` | Scripts, dbt | Snowflake admin |
| `TF_VAR_snowflake_organization_name` | Snowflake Terraform provider | From Snowflake creds |
| `TF_VAR_snowflake_account_name` | Snowflake Terraform provider | From Snowflake creds |
| `TF_VAR_snowflake_user` | Snowflake Terraform provider | From Snowflake creds |
| `EDGAR_IDENTITY` | Warehouse runtime | `"Your Name your@email.com"` |
| `SERVING_EXPORT_ROOT` | Warehouse runtime | Export root for Snowflake serving Parquet |

---

## Credential Strategy

AWS uses a split-principal model:

- **AWS admin profile**: Applies `bootstrap-state`, AWS provisioning Terraform,
  and AWS access Terraform in the target account.
- **`sec_platform_deployer`**: Deploys the warehouse image, ECS task
  definitions, Step Functions state machines, and starts executions. Prefer IAM
  Identity Center or a CI OIDC role with this name. Use
  `infra/scripts/create-deployer.sh` only as an IAM user fallback; store any
  access key in a secret manager or CI secret store, rotate it regularly, and do
  not use it for Terraform admin applies.
- **`sec_platform_runner`**: Runtime is a family of service-assumed roles, not
  an IAM user. The concrete roles are `sec_platform_runner_execution` for ECS
  image pulls/logging/secret reads, `sec_platform_runner_task` for application
  task permissions, and `sec_platform_runner_step_functions` for Step Functions
  service execution. These roles have no long-lived access keys.

- **EDGAR identity**: Store the SEC User-Agent contact string in AWS Secrets Manager
  secret `edgartools-<env>-edgar-identity`. The runtime receives it as `EDGAR_IDENTITY`.
  Use an app/operator name and monitored email, for example
  `EdgarTools Platform data-ops@example.com`.
- **MDM secrets**: Operators store `MDM_DATABASE_URL`, `MDM_API_KEYS`, and Snowflake
  graph-sync settings under `edgartools-<env>/mdm/*` with
  `infra/scripts/bootstrap-aws-mdm-secrets.sh`.

### Select and verify the admin profile

Dev and prod currently share canonical AWS account `690839588395`; their resources and Terraform state keys are environment-scoped. Account `077127448006` is retired. Profile names are not proof of account identity, so verify the selected profile before every Terraform operation:

```bash
# Choose exactly one:
export AWS_PROFILE=aws-admin-dev   # infra/terraform/**/dev roots
# export AWS_PROFILE=aws-admin-prod  # infra/terraform/**/prod roots

export AWS_DEFAULT_REGION=us-east-1
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
test "$ACCOUNT_ID" = "690839588395" || {
  echo "Refusing AWS operation: $AWS_PROFILE resolved to $ACCOUNT_ID" >&2
  exit 1
}
```

Use the same verified profile for the environment's state bootstrap, passive-infrastructure root, and AWS-access root. See [AWS account and profile selection](aws-authentication.md) for SSO configuration, dev/prod examples, troubleshooting, and the mandatory retired-account guard.

---

## Manual / Under the Hood

Everything from here down is the same procedure `install.sh` runs for you,
broken out stage by stage as raw commands. Reach for this section when a
specific `install.sh` stage fails and you need to run its underlying
commands by hand to diagnose or retry it — not as the primary path for a
new environment.

## Step 1 — Terraform: Bootstrap State Bucket

The state bucket must exist before any other Terraform root can initialise its backend.
Run this with an AWS admin profile in the target account.

```bash
# Dev:  export AWS_PROFILE=aws-admin-dev; set environment = "dev"
# Prod: export AWS_PROFILE=aws-admin-prod; set environment = "prod"
cd infra/terraform/bootstrap-state
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set environment ("dev" or "prod") and aws_region
terraform init
terraform apply
```

Note the bucket name printed in the output (e.g. `edgartools-prod-tfstate-690839588395`). You will use
this in every subsequent backend configuration.

---

## Step 2 — Terraform: AWS Infrastructure

Apply the AWS account root. This creates passive infrastructure: ECR, the ECS
cluster and logs, S3 buckets, SNS topic, and empty Secrets Manager containers.
It does not create IAM roles, task definitions, schedules, or workflow engines.
Use the same AWS admin profile that created the state bucket.

```bash
export AWS_PROFILE=aws-admin-prod
cd infra/terraform/accounts/prod

# Configure the remote state backend
cp backend.hcl.example backend.hcl
# Edit backend.hcl — set bucket to the name from Step 1
# Default contents:
#   bucket  = "edgartools-prod-tfstate-690839588395"
#   key     = "accounts/prod/terraform.tfstate"
#   region  = "us-east-1"
#   encrypt = true

terraform init -backend-config=backend.hcl

# Configure inputs
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars for account-specific storage, Snowflake export, and tags.
```

Apply the passive AWS infrastructure:

```bash
terraform apply
```

> **Note**: `accounts/prod` has `prevent_destroy = true` on the bronze bucket.
> `terraform destroy` will fail unless you remove that guard manually.

After apply, record the following provisioning outputs — you will need them in
later steps:

```bash
terraform output ecr_repository_url                # used in Step 3
terraform output cluster_arn                       # used in Step 3
terraform output public_subnet_ids                 # used in Step 3
terraform output public_ecs_security_group_id      # used in Step 3
terraform output snowflake_manifest_sns_topic_arn  # used in Step 4
terraform output snowflake_export_root_url          # used in Step 4
```

### Apply AWS Access Control

Apply the separate AWS access root after the provisioning root. This creates the
runtime service roles, S3/KMS/Secrets Manager policies, and Snowflake export
trust policy. It does not create a runner IAM user.

```bash
cd infra/terraform/access/aws/accounts/prod
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars so provisioning_state_bucket matches Step 1.

terraform init -backend-config=backend.hcl
terraform apply

terraform output runner_execution_role_arn
terraform output runner_task_role_arn
terraform output runner_step_functions_role_arn
terraform output snowflake_storage_role_arn
```

The runner roles are named `sec_platform_runner_execution`,
`sec_platform_runner_task`, and `sec_platform_runner_step_functions`. ECS tasks
assume the first two through `ecs-tasks.amazonaws.com`; Step Functions assumes
the third through `states.amazonaws.com`.

### Populate Secrets

Terraform creates the EDGAR identity as an empty Secrets Manager container.
Populate it before running any warehouse workload:

```bash
# EDGAR identity (used by the warehouse CLI as the SEC User-Agent header)
aws secretsmanager put-secret-value \
  --secret-id edgartools-prod-edgar-identity \
  --secret-string "Your Name your@email.com"
```

The `edgartools-prod-runner-credentials` secret is a legacy empty container for
backward-compatible operator storage only. Do not create runner access keys for
normal runtime or deployment; runtime uses the `sec_platform_runner_*` service
roles, and deployment uses `sec_platform_deployer`.

---

## Step 2a — Configure the AWS Application Deployer

Create or map an operator principal named `sec_platform_deployer` after the AWS
access root exists. Prefer IAM Identity Center for humans or a CI OIDC role for
automation. The deployer needs application rollout permissions and scoped
`iam:PassRole` only:

- Pass `sec_platform_runner_execution` and `sec_platform_runner_task` only to
  `ecs-tasks.amazonaws.com`.
- Pass `sec_platform_runner_step_functions` only to `states.amazonaws.com`.
- Push to the environment ECR repository, register ECS task definitions, create
  or update `edgartools-<env>-*` Step Functions state machines, read the
  Terraform state outputs, and start/inspect/stop executions.

If a long-lived IAM user is unavoidable, use the fallback helper with admin
credentials, then store the printed key in a secret manager or CI secret store
and rotate it regularly:

```bash
export AWS_PROFILE=aws-admin-prod
bash infra/scripts/create-deployer.sh prod us-east-1
```

The helper creates `sec_platform_deployer`; the older
`edgartools-<env>-deployer` naming is legacy.

---

## Step 2b — Reuse Dev Bronze SEC Artifacts For Prod

After the prod bronze bucket exists, seed it from the existing dev bronze
bucket before the first production bootstrap/capture run. Bronze SEC filing
artifacts are additive and immutable after capture, so this avoids re-fetching
the same historical SEC data from EDGAR. Copy only the bronze source tree; do
not copy dev warehouse, silver, or gold outputs into prod.

Use an operator profile that can read the dev bronze bucket and write the prod
bronze bucket:

```bash
export AWS_PROFILE=aws-admin-prod
REPO_ROOT="$(git rev-parse --show-toplevel)"
export AWS_REGION=us-east-1
export DEV_BRONZE_ROOT="s3://edgartools-dev-bronze/warehouse/bronze/"

PROD_BRONZE_BUCKET="$(terraform -chdir="${REPO_ROOT}/infra/terraform/accounts/prod" output -raw bronze_bucket_name)"
export PROD_BRONZE_ROOT="s3://${PROD_BRONZE_BUCKET}/warehouse/bronze/"

# Preview first. Keep only counts/size in evidence, not a full object listing.
aws s3 sync "$DEV_BRONZE_ROOT" "$PROD_BRONZE_ROOT" \
  --source-region "$AWS_REGION" \
  --region "$AWS_REGION" \
  --size-only \
  --dryrun

# Copy immutable bronze artifacts. Do not add --delete.
aws s3 sync "$DEV_BRONZE_ROOT" "$PROD_BRONZE_ROOT" \
  --source-region "$AWS_REGION" \
  --region "$AWS_REGION" \
  --size-only \
  --only-show-errors

aws s3api list-objects-v2 \
  --bucket "$PROD_BRONZE_BUCKET" \
  --prefix "warehouse/bronze/" \
  --query '{object_count: length(Contents[]), total_bytes: sum(Contents[].Size)}' \
  --output json
```

After this copy, run normal production warehouse commands without `--force`.
The loaders should keep their default idempotent behavior and skip already
captured SEC files; use `--force` only for explicit operator repair. Daily or
bounded production capture still runs afterward to pick up filings that were
not present in the dev bronze snapshot at copy time.

---

## Step 3 — Deploy AWS Application Components

The ECR repository, ECS cluster, access roles, subnets, log group, and empty secret
container now exist. Deploy the active application layer outside Terraform:
build/push the image, register ECS task definitions, and create or update Step
Functions state machines.

### Linux / CI (preferred)

```bash
bash infra/scripts/deploy-aws-application.sh \
  --env prod \
  --aws-profile sec_platform_deployer \
  --aws-account-id 690839588395 \
  --aws-region us-east-1 \
  --build-image \
  --publish-mode linux \
  --output-file infra/aws-prod-application.json
```

### Windows (Git Bash + WSL)

```bash
IMAGE_REF_FILE=infra/aws-prod-image.txt
bash infra/scripts/publish-warehouse-image-via-wsl.sh \
  --aws-profile sec_platform_deployer \
  --aws-region us-east-1 \
  --ecr-repository edgartools-prod-images \
  --image-tag "$(git rev-parse HEAD)" \
  --output-file "$IMAGE_REF_FILE"

bash infra/scripts/deploy-aws-application.sh \
  --env prod \
  --aws-profile sec_platform_deployer \
  --aws-account-id 690839588395 \
  --aws-region us-east-1 \
  --skip-build \
  --image-ref "$(cat "$IMAGE_REF_FILE")" \
  --output-file infra/aws-prod-application.json
```

The deployment script prints a JSON summary with the image digest, ECS task
definition ARNs, and Step Functions state machine ARNs. It does not create
EventBridge schedules; schedule activation remains an explicit operator action.

The image reference in the summary is a verified `@digest` reference, for example:

```
123456789012.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-images@sha256:abc123... (tagged warehouse-sha-<...>)
```

### macOS / Colima — publish once, then deploy once

For a source revision that has not yet been published, build and push exactly
one immutable `sha-<git-sha>` image. Save the resulting digest reference, then
deploy that exact reference with `--skip-build`. Do **not** rerun either command
because a terminal wrapper returned before the deployment script has finished:
first inspect the existing deploy process and the active ECS task-definition
images. A second publish is needed only for a new source revision; a second
deployment is needed only when all three task definitions still reference a
different digest after the original process has stopped.

Budget roughly **three minutes** for the deploy script's ECR retention audit,
task-definition registration, and Step Functions update. After starting it,
wait the full three minutes before the first status check. If it is still
running, wait five-minute intervals between subsequent checks; never poll in a
tight loop. Once it has stopped, perform one authoritative verification of the
three ECS task-definition images and the output summary before deciding whether
the rollout needs investigation or a single justified retry.

```bash
colima status
test "$(docker context show)" = colima

IMAGE_TAG="sha-$(git rev-parse --short=12 HEAD)"
IMAGE_REF_FILE="/tmp/edgartools-prod-warehouse-${IMAGE_TAG}.txt"

AWS_PROFILE=sec_platform_deployer \
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-prod-images \
  --role warehouse \
  --image-tag "$IMAGE_TAG" \
  --mode docker \
  --cache-from-tag dev \
  --output-file "$IMAGE_REF_FILE"

IMAGE_REF="$(< "$IMAGE_REF_FILE")"
AWS_PROFILE=sec_platform_deployer \
bash infra/scripts/deploy-aws-application.sh \
  --env prod \
  --aws-profile sec_platform_deployer \
  --aws-account-id 690839588395 \
  --aws-region us-east-1 \
  --skip-build \
  --image-ref "$IMAGE_REF" \
  --output-file /tmp/edgartools-prod-application.json

# Authoritative rollout verification: each size must match $IMAGE_REF.
for size in small medium large; do
  task_definition="$(aws --profile sec_platform_deployer --region us-east-1 \
    ecs list-task-definitions --family-prefix "edgartools-prod-${size}" \
    --status ACTIVE --sort DESC --max-results 1 \
    --query 'taskDefinitionArns[0]' --output text)"
  aws --profile sec_platform_deployer --region us-east-1 \
    ecs describe-task-definition --task-definition "$task_definition" \
    --query 'taskDefinition.containerDefinitions[0].image' --output text
done
```

Do not copy this image reference into Terraform. Image rollout, workflow
deployment, and workload execution are explicit operator actions outside the AWS
infrastructure root.

### Audit and retire stale ECS task-definition revisions

The durable rollback registry is the release manifest for task-definition
cleanup. Each verified cohort records the immutable warehouse and MDM image
digests, immutable source tags, exact task-definition ARNs, verification
evidence, and verification time. Do not infer a release from revision age,
revision ranges, image equality, or a `latest-N` rule.

After a deploy has completed its full verification contract, advance the
registry with `record-cohort`. Until the registry contains the current release
and two verified rollback cohorts, every cleanup remains fail-closed and retains
all tagged runtime images. `deploy-aws-application.sh`, `record-cohort`, and
`apply` coordinate through the same durable S3 lock. A deploy holds it from
before task-definition registration through the final state-machine update, so
its temporarily unreferenced candidate ARNs cannot be retired concurrently. A
crashed operation leaves the lock in place deliberately. Normal owners release
it with the token returned by `acquire-lock`; confirm that no deploy, cohort
update, or cleanup remains active before using `release-lock --force` for stale
lock recovery.

`record-cohort` verifies the live AWS account and both immutable source tags
before changing release state. It publishes every movable rollback mirror tag
first and commits the ETag-guarded authoritative registry last. A partial mirror
failure therefore leaves the prior registry authoritative and cleanup blocked;
rerun the same command after correcting the ECR failure rather than editing the
registry manually.

Image publication may happen before deployment (including through the
standalone publisher), so the current cohort's `verified_at` is also the release
candidate watermark: any immutable runtime image pushed after it is retained
until a later verified cohort advances the watermark. This closes the
publish-to-deploy window without guessing from image age.

Run the read-only drift gate before relying on the deployment. It recursively
checks every `edgartools-prod-*` Step Functions definition, requires each
referenced task-definition ARN to be active and part of the registry's current
release cohort, verifies that each current task definition resolves to its
recorded role digest, and reconciles live ECS tasks, rollback mirror tags, each
cohort's recorded immutable source tag, and its exact repository.
Task enumeration scans every ECS cluster in the account, queries both `RUNNING`
and `STOPPED` desired states, retains every platform task whose actual state is
still transitional, and fails closed on any `DescribeTasks` response-level
failure. The deployment script does not run the legacy ECR cleanup script;
deletion requires an explicit reviewed `ecr_rollback_cli plan`/`apply` cycle.

```bash
AWS_PROFILE=sec_platform_deployer \
uv run python -m edgar_warehouse.scripts.ecr_rollback_cli \
  --region us-east-1 \
  --account-id 690839588395 \
  --repository edgartools-prod-images \
  --name-prefix edgartools-prod \
  --registry-bucket edgartools-prod-warehouse-690839588395 \
  check \
  --output-file /tmp/edgartools-prod-task-definition-check.json
```

`check` never changes AWS. It exits nonzero on reference drift, unresolved or
dynamic task-definition references, incomplete rollback evidence, identity
mismatch, or any other fail-closed condition. Inspect `reference_drift`,
`fail_closed_reasons`, and the exact `stale_task_definition_arns`; the historical
458-candidate count is only a counting check.

For retirement, generate a reviewed plan first, then pass its exact hash to
`apply`:

```bash
AWS_PROFILE=sec_platform_deployer \
uv run python -m edgar_warehouse.scripts.ecr_rollback_cli \
  --region us-east-1 \
  --account-id 690839588395 \
  --repository edgartools-prod-images \
  --name-prefix edgartools-prod \
  --registry-bucket edgartools-prod-warehouse-690839588395 \
  plan \
  --output-file /tmp/edgartools-prod-ecr-retirement-plan.json

# Destructive: use only after reviewing the exact ARNs and digests above.
AWS_PROFILE=sec_platform_deployer \
uv run python -m edgar_warehouse.scripts.ecr_rollback_cli \
  --region us-east-1 \
  --account-id 690839588395 \
  --repository edgartools-prod-images \
  --name-prefix edgartools-prod \
  --registry-bucket edgartools-prod-warehouse-690839588395 \
  apply \
  --plan-hash '<plan_sha256>' \
  --operator '<operator-id>'
```

`apply` acquires the durable cleanup lock, reloads the registry, and repeats the
full audit before changing anything. It deregisters only the reviewed exact
ARNs in bounded batches of 100, verifies each is `INACTIVE`, and repeats the
full read-only reconciliation after every batch. It deletes only digests that
remain eligible in both the reviewed and repeated plans. Any changed or
unresolved reference aborts before image deletion. Use
`--task-definition-batch-size` to choose a smaller reviewed batch when needed.

### Bounded ECS warehouse tasks

Use the standard launcher for CIK-scoped operational work instead of composing
an `aws ecs run-task` command manually. It verifies the selected AWS account,
uses the active task-definition revision, discovers the only container name and
the environment's Fargate network configuration, and permits only bounded
warehouse task profiles. It does not expose `--force`.

```bash
# Print the exact resolved command without starting a task.
bash scripts/ops/run-ecs-task.sh artifact-registration \
  --env prod \
  --aws-profile sec_platform_deployer \
  --aws-account-id 690839588395 \
  --cik-list 320193 \
  --artifact-policy all_attachments \
  --dry-run

# Launch and wait for the bounded Branch A registration pass.
bash scripts/ops/run-ecs-task.sh artifact-registration \
  --env prod \
  --aws-profile sec_platform_deployer \
  --aws-account-id 690839588395 \
  --cik-list 320193 \
  --artifact-policy all_attachments \
  --wait

# Run Branch B only after Branch A published successfully.
bash scripts/ops/run-ecs-task.sh per-filing \
  --env prod \
  --aws-profile sec_platform_deployer \
  --aws-account-id 690839588395 \
  --cik-list 320193 \
  --wait
```

---

## Step 4 — Prepare the Snowflake Terraform Root

Prepare the Snowflake provisioning and access roots so the wrapper in Step 5 can
initialize them and apply database objects plus grants.

```bash
cd infra/terraform/snowflake/accounts/prod

cp backend.hcl.example backend.hcl
# Edit backend.hcl — set bucket to the name from Step 1
# Default contents:
#   bucket = "edgartools-prod-tfstate-690839588395"
#   key    = "snowflake/prod/terraform.tfstate"
#   region = "us-east-1"

terraform init -backend-config=backend.hcl

cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars:
#   snowflake_organization_name = "YOURORG"
#   snowflake_account_name      = "YOURACCOUNT"
#   snowflake_user              = "your_admin_user"
#   snowflake_authenticator     = "externalbrowser"  # or "snowflake_jwt"
#   snowflake_admin_role        = "ACCOUNTADMIN"

```

If you use the wrapper in Step 5, you do not need to run a separate manual `terraform apply`
in this root.

Also prepare the Snowflake access root:

```bash
cd infra/terraform/access/snowflake/accounts/prod

cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars so provisioning_state_bucket matches Step 1 and
# Snowflake provider credentials match the provisioning root.

terraform init -backend-config=backend.hcl
```

---

## Step 5 — Deploy Snowflake, dbt, and Dashboard

Use the wrapper script to coordinate the AWS and Snowflake Terraform states and
reconcile the Snowflake IAM trust automatically. Validation, dbt, and dashboard
upload run only when their flags are passed.

```bash
# Run from the repo root
bash infra/scripts/deploy-snowflake-stack.sh \
  --env-name prod \
  --snow-connection edgartools-prod
```

The wrapper performs these stages in order:

1. AWS access Terraform bootstrap apply with temporary trust and deterministic external ID.
2. Snowflake Terraform apply for the storage integration, stage, source tables, pipe, stream, procedures, and task.
3. AWS access Terraform reconcile apply narrowed to the exact Snowflake-managed AWS principal.
4. Snowflake Terraform re-apply.
5. Snowflake access Terraform apply for roles and grants.
6. Native-pull validation artifact generation in `infra/snowflake/sql/prod_native_pull_handshake.json`.
7. `dbt deps`, `dbt run`, and `dbt test`.
8. Streamlit artifact upload to the Terraform-managed dashboard stage.

Validation, dbt, and dashboard upload are opt-in:

```bash
bash infra/scripts/deploy-snowflake-stack.sh --env-name prod --snow-connection edgartools-prod --run-validation
bash infra/scripts/deploy-snowflake-stack.sh --env-name prod --snow-connection edgartools-prod --run-dbt
bash infra/scripts/deploy-snowflake-stack.sh --env-name prod --snow-connection edgartools-prod --upload-dashboard
```

---

## Step 6 — Run the Warehouse (Source to Bronze)

The warehouse CLI fetches filings from SEC EDGAR and writes Parquet files to S3.

### Step Functions Run

Terraform does not create Step Functions or schedules. After Step 3, start an
operator-managed state machine explicitly:

```bash
STATE_MACHINE_ARN="$(
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["state_machines"]["bootstrap"])' \
    infra/aws-prod-application.json
)"

aws stepfunctions start-execution \
  --profile sec_platform_deployer \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --input '{"trigger":"operator","workflow":"bootstrap"}'
```

For a bounded replay, pass a `cik_list` string to workflows that support it:

```bash
aws stepfunctions start-execution \
  --profile sec_platform_deployer \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --input '{"trigger":"operator","workflow":"bootstrap","cik_list":"0000320193,0000789019"}'
```

### Local Run (development / testing)

```bash
export EDGAR_IDENTITY="EdgarTools Platform thepaulananth@gmail.com"
edgar-warehouse bootstrap --tracking-status-filter active
```

---

## Step 7 — Run dbt Separately (Optional)

dbt reads Parquet data staged in Snowflake and materialises the gold dynamic tables.

```bash
cd infra/snowflake/dbt/edgartools_gold

# Create profiles.yml from the example
cp profiles.yml.example profiles.yml
```

`profiles.yml` uses environment variables. Set them before running dbt:

```bash
export DBT_SNOWFLAKE_ACCOUNT="ORGNAME-ACCOUNTNAME"
export DBT_SNOWFLAKE_USER="your_user"
export DBT_SNOWFLAKE_PASSWORD="your_password"
export DBT_SNOWFLAKE_ROLE="EDGARTOOLS_PROD_DEPLOYER"
export DBT_SNOWFLAKE_DATABASE="EDGARTOOLS_PROD"
export DBT_SNOWFLAKE_WAREHOUSE="EDGARTOOLS_PROD_REFRESH_WH"
```

Run dbt against the prod target:

```bash
dbt deps
dbt run --target prod
dbt test --target prod
```

This creates 10 objects in `EDGARTOOLS_PROD.EDGARTOOLS_GOLD`:
- 9 dynamic tables: `COMPANY`, `FILING_DETAIL`, `FILING_ACTIVITY`, `TICKER_REFERENCE`,
  `OWNERSHIP_ACTIVITY`, `OWNERSHIP_HOLDINGS`, `ADVISER_DISCLOSURES`, `ADVISER_OFFICES`,
  `PRIVATE_FUNDS`
- 1 view: `EDGARTOOLS_GOLD_STATUS`

> **Note**: Gold dynamic tables use `TARGET_LAG = 6 hours` (change-propagation
> Ticket 39). `DOWNSTREAM` did not refresh gold leaves in prod — refresh
> history was `MANUAL` only via `REFRESH_AFTER_LOAD`.

---

## Step 8 — Deploy the Dashboard Separately (Optional)

### Option A — Streamlit-in-Snowflake (production)

Requires a SnowCLI connection configured and the Terraform-managed dashboard stage to exist.

```bash
# Default: uploads to EDGARTOOLS_DEV.EDGARTOOLS_DASHBOARD.DASHBOARD_SRC
bash infra/snowflake/streamlit/deploy.sh

# For prod:
SNOW_CONNECTION=edgartools-prod \
DASHBOARD_DATABASE=EDGARTOOLS_PROD \
DASHBOARD_ENVIRONMENT=prod \
DASHBOARD_WAREHOUSE_RELEASE_EVIDENCE=docs/release-readiness/releases/<rc>/release-evidence.json \
bash infra/snowflake/streamlit/deploy.sh
```

The access Terraform must be applied first so
`EDGARTOOLS_<ENV>_DASHBOARD_OWNER` inherits the bounded reader contract and
has stage access. Deployment backs up the prior release, safely prunes only
validated `sha-<12 hex>` release directories beyond the retention count,
recreates the object under the dedicated owner role, verifies staged file
digests, and runs bounded smoke reads as both owner and viewer. Secret-free
release and verification JSON are written below
`infra/snowflake/streamlit/.evidence/<environment>/dashboard/`.

The warehouse evidence input makes dashboard drift explicit:
`warehouse_dashboard_alignment.status` is `aligned`, `drift`, or `unknown`.
It does not turn dashboard acceptance into full-chain data acceptance.

Test rollback to the prior version recorded in release evidence:

```bash
SNOW_CONNECTION=edgartools-prod \
DASHBOARD_DATABASE=EDGARTOOLS_PROD \
DASHBOARD_ENVIRONMENT=prod \
bash infra/snowflake/streamlit/deploy.sh --rollback sha-<12-hex>
```

Rollback removes only the known root release files, copies the selected
immutable backup, and must pass both role smokes. It writes a separate
`rollback-<version>.json` exercise artifact.

After upload, open Snowsight → Streamlit →
`EDGARTOOLS_PROD.EDGARTOOLS_DASHBOARD.EDGARTOOLS_DASHBOARD`.

### Option B — External Streamlit (local or self-hosted)

```bash
cd examples/dashboard
pip install -r requirements.txt

export SNOWFLAKE_ACCOUNT="ORGNAME-ACCOUNTNAME"
export SNOWFLAKE_USER="your_user"
export SNOWFLAKE_PASSWORD="your_password"
# Optional overrides (default to EDGARTOOLS and EDGARTOOLS_GOLD):
export EDGARTOOLS_DATABASE="EDGARTOOLS_PROD"
export EDGARTOOLS_SCHEMA="EDGARTOOLS_GOLD"

streamlit run edgar_universe_dashboard.py
```

---

## Verification

After all steps complete, run these checks:

```bash
# Verify dbt models pass their tests
cd infra/snowflake/dbt/edgartools_gold
dbt test --target prod

# Verify the warehouse CLI is installed
edgar-warehouse --help

# Verify the Python package is importable
python -c "from edgar_warehouse.cli import main; print('OK')"
```

In Snowflake, confirm the gold status view returns rows:

```sql
SELECT * FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS LIMIT 10;
```

---

## Gotchas and Known Issues

### Docker Image Creation

- **Windows cannot use `linux` mode directly.** Use
  `infra/scripts/publish-warehouse-image-via-wsl.sh` from Git Bash (not PowerShell). It
  re-enters WSL and bridges to the Windows Docker and AWS CLIs.
- **WSL bridge assumes Docker at** `C:\Program Files\Docker\Docker\resources\bin\docker.exe`.
  Set `WINDOWS_DOCKER_BRIDGE` (as a WSL path: `/mnt/c/...`) if your Docker is elsewhere.
- **WSL bridge assumes AWS CLI at** `C:\Program Files\Amazon\AWSCLIV2\aws.exe`.
  Set `WINDOWS_AWS_BRIDGE` if different.
- **Default WSL distro is `Ubuntu`.** Pass `--wsl-distro <name>` if yours is named
  differently (e.g. `Ubuntu-22.04`).
- **Alternative: `--mode crane`** — builds locally, saves a tarball, and pushes with
  `crane`. Requires `crane`:
  ```bash
  go install github.com/google/go-containerregistry/cmd/crane@latest
  ```
- **`docker buildx` is required** regardless of mode. Docker Desktop >= 24 ships it.
- **ECR repository must exist before the image push.** It is created by the
  AWS infrastructure apply in Step 2.

### Terraform

- **Terraform CLI should be `1.14.8` or another compatible `1.14.x` release.** The Snowflake
  roots require `~> 1.14.8`.
  due to provider version pins.
- **After apply, populate the EDGAR identity secret manually** —
  `edgartools-prod-edgar-identity` (see Step 2).
- **Do not create runner access keys.** The AWS access root creates
  `sec_platform_runner_execution`, `sec_platform_runner_task`, and
  `sec_platform_runner_step_functions` service roles. The
  `edgartools-prod-runner-credentials` secret is retained only as a legacy
  compatibility container for non-runtime operator storage.
- **Capture `snowflake_manifest_sns_topic_arn`** from provisioning outputs — the bootstrap
  script needs it to subscribe Snowflake's Snowpipe to the SNS topic.
- **`accounts/prod` has `prevent_destroy` on the bronze bucket.** `terraform destroy` will
  error unless you remove the lifecycle rule manually first.
- **S3 state locking uses `use_lockfile = true`** — no DynamoDB table is required.

### Snowflake Native Pull

- **Use the deploy wrapper** for normal deployments. It coordinates the AWS bootstrap apply,
  Snowflake apply, AWS trust reconciliation, Snowflake re-apply, validation, dbt, and dashboard
  upload in one flow.
- **`export_root_url` must have a trailing slash** on `snowflake_exports/` — the value
  must match the Snowflake integration allow-list exactly.
- **SnowCLI connection name** (`--snow-connection`) must match a connection defined in
  your SnowCLI config (`~/.snowflake/config.toml`).
- **The SQL files in `infra/snowflake/sql/bootstrap/` are retained as implementation reference**.
  They are no longer the operator-facing deployment path.

### dbt

- **Snowflake Enterprise+ edition is required** for dynamic tables. The `dbt run` will
  fail with a privilege or feature error on Standard edition.
- **Create `profiles.yml` from `profiles.yml.example`** before running dbt. dbt will not
  run without a `profiles.yml` in the project directory.
- **`TARGET_LAG = 6 hours`** for gold and silver dynamic tables. `DOWNSTREAM`
  does not refresh gold leaves (change-propagation Ticket 39: prod refresh
  history was `MANUAL` only).
- **`DBT_SNOWFLAKE_DATABASE` must be set** — the dbt project uses
  `{{ env_var('DBT_SNOWFLAKE_DATABASE') }}` and will fail at parse time if the variable is
  missing.

### Warehouse CLI

- **`EDGAR_IDENTITY`** must be a valid SEC User-Agent string (`"Name email@example.com"`).
  SEC EDGAR returns HTTP 403 for requests without a compliant User-Agent.

### Streamlit Deployment (Option A)

- **The Terraform-managed dashboard stage must exist** before running `deploy.sh`. It is
  created by the Snowflake Terraform root in Step 4.
- **SnowCLI connection** (`SNOW_CONNECTION`) must be configured in
  `~/.snowflake/config.toml` and have `PUT` privileges on the stage.

### Bookkeeping Store Cutover (DuckDB Retirement, in progress)

- **The 11 operational bookkeeping tables** (checkpoints, sync-state, leases,
  the run audit trail, the gold publish manifest, and reconcile findings —
  see `.scratch/duckdb-retirement-cutover/issues/02-move-bookkeeping-tables-to-snowflake-postgres.md`)
  are moving off DuckDB onto a dedicated Snowflake-hosted Postgres store
  (`edgar_warehouse/bookkeeping/`, `BOOKKEEPING_DATABASE_URL`).
- **The new store starts empty at cutover — it is not migrated from
  existing DuckDB state.** Every CIK that is currently paused or completed
  in `sec_company_sync_state` reverts to pending the moment the write path
  repoints at this store, and becomes eligible for a full re-bootstrap on
  the next run. This is an explicit, accepted operator decision (DuckDB
  Retirement wayfinder map, Ticket 08), not a bug — but it is a
  platform-wide reactivation of the entire tracked-company universe, so
  size the first post-cutover run's expected cost/duration accordingly
  before triggering it, and don't schedule the cutover immediately before
  a cost-sensitive window.
- **Not yet live as of this note** — see
  `.scratch/duckdb-retirement-cutover/issues/04-provision-live-bookkeeping-postgres.md`
  for the live-provisioning ticket and
  `.scratch/duckdb-retirement-cutover/issues/10-atomic-write-path-cutover.md`
  for the ticket that actually repoints the write path (and triggers this
  reactivation).

---

## Recovering from a partial load_history failure

When `load_history` reaches FAILED state, one or more batches in the `BatchBootstrap`
Distributed Map failed after exhausting retries. Because `ToleratedFailurePercentage: 0`,
a single batch failure drives the execution to FAILED — other batches may have succeeded.

**Recovery is safe to run immediately.** DEC-009: already-loaded CIKs are skipped on
re-run, so a full `load_history` re-run processes only the CIKs that were not loaded.

### Option A: Full re-run (recommended)

The simplest recovery. Already-loaded CIKs are skipped automatically (DEC-009
idempotency). Use this unless you need to load only specific CIKs.

```bash
./scripts/ops/trigger.sh bootstrap
```

### Option B: Targeted recovery for specific CIKs

Use this if you want to re-run only the failed CIKs rather than re-seeding the full
universe. Requires identifying the failed child executions from the Map Run.

**Step 1: Find the failed execution ARN**

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
aws stepfunctions list-executions \
  --state-machine-arn "arn:aws:states:us-east-1:${ACCOUNT}:stateMachine:edgartools-dev-load-history" \
  --status-filter FAILED \
  --max-results 1 \
  --query 'executions[0].executionArn' \
  --output text
```

**Step 2: Find the BatchBootstrap Map Run ARN**

```bash
EXEC_ARN=<execution-arn-from-step-1>
aws stepfunctions get-execution-history \
  --execution-arn "$EXEC_ARN" --output json \
  | python3 -c "
import json,sys
for e in json.load(sys.stdin)['events']:
    if e['type']=='MapRunStarted':
        print(e['mapRunStartedEventDetails']['mapRunArn']); break
"
```

**Step 3: List failed child executions**

```bash
MAP_RUN_ARN=<map-run-arn-from-step-2>
aws stepfunctions list-executions \
  --map-run-arn "$MAP_RUN_ARN" \
  --status-filter FAILED \
  --output json \
  --query 'executions[].executionArn'
```

**Step 4: Extract CIK list from each failed child execution**

```bash
CHILD_EXEC_ARN=<child-execution-arn-from-step-3>
aws stepfunctions describe-execution \
  --execution-arn "$CHILD_EXEC_ARN" \
  --query 'input' --output text \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['cik_list'])"
```

**Step 5b: Per-CIK targeted resync (for single-company recovery)**

```bash
# scope_type "cik" is a valid targeted_resync input (warehouse_orchestrator.py line 722)
CIK=<cik-from-step-4>
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:us-east-1:${ACCOUNT}:stateMachine:edgartools-dev-targeted-resync" \
  --name "targeted-resync-${CIK}-$(date +%s)" \
  --input "{\"scope_type\": \"cik\", \"scope_key\": \"${CIK}\"}"
```

### Note on post-failure child executions

AWS Step Functions may continue to run child workflows in a Map Run even after the
tolerated failure threshold is exceeded, before the Map Run is marked failed. This is
by-design behavior. The parent execution status (FAILED) is the authoritative signal —
do not interpret some children completing as a partial success.

### Failures during MDM stages

If `load_history` fails during `MdmRun`, `MdmBackfill`, `MdmSync`, or `MdmVerify`
(after `BatchBootstrap` succeeded), skip re-batching and run only the MDM+gold stages:

```bash
./scripts/ops/trigger.sh mdm-gold
```
