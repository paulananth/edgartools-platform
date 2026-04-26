# EdgarTools Platform — End-to-End Setup Runbook

This guide walks from zero to the legacy AWS/Snowflake gold layer and documents the
Azure/Databricks parallel-run path used for migration. Keep AWS/Snowflake running until
Azure/Databricks output validation has passed.

## Architecture Overview

```
SEC EDGAR API → edgar-warehouse Python CLI → AWS S3 (Parquet, bronze)
  → Snowflake storage integration (EDGARTOOLS_SOURCE)
  → dbt run → EDGARTOOLS_GOLD dynamic tables (9 tables + 1 status view)
  → Streamlit dashboard
```

Migration target:

```
SEC EDGAR API → edgar-warehouse Python CLI → ADLS Gen2 (Parquet)
  → Unity Catalog external tables / Databricks SQL
  → dbt-databricks → EDGARTOOLS_GOLD tables/views
```

Layers:
- **Source**: SEC EDGAR API (live pull by the warehouse CLI)
- **Bronze**: AWS S3 Parquet exports written by `edgar-warehouse`
- **Azure Bronze**: ADLS Gen2 Parquet exports written by the same runtime during parallel runs
- **Silver** (internal): DuckDB intermediate processing inside the warehouse container
- **Gold**: Snowflake `EDGARTOOLS_GOLD` dynamic tables managed by dbt
- **Databricks Gold**: Databricks tables/views managed by `dbt-databricks`

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
| Azure CLI | latest | learn.microsoft.com/cli/azure |
| Terraform | **1.14.8 or later in the 1.14.x line** | terraform.io |
| SnowCLI (`snow`) | latest | `pip install snowflake-cli-labs` |
| Bash | any | native on Linux/Mac; WSL on Windows |
| dbt-snowflake | >= 1.7 | `pip install dbt-snowflake` |
| dbt-databricks | >= 1.8 | `pip install dbt-databricks` |

### Clone the Repository

```bash
git clone https://github.com/paulananth/edgartools-platform
cd edgartools-platform
pip install -e ".[s3,snowflake]"
pip install dbt-snowflake

# Azure/Databricks parallel run
pip install -e ".[azure,databricks]"
pip install dbt-databricks
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

Azure/Databricks migration variables:

| Variable | Used By | Notes |
|----------|---------|-------|
| `SERVING_EXPORT_ROOT` | Warehouse runtime | Preferred export root for Databricks/Snowflake serving Parquet |
| `SNOWFLAKE_EXPORT_ROOT` | Warehouse runtime | Temporary fallback during migration |
| `DBT_DATABRICKS_HOST` | dbt | Databricks workspace host |
| `DBT_DATABRICKS_HTTP_PATH` | dbt | SQL warehouse HTTP path |
| `DBT_DATABRICKS_TOKEN` | dbt | Personal access token or service-principal token |
| `DBT_DATABRICKS_CATALOG` | dbt | Unity Catalog catalog for source and gold models |
| `DBT_SOURCE_SCHEMA` | dbt | Source schema, default `EDGARTOOLS_SOURCE` |
| `DBT_GOLD_SCHEMA` | dbt | Gold schema, default `EDGARTOOLS_GOLD` |

---

## Credential Strategy

Azure/Databricks uses managed identity for cloud resources and Key Vault for unavoidable
secret values.

- **EDGAR identity**: Store the SEC User-Agent contact string in Key Vault secret
  `edgar-identity`. The runtime receives it as `EDGAR_IDENTITY`. Use an app/operator
  name and monitored email, for example `EdgarTools Platform data-ops@example.com`.
- **Azure storage**: Container Apps Jobs use managed identity with `Storage Blob Data
  Contributor` on the ADLS Gen2 account. Do not use account keys, SAS tokens, or
  connection strings.
- **Databricks dbt**: Store local/dev dbt fallback values in Key Vault secrets
  `databricks-host`, `databricks-http-path`, `databricks-token`, and optionally
  `databricks-catalog`, `dbt-source-schema`, and `dbt-gold-schema`. Production should
  use a service principal or workload identity from CI/Databricks Jobs rather than a
  personal token.
- **Databricks storage**: Use Unity Catalog storage credentials and external locations
  backed by managed identity/access connector. Do not grant Databricks ADLS account keys.
- **MDM Azure SQL**: When the Azure MDM data plane is enabled, Terraform creates Key
  Vault secret `mdm-database-url` for `MDM_DATABASE_URL`. It uses a generated SQL
  admin password stored in `mdm-sql-admin-password`.
- **MDM Neo4j**: Terraform runs Neo4j as a Container App with Azure Files persistence.
  Key Vault secret `mdm-neo4j` stores a JSON object with `uri`, `user`, and
  `password`; Terraform also writes split secrets `mdm-neo4j-uri`,
  `mdm-neo4j-user`, and `mdm-neo4j-password` for Container Apps env vars.
- **MDM API keys**: Terraform stores API keys in Key Vault secret `mdm-api-keys`. If
  `mdm_api_keys` is empty, a generated key is stored there. Container Apps use
  `mdm-api-keys-csv` as `MDM_API_KEYS`.

The Azure CLI and Databricks CLI are operator tools for bootstrapping and validation;
production runtime auth should not depend on a local CLI login session.

---

## Azure/Databricks Parallel Run

Use this path to stand up the replacement platform without removing AWS/Snowflake.

```bash
# Build and push the warehouse image to ACR
bash infra/scripts/publish-warehouse-image-acr.sh \
  --acr-name edgartoolsdevacr01 \
  --image-tag "$(git rev-parse --short HEAD)"

# Apply Azure infrastructure and run the validation job
cd infra/terraform/azure/accounts/dev
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
# Edit backend.hcl and terraform.tfvars, especially container_image.
# To provision MDM, set enable_mdm=true plus globally unique
# mdm_sql_server_name and mdm_neo4j_storage_account_name.
cd ../../../../..

# First create the resource group and Key Vault.
bash infra/scripts/deploy-azure-stack.sh --env dev --key-vault-only

# Store EDGAR identity and optional dbt/Databricks settings outside Terraform state.
bash infra/scripts/bootstrap-azure-secrets.sh \
  --key-vault-name edgartools-dev-kv-01 \
  --edgar-identity "EdgarTools Platform data-ops@example.com" \
  --databricks-host "https://adb-..." \
  --databricks-http-path "/sql/1.0/warehouses/..." \
  --databricks-token "..."

# Then apply the full Azure stack and start the validation job.
bash infra/scripts/deploy-azure-stack.sh --env dev --start-validation-job
```

Terraform outputs the runtime roots:

```bash
terraform -chdir=infra/terraform/azure/accounts/dev output warehouse_bronze_root
terraform -chdir=infra/terraform/azure/accounts/dev output warehouse_storage_root
terraform -chdir=infra/terraform/azure/accounts/dev output serving_export_root
terraform -chdir=infra/terraform/azure/accounts/dev output mdm_sql_server_fqdn
terraform -chdir=infra/terraform/azure/accounts/dev output mdm_neo4j_uri
terraform -chdir=infra/terraform/azure/accounts/dev output mdm_container_app_job_names
```

Run the MDM e2e checks after Azure SQL and Neo4j are provisioned:

```bash
EDGAR_WAREHOUSE_CMD="uv run --extra mdm edgar-warehouse" \
  bash infra/scripts/test-mdm-e2e.sh --env dev
```

The script hydrates `MDM_DATABASE_URL`, `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD`, and `MDM_API_KEYS` from Key Vault, then runs:

- `edgar-warehouse mdm check-connectivity --neo4j`
- `edgar-warehouse mdm migrate`
- `edgar-warehouse mdm counts`

To validate from inside Container Apps instead of the operator machine, add
`--start-container-jobs`. That starts the Terraform-managed MDM migrate, run, and
counts jobs. The MDM run job receives `MDM_SILVER_DUCKDB`; by default it points to
`<WAREHOUSE_STORAGE_ROOT>/silver/sec/silver.duckdb`, and can be overridden with
`mdm_silver_duckdb_path`.

Register Databricks external tables with
`infra/databricks/sql/register_external_tables.sql`, then run dbt:

```bash
export DBT_DATABRICKS_HOST="https://adb-..."
export DBT_DATABRICKS_HTTP_PATH="/sql/1.0/warehouses/..."
export DBT_DATABRICKS_TOKEN="..."
export DBT_DATABRICKS_CATALOG="edgartools_dev"
export DBT_SOURCE_SCHEMA="EDGARTOOLS_SOURCE"
export DBT_GOLD_SCHEMA="EDGARTOOLS_GOLD"

bash infra/scripts/run-databricks-dbt.sh --target databricks_dev

# Or hydrate DBT_* values from Azure Key Vault:
bash infra/scripts/run-databricks-dbt.sh \
  --target databricks_dev \
  --key-vault-name edgartools-dev-kv-01
```

Acceptance before cutover:

- Run the same bounded scope on both paths, starting with `bootstrap-recent-10`.
- Compare row counts for company, filing activity/detail, ownership, adviser, private funds, and ticker reference.
- Compare key samples by CIK and accession number.
- Run at least one daily incremental and one reconciliation-style run successfully before production cutover.

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

## Step 4 — Prepare the Snowflake Terraform Root

Prepare the Snowflake root so the wrapper in Step 5 can initialize it and apply both the
baseline and native-pull objects.

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

```

If you use the wrapper in Step 5, you do not need to run a separate manual `terraform apply`
in this root.

---

## Step 5 — Deploy Snowflake, dbt, and Dashboard

Use the wrapper script to coordinate the AWS and Snowflake Terraform states, reconcile the
Snowflake IAM trust automatically, run dbt, validate the native-pull contract, and upload the
Streamlit dashboard artifacts.

```bash
# Run from the repo root
bash infra/scripts/deploy-snowflake-stack.sh \
  --env prod \
  --snow-connection edgartools-prod
```

The wrapper performs these stages in order:

1. AWS Terraform bootstrap apply with temporary trust and deterministic external ID.
2. Snowflake Terraform apply for the storage integration, stage, source tables, pipe, stream, procedures, and task.
3. AWS Terraform reconcile apply narrowed to the exact Snowflake-managed AWS principal.
4. Snowflake Terraform re-apply.
5. Native-pull validation artifact generation in `infra/snowflake/sql/prod_native_pull_handshake.json`.
6. `dbt deps`, `dbt run`, and `dbt test`.
7. Streamlit artifact upload to the Terraform-managed dashboard stage.

If you need to skip parts of the wrapper during troubleshooting, use:

```bash
bash infra/scripts/deploy-snowflake-stack.sh --env prod --skip-validation
bash infra/scripts/deploy-snowflake-stack.sh --env prod --skip-dbt
bash infra/scripts/deploy-snowflake-stack.sh --env prod --skip-dashboard
```

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

> **Note**: Dynamic tables use `TARGET_LAG = DOWNSTREAM`, meaning they refresh on query.
> The first query after a warehouse load may be slower than subsequent queries.

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

- **Terraform CLI should be `1.14.8` or another compatible `1.14.x` release.** The Snowflake
  roots require `~> 1.14.8`.
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
