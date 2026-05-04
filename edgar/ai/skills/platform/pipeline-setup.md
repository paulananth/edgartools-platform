---
name: pipeline-setup
description: Complete guide to the edgartools-platform SEC EDGAR data pipeline — architecture, setup, operation, and debugging. Use when setting up the pipeline, running components, or diagnosing issues.
---

# SEC EDGAR Data Pipeline

## Architecture Overview

The pipeline ingests SEC EDGAR filings and delivers structured financial data to a Snowflake gold layer that powers dashboards and analytics.

**Data flow:**

```
SEC EDGAR → edgar-warehouse (ETL) → S3 (Bronze) → Snowflake SOURCE → dbt → GOLD → Dashboard
```

**Layer definitions:**

| Layer | Location | Description |
|---|---|---|
| Bronze | S3 `snowflake_exports/` | Raw parquet exports from edgar-warehouse |
| Source | Snowflake `EDGARTOOLS_SOURCE` schema | External tables / staged data from S3 |
| Gold | Snowflake `EDGARTOOLS_GOLD` schema | dbt dynamic tables, query-ready |

The `edgar-warehouse` CLI runs in AWS ECS Fargate (containerized), reads from SEC EDGAR using the `edgartools` Python library, and writes parquet files to S3. Snowflake ingests via external stage → dbt transforms to gold.

---

## Repo Navigation

| Need | Location |
|---|---|
| Warehouse ETL runtime | `edgar_warehouse/runtime.py`, `edgar_warehouse/gold.py` |
| AWS infrastructure | `infra/terraform/accounts/` |
| Snowflake infrastructure | `infra/terraform/snowflake/` |
| dbt gold models | `infra/snowflake/dbt/edgartools_gold/models/gold/` |
| Bootstrap SQL | `infra/snowflake/sql/bootstrap/` |
| Bootstrap Python driver | `infra/snowflake/sql/bootstrap_native_pull.py` |
| Production dashboard | `infra/snowflake/streamlit/streamlit_app.py` |
| External dashboard | `examples/dashboard/edgar_universe_dashboard.py` |
| Batch scripts | `scripts/batch/` |
| Setup runbook | `docs/runbook.md` |
| MDM universe client | `edgar_warehouse/mdm/universe.py` |
| MDM CLI commands | `edgar_warehouse/mdm/cli.py` |

---

## MDM Setup

The MDM system (Master Data Management) owns the canonical company/adviser/person/fund registry and the **tracked universe** — the list of CIKs the warehouse processes. It uses PostgreSQL (prod) or Azure SQL (Azure path) as its relational store and Neo4j AuraDB for the graph layer.

**Required env vars:**
```bash
export MDM_DATABASE_URL="postgresql://user:pass@host:5432/mdm"  # PostgreSQL
# OR for Azure SQL:
export MDM_DATABASE_URL="mssql+pyodbc://user:pass@server.database.windows.net/mdm?driver=ODBC+Driver+18+for+SQL+Server"

export NEO4J_URI="neo4j+s://<id>.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="<password>"
export MDM_API_KEYS='["<key1>"]'
export EDGAR_IDENTITY="Your Name your@email.com"
```

**MDM setup sequence:**
```bash
# 1. Apply schema + seed reference data (idempotent)
edgar-warehouse mdm migrate

# 2. Verify connectivity
edgar-warehouse mdm check-connectivity --neo4j

# 3. Seed the tracked universe from SEC reference data
edgar-warehouse mdm seed-universe
#    Add --limit 100 for a quick smoke test

# 4. Run entity resolution pipeline
edgar-warehouse mdm run --entity-type company

# 5. Sync relationships to Neo4j
edgar-warehouse mdm sync-graph
```

---

## MDM Health Checks

```bash
# Table row counts
edgar-warehouse mdm counts

# SQL + Neo4j connectivity
edgar-warehouse mdm check-connectivity --neo4j

# List pending curation reviews
edgar-warehouse mdm review list --status pending

# Verify Neo4j graph (node/edge counts)
edgar-warehouse mdm verify-graph
```

**Windows-specific E2E notes:**

The bash E2E scripts (`infra/scripts/test-mdm-e2e.sh`, `infra/scripts/run-neo4j-e2e.sh`) run in Git Bash or WSL. Before running them on Windows:

```powershell
# Install sqlcmd (required by run-neo4j-e2e.sh)
winget install Microsoft.SQLCmdUtils

# Verify az CLI is present
az version
```

Run the MDM E2E from Git Bash:
```bash
bash infra/scripts/test-mdm-e2e.sh --env dev
# Skip Neo4j check if AuraDB not yet provisioned:
bash infra/scripts/test-mdm-e2e.sh --env dev --skip-neo4j
```

---

## Seed Universe

The warehouse only processes companies in its **tracked universe**. With MDM connected, the universe lives in `mdm_company.tracking_status`. Without MDM, it falls back to DuckDB's `sec_tracked_universe` table (local-only).

```bash
# With MDM configured (preferred):
edgar-warehouse mdm seed-universe
edgar-warehouse mdm seed-universe --limit 500 --tracking-status bootstrap_pending

# Without MDM (legacy / local-only):
edgar-warehouse seed-universe
edgar-warehouse seed-universe --limit 500
```

After seeding, `bootstrap-next` or `bootstrap-full` reads the universe automatically. The warehouse always tries MDM first (if `MDM_DATABASE_URL` is set) and falls back to DuckDB if MDM returns no rows.

---

## Quick Setup Checklist

Follow these steps in order. Each step depends on the previous.

**1. Install dependencies**
```bash
pip install -e ".[s3,snowflake]" && pip install dbt-snowflake
```

**2. Bootstrap AWS Terraform**
```bash
export AWS_PROFILE=aws-admin-prod

# Step 2a: create Terraform state bucket (one-time, per account)
cd infra/terraform/bootstrap-state && terraform init && terraform apply

# Step 2b: provision passive AWS infrastructure
cd infra/terraform/accounts/prod
cp backend.hcl.example backend.hcl            # fill in state bucket name
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform apply

# Step 2c: provision AWS access and runner service roles
cd ../../access/aws/accounts/prod
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform apply
```

**3. Deploy AWS application components**

Use `sec_platform_deployer` for application rollout. Runtime uses service-assumed
roles named `sec_platform_runner_execution`, `sec_platform_runner_task`, and
`sec_platform_runner_step_functions`; do not create a runner IAM user or runner
access keys.

Linux/CI (preferred):
```bash
bash infra/scripts/deploy-aws-application.sh \
  --env prod \
  --aws-profile sec_platform_deployer \
  --aws-region <region> \
  --build-image \
  --publish-mode linux
```

Windows (Git Bash + WSL):
```bash
bash infra/scripts/publish-warehouse-image-via-wsl.sh \
  --aws-profile sec_platform_deployer \
  --aws-region <region> \
  --ecr-repository edgartools-prod-warehouse \
  --image-tag "$(git rev-parse HEAD)" \
  --output-file infra/aws-prod-image.txt

bash infra/scripts/deploy-aws-application.sh \
  --env prod \
  --aws-profile sec_platform_deployer \
  --aws-region <region> \
  --skip-build \
  --image-ref "$(cat infra/aws-prod-image.txt)"
```

**4. Populate AWS Secrets Manager secrets manually**
```bash
# SEC EDGAR identity (required by SEC rate-limiting policy)
aws secretsmanager put-secret-value \
  --secret-id edgartools-prod-edgar-identity \
  --secret-string "Your Name your@email.com"
```

**5. Apply Snowflake Terraform**
```bash
cd infra/terraform/snowflake/accounts/prod
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars  # fill in Snowflake creds
terraform init -backend-config=backend.hcl
terraform apply
```

**6. Run the Snowflake bootstrap (two-pass)**

First pass — creates storage integration and emits `snowflake_storage_external_id`:
```bash
uv run python infra/snowflake/sql/bootstrap_native_pull.py \
  --aws-root infra/terraform/accounts/prod \
  --snowflake-root infra/terraform/snowflake/accounts/prod \
  --connection snowconn \
  --artifact-path infra/snowflake/sql/prod_native_pull_handshake.json
# Note the snowflake_storage_external_id in the artifact JSON
```

Feed external ID back to AWS Terraform and re-apply:
```bash
# Add to infra/terraform/accounts/prod/terraform.tfvars:
# snowflake_storage_external_id = "<id-from-artifact-json>"
cd infra/terraform/accounts/prod && terraform apply
```

Second pass — validates LIST and COPY_HISTORY work end-to-end:
```bash
uv run python infra/snowflake/sql/bootstrap_native_pull.py \
  --aws-root infra/terraform/accounts/prod \
  --snowflake-root infra/terraform/snowflake/accounts/prod \
  --connection snowconn \
  --artifact-path infra/snowflake/sql/prod_native_pull_handshake.json \
  --storage-external-id "<id-from-artifact-json>" \
  --validate-native-pull
```

**7. Run the warehouse bootstrap**
```bash
edgar-warehouse bootstrap
```

This populates the S3 bronze layer with initial parquet exports.

**8. Run dbt to create gold tables**
```bash
cd infra/snowflake/dbt/edgartools_gold
dbt run
```

Gold dynamic tables are created in `EDGARTOOLS.EDGARTOOLS_GOLD`.

**9. Deploy the dashboard**

Production (Snowflake Streamlit — requires Snowflake account access):
```bash
# Deploy via Snowflake UI or snowsql:
# Upload infra/snowflake/streamlit/streamlit_app.py to a Streamlit app
```

External (standalone Streamlit, no Snowflake account required):
```bash
streamlit run examples/dashboard/edgar_universe_dashboard.py
```

---

## Health Check Commands

Run these to verify each layer is operational.

```bash
# Warehouse CLI is installed and reachable
edgar-warehouse --help

# ECR image exists in AWS
aws ecr describe-images --repository-name edgartools-prod-warehouse

# S3 bronze data exists
aws s3 ls s3://<bronze-bucket>/snowflake_exports/ --human-readable | tail -5

# dbt models pass all tests
cd infra/snowflake/dbt/edgartools_gold && dbt test

# Gold layer status (run in Snowflake worksheet or snowsql)
SELECT * FROM EDGARTOOLS.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS LIMIT 10;

# MDM table row counts
edgar-warehouse mdm counts

# MDM connectivity
edgar-warehouse mdm check-connectivity --neo4j
```

---

## Common Failure Patterns

| Symptom | Likely Cause | Fix |
|---|---|---|
| Docker push fails on Windows | `linux` mode requires a Linux runner | Use `publish-warehouse-image-via-wsl.sh` instead |
| Snowflake bootstrap fails on storage integration | External ID not fed back to AWS Terraform | Two-pass bootstrap: capture external ID, re-apply AWS TF (`storage` module), re-run driver |
| `dbt run` fails with `CREATE DYNAMIC TABLE` error | Snowflake Standard edition | Dynamic tables require Enterprise+ edition |
| `export_root_url` mismatch error at runtime | Missing trailing slash on S3 path | Add `/` at end of `snowflake_exports/` path in config |
| `SNOWFLAKE_ACCOUNT not set` error | Default removed for security | Set `export SNOWFLAKE_ACCOUNT=ORGNAME-ACCOUNTNAME` before running |
| dbt target lag slow on first query | `TARGET_LAG = DOWNSTREAM` setting | Normal — refreshes on query; run `dbt run` first to pre-warm |
| `terraform destroy` fails on prod bronze bucket | `prevent_destroy = true` on storage | By design — prod storage is protected; remove lifecycle block manually only if intentionally tearing down |
| `MDM_DATABASE_URL not set` when running `edgar-warehouse mdm ...` | Env var missing | `export MDM_DATABASE_URL=postgresql://...` before running MDM commands |
| `edgar-warehouse mdm seed-universe` 403 from SEC | Missing `EDGAR_IDENTITY` env var | `export EDGAR_IDENTITY="Your Name your@email.com"` |
| `edgar-warehouse bootstrap` fails with "requires seeded tracked universe" | Neither MDM nor DuckDB has universe data | Run `edgar-warehouse mdm seed-universe` (with MDM) or `edgar-warehouse seed-universe` (without MDM) first |
| `sqlcmd` not found on Windows in `run-neo4j-e2e.sh` | MSSQL tools not installed | `winget install Microsoft.SQLCmdUtils` |

---

## edgartools Dependency

The `edgartools` PyPI package is a required runtime dependency of this platform.

- **Install**: included in `pip install -e ".[s3,snowflake]"` — do not install separately unless pinning a version
- **Key import**: `edgar_warehouse/parsers/ownership.py` uses `from edgar.ownership import Ownership`
- **Batch scripts**: all files in `scripts/batch/*.py` import from `edgar.*` and require `edgartools` at runtime
- **External dashboard**: `examples/dashboard/edgar_universe_dashboard.py` does NOT require `edgartools` — it reads from Snowflake gold tables directly

If `edgartools` is not importable, the warehouse ETL and batch scripts will fail at import time with a clear `ModuleNotFoundError`.
