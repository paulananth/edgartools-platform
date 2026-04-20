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

---

## Quick Setup Checklist

Follow these steps in order. Each step depends on the previous.

**1. Install dependencies**
```bash
pip install -e ".[s3,snowflake]" && pip install dbt-snowflake
```

**2. Bootstrap AWS Terraform**
```bash
# Step 2a: create Terraform state bucket (one-time, per account)
cd infra/terraform/bootstrap-state && terraform init && terraform apply

# Step 2b: provision AWS infrastructure
cd infra/terraform/accounts/prod
cp backend.hcl.example backend.hcl            # fill in state bucket name
cp terraform.tfvars.example terraform.tfvars  # fill in edgar_identity_value
terraform init -backend-config=backend.hcl
terraform apply -target module.network_runtime
terraform apply -target module.storage
# (pause — build and push Docker image in step 3, then continue)
```

**3. Build and push Docker image**

Linux/CI (preferred):
```bash
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region <region> \
  --ecr-repository edgartools-prod-warehouse \
  --image-tag $(git rev-parse HEAD) \
  --mode linux
```

Windows (Git Bash + WSL):
```bash
bash infra/scripts/publish-warehouse-image-via-wsl.sh \
  --aws-region <region> \
  --ecr-repository edgartools-prod-warehouse \
  --image-tag $(git rev-parse HEAD)
```

**4. Complete AWS Terraform with the verified image digest**
```bash
# Add the @digest output from step 3 to terraform.tfvars:
# container_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-warehouse@sha256:..."

cd infra/terraform/accounts/prod
terraform apply -target module.runtime   # provisions ECS + Step Functions
terraform apply                          # full apply
```

**5. Populate AWS Secrets Manager secrets manually**
```bash
# SEC EDGAR identity (required by SEC rate-limiting policy)
aws secretsmanager put-secret-value \
  --secret-id edgartools-prod-edgar-identity \
  --secret-string "Your Name your@email.com"

# Runner IAM credentials
aws iam create-access-key --user-name edgartools-prod-runner
# Put the keys into edgartools-prod-runner-credentials secret
```

**6. Apply Snowflake Terraform**
```bash
cd infra/terraform/snowflake/accounts/prod
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars  # fill in Snowflake creds
terraform init -backend-config=backend.hcl
terraform apply
```

**7. Run the Snowflake bootstrap (two-pass)**

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

**8. Run the warehouse bootstrap**
```bash
edgar-warehouse bootstrap
```

This populates the S3 bronze layer with initial parquet exports.

**9. Run dbt to create gold tables**
```bash
cd infra/snowflake/dbt/edgartools_gold
dbt run
```

Gold dynamic tables are created in `EDGARTOOLS.EDGARTOOLS_GOLD`.

**10. Deploy the dashboard**

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

---

## edgartools Dependency

The `edgartools` PyPI package is a required runtime dependency of this platform.

- **Install**: included in `pip install -e ".[s3,snowflake]"` — do not install separately unless pinning a version
- **Key import**: `edgar_warehouse/parsers/ownership.py` uses `from edgar.ownership import Ownership`
- **Batch scripts**: all files in `scripts/batch/*.py` import from `edgar.*` and require `edgartools` at runtime
- **External dashboard**: `examples/dashboard/edgar_universe_dashboard.py` does NOT require `edgartools` — it reads from Snowflake gold tables directly

If `edgartools` is not importable, the warehouse ETL and batch scripts will fail at import time with a clear `ModuleNotFoundError`.
