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

**2. Bootstrap AWS Terraform (four sub-modules in order)**
```bash
cd infra/terraform/accounts/bootstrap-state && terraform init && terraform apply
cd ../network                                && terraform init && terraform apply
cd ../storage                                && terraform init && terraform apply
cd ../warehouse_runtime                      && terraform init && terraform apply
```

**3. Build and push Docker image**

Linux/macOS:
```bash
scripts/publish-warehouse-image.sh
```

Windows (requires WSL):
```bash
scripts/publish-warehouse-image-via-wsl.sh
```

**4. Update container image reference and re-apply**
```bash
# Copy the ECR image URI printed by step 3, then:
# Edit infra/terraform/accounts/warehouse_runtime/terraform.tfvars
# Set: container_image = "<ECR_URI>"
cd infra/terraform/accounts/warehouse_runtime && terraform apply
```

**5. Populate AWS Secrets Manager secrets**
- `edgar-identity` — SEC EDGAR identity header (name + email)
- `runner-credentials` — Snowflake credentials used by the warehouse runner

**6. Apply Snowflake Terraform**
```bash
cd infra/terraform/snowflake && terraform init && terraform apply
```

**7. Run the Snowflake bootstrap (two-pass)**

First pass — creates storage integration and emits external ID:
```bash
python infra/snowflake/sql/bootstrap_native_pull.py
# Note the STORAGE_AWS_EXTERNAL_ID printed to stdout
```

Feed external ID back to AWS Terraform:
```bash
# Edit infra/terraform/accounts/storage/terraform.tfvars
# Set: snowflake_external_id = "<EXTERNAL_ID>"
cd infra/terraform/accounts/storage && terraform apply
```

Second pass — completes bootstrap now that trust policy is in place:
```bash
python infra/snowflake/sql/bootstrap_native_pull.py
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
