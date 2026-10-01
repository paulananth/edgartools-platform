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
/ graph prerequisites → `one_click_data_refresh` → standalone gold-refresh
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
- **Silver**: Snowflake `EDGARTOOLS_SILVER` (the warehouse CLI writes to the `EDGARTOOLS_SILVER_LANDING` landing zone; dbt collapses it)
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

The former `edgartools-prod-runner-credentials` empty container is retired. Do
not create runner access keys: runtime uses the `sec_platform_runner_*` service
roles, and deployment uses `sec_platform_deployer`. Reviewed cleanup uses
`scripts/ops/delete_unused_aws_secrets.py`, which schedules a 30-day recoverable
deletion only after Terraform state and live-reference checks pass.

After applying the passive-infrastructure and matching access roots, review the
live deletion plan:

```bash
uv run python scripts/ops/delete_unused_aws_secrets.py \
  --environment prod \
  --profile aws-admin-prod \
  --region us-east-1 \
  --expected-account-id 690839588395 \
  --secret-id edgartools-prod-runner-credentials \
  --secret-id edgartools-prod/mdm/api_keys \
  --secret-id edgartools-prod/mdm/neo4j
```

Apply the same command with `--apply --confirm-delete-unused-secrets`. The
script refuses populated, accessed, referenced, replicated, rotating,
resource-policy-bound, or Terraform-managed secrets. Restore a scheduled
deletion during its 30-day recovery window with `aws secretsmanager
restore-secret --secret-id <name>`.

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

## Step 3 — Publish the Images

The ECR repository, ECS cluster, access roles, subnets, log group, and empty secret
containers now exist. The AWS pipeline (its ECS task definitions and Step Functions,
deployed by the old `deploy-aws-application.sh`) was retired with the commands it
ran (platform validation 2a/2b, 2026-09-30). Only image publishing remains:

```bash
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-prod-images \
  --role mdm \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode auto
```

Running feeds is the Bookkeeping skill's **run** mode (`skills/bookkeeping/`), and
mastering is Clean MDM (`docs/specs/clean-mdm/local-operations.md`).

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

## Step 6 — Run a Feed

The warehouse commands (`bootstrap-full`, `daily-incremental` and the rest) and
their Step Functions were retired. Run a feed with the Bookkeeping skill's
**run** mode (`skills/bookkeeping/RUN.md`).

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
  `sec_platform_runner_step_functions` service roles. The former
  `edgartools-prod-runner-credentials` empty container is retired.
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

- **The 10 operational bookkeeping tables** (checkpoints, sync-state, leases,
  the run audit trail, and the gold publish manifest —
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
