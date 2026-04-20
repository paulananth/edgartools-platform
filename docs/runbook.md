# EdgarTools Platform — End-to-End Setup Runbook

This guide walks from zero to a working gold layer in Snowflake, including the Streamlit
dashboard. Follow each section in order; each step depends on the previous one completing
successfully.

## Architecture Overview

```
SEC EDGAR API → edgar-warehouse Python CLI → AWS S3 (Parquet, bronze)
  → Snowflake storage integration (EDGARTOOLS_SOURCE)
  → dbt run → EDGARTOOLS_GOLD dynamic tables (8 tables + 1 status view)
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
| AWS (admin access) | ECS, ECR, S3, CodeBuild, Step Functions, Secrets Manager |
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
| Terraform | **exactly 1.14.7** | terraform.io |
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
| `AWS_PROFILE` or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Terraform, CLI, ECR | AWS IAM |
| `SNOWFLAKE_ACCOUNT` | Scripts, dbt | Snowflake admin — format: `ORGNAME-ACCOUNTNAME` |
| `SNOWFLAKE_USER` | Scripts, dbt | Snowflake admin |
| `SNOWFLAKE_PASSWORD` | Scripts, dbt | Snowflake admin |
| `TF_VAR_snowflake_organization_name` | Snowflake Terraform provider | From Snowflake creds |
| `TF_VAR_snowflake_account_name` | Snowflake Terraform provider | From Snowflake creds |
| `TF_VAR_snowflake_user` | Snowflake Terraform provider | From Snowflake creds |
| `STATE_MACHINE_ARN` | `trigger-next-100.sh` | From Terraform outputs (Step 1) |
| `EDGAR_USER_AGENT` | `trigger-next-100.sh` | `"Your Name your@email.com"` |

---

## Step 1 — Terraform: Bootstrap State Bucket

The state bucket must exist before any other Terraform root can initialise its backend.

```bash
cd infra/terraform/bootstrap-state
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set environment ("dev" or "prod") and aws_region
terraform init
terraform apply
```

Note the bucket name printed in the output (e.g. `edgartools-prod-tfstate`). You will use
this in every subsequent backend configuration.

---

## Step 2 — Terraform: AWS Infrastructure

Apply the AWS account root. This creates ECR, ECS, S3 buckets, Step Functions, Secrets
Manager containers, and the Snowflake export IAM role.

```bash
cd infra/terraform/accounts/prod

# Configure the remote state backend
cp backend.hcl.example backend.hcl
# Edit backend.hcl — set bucket to the name from Step 1
# Default contents:
#   bucket  = "edgartools-prod-tfstate"
#   key     = "accounts/prod/terraform.tfstate"
#   region  = "us-east-1"
#   encrypt = true

terraform init -backend-config=backend.hcl

# Configure inputs
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars:
#   edgar_identity_value = "Your Name your@email.com"
#   container_image      = (leave placeholder for now — set after Step 3)
```

Apply in dependency order (the image does not exist yet, so apply the ECR repo first):

```bash
terraform apply -target module.storage
terraform apply -target module.runtime
```

> **Note**: `accounts/prod` has `prevent_destroy = true` on the bronze bucket.
> `terraform destroy` will fail unless you remove that guard manually.

After apply, record the following outputs — you will need them in later steps:

```bash
terraform output ecr_repository_url             # used in Step 3
terraform output snowflake_manifest_sns_topic_arn  # used in Step 4
terraform output snowflake_storage_role_arn      # used in Step 4
terraform output snowflake_export_root_url        # used in Step 4
terraform output runner_user_name                # used below
terraform output state_machine_arns              # set STATE_MACHINE_ARN from this
```

### Populate Secrets

Two secrets are created as empty containers by Terraform; populate them now:

```bash
# EDGAR identity (used by the warehouse CLI as the SEC User-Agent header)
aws secretsmanager put-secret-value \
  --secret-id edgartools-prod-edgar-identity \
  --secret-string "Your Name your@email.com"

# Runner IAM credentials (ECS task runner)
aws iam create-access-key --user-name edgartools-prod-runner \
  | jq -r '{"access_key_id": .AccessKey.AccessKeyId, "secret_access_key": .AccessKey.SecretAccessKey}' \
  | aws secretsmanager put-secret-value \
    --secret-id edgartools-prod-runner-credentials \
    --secret-string file:///dev/stdin
```

---

## Step 3 — Build and Push the Warehouse Docker Image

The ECR repository now exists. Build the `linux/amd64` image and push it.

### Linux / CI (preferred)

```bash
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-prod-warehouse \
  --image-tag "$(git rev-parse HEAD)" \
  --mode linux
```

### Windows (Git Bash + WSL)

```bash
bash infra/scripts/publish-warehouse-image-via-wsl.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-prod-warehouse \
  --image-tag "$(git rev-parse HEAD)"
```

Both scripts print a `@digest` reference when done, for example:

```
123456789012.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-warehouse@sha256:abc123...
```

Copy that `@digest` value into `terraform.tfvars`:

```hcl
container_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-warehouse@sha256:abc123..."
```

Then complete the AWS apply:

```bash
cd infra/terraform/accounts/prod
terraform apply
```

---

## Step 4 — Terraform: Snowflake Baseline Objects

This creates the `EDGARTOOLS_PROD` database, schemas, roles, and warehouses.

```bash
cd infra/terraform/snowflake/accounts/prod

cp backend.hcl.example backend.hcl
# Edit backend.hcl — set bucket to the name from Step 1
# Default contents:
#   bucket = "edgartools-prod-tfstate"
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

terraform apply
```

---

## Step 5 — Snowflake Bootstrap SQL (Two-Pass)

This wires up the Snowflake storage integration to the AWS S3 export bucket and installs
the Snowpipe, manifest stream, and refresh wrapper procedures.

### Pass 1 — Create the Storage Integration

```bash
# Run from the repo root
uv run python infra/snowflake/sql/bootstrap_native_pull.py \
  --aws-root infra/terraform/accounts/prod \
  --snowflake-root infra/terraform/snowflake/accounts/prod \
  --connection snowconn \
  --artifact-path infra/snowflake/sql/prod_native_pull_handshake.json
```

The script reads Terraform output values automatically. After it completes:

1. Open `infra/snowflake/sql/prod_native_pull_handshake.json`.
2. Note the `snowflake_storage_external_id` value.
3. Add it to `infra/terraform/accounts/prod/terraform.tfvars`:

   ```hcl
   snowflake_storage_external_id = "<id-from-artifact-json>"
   ```

4. Re-apply the AWS root to grant Snowflake the IAM trust:

   ```bash
   cd infra/terraform/accounts/prod
   terraform apply
   ```

### Pass 2 — Validate Native Pull

```bash
uv run python infra/snowflake/sql/bootstrap_native_pull.py \
  --aws-root infra/terraform/accounts/prod \
  --snowflake-root infra/terraform/snowflake/accounts/prod \
  --connection snowconn \
  --artifact-path infra/snowflake/sql/prod_native_pull_handshake.json \
  --storage-external-id "<id-from-artifact-json>" \
  --validate-native-pull
```

A successful pass 2 confirms that Snowflake can `LIST` and read `COPY_HISTORY` from the S3
export bucket.

---

## Step 6 — Run the Warehouse (Source to Bronze)

The warehouse CLI fetches filings from SEC EDGAR and writes Parquet files to S3.

### Trigger via Step Functions (production)

```bash
export STATE_MACHINE_ARN="arn:aws:states:us-east-1:<aws-account-id>:stateMachine:edgartools-prod-bootstrap-recent-10"
export SNOWFLAKE_ACCOUNT="ORGNAME-ACCOUNTNAME"
export SNOWFLAKE_USER="your_user"
export SNOWFLAKE_PASSWORD="your_password"
export EDGAR_USER_AGENT="Your Name your@email.com"

# Triggers Step Functions for the next 100 CIKs not yet loaded
bash infra/scripts/trigger-next-100.sh
```

The script queries `EDGARTOOLS_SOURCE.COMPANY` to find CIKs not yet loaded, then starts a
Step Functions execution. Monitor progress with the `aws stepfunctions describe-execution`
command printed at the end.

### Local Run (development / testing)

```bash
export EDGAR_USER_AGENT="Your Name your@email.com"
edgar-warehouse bootstrap --tracking-status-filter active
```

---

## Step 7 — Run dbt (Bronze to Gold)

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

This creates 9 objects in `EDGARTOOLS_PROD.EDGARTOOLS_GOLD`:
- 8 dynamic tables: `COMPANY`, `FILING_DETAIL`, `FILING_ACTIVITY`, `TICKER_REFERENCE`,
  `OWNERSHIP_ACTIVITY`, `OWNERSHIP_HOLDINGS`, `ADVISER_DISCLOSURES`, `ADVISER_OFFICES`,
  `PRIVATE_FUNDS`
- 1 view: `EDGARTOOLS_GOLD_STATUS`

> **Note**: Dynamic tables use `TARGET_LAG = DOWNSTREAM`, meaning they refresh on query.
> The first query after a warehouse load may be slower than subsequent queries.

---

## Step 8 — Deploy the Dashboard

### Option A — Streamlit-in-Snowflake (production)

Requires a SnowCLI connection configured and the Terraform-managed dashboard stage to exist.

```bash
# Default: uploads to EDGARTOOLS_DEV.EDGARTOOLS_DASHBOARD.DASHBOARD_SRC
bash infra/snowflake/streamlit/deploy.sh

# For prod:
SNOW_CONNECTION=edgartools-prod \
DASHBOARD_DATABASE=EDGARTOOLS_PROD \
bash infra/snowflake/streamlit/deploy.sh
```

After upload, open Snowsight → Streamlit → `EDGARTOOLS_PROD.EDGARTOOLS_DASHBOARD.EDGARTOOLS_DASHBOARD`.

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
- **Feed the `@digest`, not the tag, into `container_image`** in `terraform.tfvars`.
  The script prints the verified digest; copy it verbatim.
- **`docker buildx` is required** regardless of mode. Docker Desktop >= 24 ships it.
- **ECR repository must exist before the image push.** It is created by the
  `module.runtime` apply in Step 2.

### Terraform

- **Terraform CLI must be exactly `1.14.7`.** Other versions are not tested and may fail
  due to provider version pins.
- **Publish the warehouse image (Step 3) before running `terraform apply` on `accounts/prod`
  with `container_image` set.** Terraform validates the image reference during plan.
- **After apply, populate both secrets manually** — `edgartools-prod-edgar-identity` and
  `edgartools-prod-runner-credentials` (see Step 2).
- **Runner IAM access key is created outside Terraform:**
  ```bash
  aws iam create-access-key --user-name edgartools-prod-runner
  ```
- **Capture `snowflake_manifest_sns_topic_arn`** from Terraform outputs — the bootstrap
  script needs it to subscribe Snowflake's Snowpipe to the SNS topic.
- **`accounts/prod` has `prevent_destroy` on the bronze bucket.** `terraform destroy` will
  error unless you remove the lifecycle rule manually first.
- **S3 state locking uses `use_lockfile = true`** — no DynamoDB table is required.

### Snowflake Bootstrap

- **Use the Python driver**, not raw SQL files directly. The driver sets the required
  session variables and runs the SQL files in the correct order.
- **Two-pass loop**: pass 1 captures `snowflake_storage_external_id`; feed it back to AWS
  Terraform; then run pass 2 with `--storage-external-id` and `--validate-native-pull`.
- **`export_root_url` must have a trailing slash** on `snowflake_exports/` — the value
  must match the Snowflake integration allow-list exactly.
- **SQL files use `IDENTIFIER($variable_name)`** — do not run them manually without setting
  all session variables listed in `infra/snowflake/sql/README.md`.
- **SnowCLI connection name** (`--connection snowconn`) must match a connection defined in
  your SnowCLI config (`~/.snowflake/config.toml`).

### dbt

- **Snowflake Enterprise+ edition is required** for dynamic tables. The `dbt run` will
  fail with a privilege or feature error on Standard edition.
- **Create `profiles.yml` from `profiles.yml.example`** before running dbt. dbt will not
  run without a `profiles.yml` in the project directory.
- **`TARGET_LAG = DOWNSTREAM`** — dynamic tables refresh lazily on query. The first query
  after loading new data may be slow; subsequent queries hit the refreshed table.
- **`DBT_SNOWFLAKE_DATABASE` must be set** — the dbt project uses
  `{{ env_var('DBT_SNOWFLAKE_DATABASE') }}` and will fail at parse time if the variable is
  missing.

### Warehouse CLI / Step Functions

- **`STATE_MACHINE_ARN` must be set** before calling `trigger-next-100.sh`. Retrieve it
  from `terraform output state_machine_arns` after Step 2.
- **`EDGAR_USER_AGENT`** must be a valid SEC User-Agent string (`"Name email@example.com"`).
  SEC EDGAR returns HTTP 403 for requests without a compliant User-Agent.
- **`snowflake-connector-python` must be installed** for `trigger-next-100.sh` to work.
  Install with `pip install snowflake-connector-python`.

### Streamlit Deployment (Option A)

- **The Terraform-managed dashboard stage must exist** before running `deploy.sh`. It is
  created by the Snowflake Terraform root in Step 4.
- **SnowCLI connection** (`SNOW_CONNECTION`) must be configured in
  `~/.snowflake/config.toml` and have `PUT` privileges on the stage.
