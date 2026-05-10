# EdgarTools Platform

This repo is the full data platform built on top of the `edgartools` PyPI package. It extracts SEC EDGAR filings data via an ETL runtime, stages Parquet files in S3, loads them into Snowflake, and transforms them into production-ready dynamic tables consumed by a Streamlit dashboard. The platform is designed to track a universe of public companies and investment advisers across all major SEC form types.

## Quick Navigation

| Need | Location |
|------|----------|
| ETL runtime (form parsing, S3 writes) | `edgar_warehouse/runtime.py` |
| Silver-layer transformations | `edgar_warehouse/silver.py` |
| Gold-layer aggregations (Python) | `edgar_warehouse/gold.py` |
| Ownership / Form 3-4-5 parser | `edgar_warehouse/parsers/ownership.py` |
| ADV parser (investment advisers) | `edgar_warehouse/parsers/adv.py` |
| CLI entry point | `edgar_warehouse/cli.py` |
| Batch scripts per form type | `scripts/batch/` |
| dbt gold models (8 dynamic tables) | `infra/snowflake/dbt/edgartools_gold/models/gold/` |
| Snowflake bootstrap SQL | `infra/snowflake/sql/bootstrap/` |
| Streamlit-in-Snowflake dashboard | `infra/snowflake/streamlit/streamlit_app.py` |
| Standalone Streamlit dashboard | `examples/dashboard/edgar_universe_dashboard.py` |
| AWS Terraform (prod) | `infra/terraform/accounts/prod/` |
| Snowflake Terraform (prod) | `infra/terraform/snowflake/accounts/prod/` |
| Docker / ECR publish scripts | `infra/scripts/` |

## Architecture

```
SEC EDGAR API
      |
      v
edgar-warehouse CLI  (edgar_warehouse/runtime.py)
      |
      v
S3 Parquet (bronze)
      |
      v
Snowflake EDGARTOOLS_SOURCE  <-- native S3 pull via bootstrap SQL
      |
      v
dbt (infra/snowflake/dbt/edgartools_gold/)
      |
      v
EDGARTOOLS_GOLD  (8 dynamic tables)
      |
      v
Streamlit dashboard  (infra/snowflake/streamlit/  OR  examples/dashboard/)
```

## Data Layer Definitions

| Layer | Location | Description |
|-------|----------|-------------|
| **Bronze** | S3 (`s3://<bucket>/`) | Raw Parquet files written by `edgar-warehouse`. One file per filing/entity, partitioned by form type and date. Never mutated. |
| **Source** | Snowflake `EDGARTOOLS_SOURCE` | External stage + tables auto-refreshed from S3 via Snowflake native S3 pull (bootstrap SQL). Read-only raw layer. |
| **Silver** | `edgar_warehouse/silver.py` | Cleaned, typed, deduplicated records. Applied in the warehouse runtime before S3 write; also used for ad-hoc re-processing. |
| **Gold** | `EDGARTOOLS_GOLD` (dbt dynamic tables) | Business-ready tables: `company`, `ownership_holdings`, `ownership_activity`, `filing_detail`, `filing_activity`, `adviser_disclosures`, `adviser_offices`, `private_funds`, `ticker_reference`, `edgartools_gold_status`. Refreshed on a Snowflake-managed schedule. |

## edgartools Dependency

The platform depends on the `edgartools` PyPI package (`edgartools>=5.29.0`). It is **not** a local path dependency — install from PyPI.

## SEC data idempotency

SEC filing artifacts are treated as additive and immutable after they have been
captured. Warehouse loaders must skip already loaded SEC files by default and
only re-fetch when an operator passes an explicit `--force` repair flag.

## Long-load 5-whys

1. Why did warehouse loads take too long? Batched Step Functions work repeated
   downstream publish work instead of separating capture, transform, and serving
   refresh phases.
2. Why was downstream work repeated? `bootstrap-batch` was treated as a
   gold-affecting command, so each batch could build gold tables and emit a
   Snowflake run manifest.
3. Why was that expensive? Gold export and Snowflake refresh operate on the
   whole warehouse state; repeating them per batch multiplies I/O and refresh
   waits.
4. Why was monitoring weak? Bronze, silver, gold, Snowflake load, and dynamic
   table refresh did not have one operator-facing timeline.
5. Why did it become hard to reason about? Distributed ECS tasks use local
   DuckDB state and then publish `silver/sec/silver.duckdb`; concurrent batch
   tasks can race unless silver is centralized into a single all-at-once phase.

Target pipeline shape:
- Populate bronze individually and make each CIK or batch progress visible.
- Run silver once for the completed bronze run.
- Run gold once after silver completes.
- Emit structured progress events and surface Snowflake load, task, copy, and
  dynamic-table refresh state in the dashboard.

Key import pattern (do not change without checking the edgartools changelog):

```python
# edgar_warehouse/parsers/ownership.py
from edgar.ownership import Ownership

parsed = Ownership.from_xml(content)
```

Other edgartools surfaces used:
- `edgar.filing` — filing metadata and document fetching in `runtime.py`
- `edgar.entity` — company/entity resolution
- `edgar.xbrl` — financial statement parsing in batch scripts

When the `edgartools` version is bumped, run the batch scripts in `scripts/batch/` to smoke-test parsing.

## Development Commands

> **Tooling:** always use `uv` for Python dependency management and Python CLI
> execution in this repo. The lockfile is `uv.lock`; never invoke bare `pip` or
> bare `dbt` from repo workflows. Use `uv sync` for project deps, `uv pip
> install` for deliberate one-off installs, and `uv run --with <package>` when a
> deploy needs a transient tool such as `dbt-snowflake`.
>
> **Docker runtime:** on macOS use Colima as the local Docker daemon. On Windows
> use Docker Desktop. The default macOS fast-feedback path is Colima plus plain
> `docker build`/`docker push`; `docker buildx` is supported when it is
> measurably faster or when using Linux/Windows CI registry cache. Do not
> introduce another container build/runtime stack.

```bash
# Install project deps (uses uv.lock)
uv sync --extra s3 --extra snowflake

# Warehouse CLI
edgar-warehouse --help
edgar-warehouse bootstrap --tracking-status-filter active

# dbt (from dbt project root)
cd infra/snowflake/dbt/edgartools_gold
uv run --with dbt-snowflake dbt compile  # validate models without executing
uv run --with dbt-snowflake dbt run      # create/refresh gold dynamic tables in Snowflake
uv run --with dbt-snowflake dbt test     # run data quality tests

# Terraform — AWS infra
cd infra/terraform/accounts/prod
terraform plan
terraform apply

# Terraform — Snowflake infra
cd infra/terraform/snowflake/accounts/prod
terraform plan
terraform apply

# AWS-only Snowflake native-pull deploy (dev)
# Requires SnowCLI connection edgartools-dev and keeps Snowflake secrets out of repo files.
bash infra/scripts/deploy-snowflake-stack.sh \
  --env dev \
  --snow-connection edgartools-dev \
  --run-validation \
  --run-dbt

# Docker image publish (Linux / CI with buildx registry cache)
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region <region> \
  --ecr-repository edgartools-dev-warehouse \
  --role warehouse \
  --image-tag $(git rev-parse HEAD) \
  --mode buildx \
  --cache-tag buildcache \
  --also-tag dev

# Docker image publish (macOS Colima fast feedback)
colima start
export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region <region> \
  --ecr-repository edgartools-dev-warehouse \
  --role warehouse \
  --image-tag $(git rev-parse HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# Standalone dashboard (local)
cd examples/dashboard
uv pip install -r requirements.txt
streamlit run edgar_universe_dashboard.py
```

## Image management

Use AWS ECR only for deployable images. Do not add Azure Container Registry,
Azure SDK, ODBC, or Azure deployment steps back into this repo unless the
platform architecture changes explicitly.

| Image | Dockerfile | Installs | Runs |
|-------|------------|----------|------|
| `edgartools-dev-warehouse-deps` | `Dockerfile.warehouse-deps` | locked `.[s3]` deps via `uv` | dependency base image |
| `edgartools-dev-warehouse` | `Dockerfile` | source copy on warehouse deps | warehouse ECS tasks |
| `edgartools-dev-mdm-deps` | `Dockerfile.mdm-deps` | locked `.[s3,mdm-runtime]` deps via `uv`; no API/admin packages | MDM Step Functions dependency base image |
| `edgartools-dev-mdm` | `Dockerfile.mdm-neo4j` | source copy on MDM deps | MDM ECS tasks/API |

**Tagging strategy**

| Tag | Meaning |
|-----|---------|
| `:dev` | Mutable latest dev image |
| `:sha-<hash>` | Immutable rollback/audit image |
| `:prod` | Manually promoted production image |

**Manual AWS build and deploy**

```bash
# Build/push warehouse with macOS Colima and AWS ECR.
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-warehouse \
  --role warehouse \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# Build/push MDM separately when MDM code/deps changed.
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-mdm \
  --role mdm \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# Deploy AWS ECS/Step Functions with an existing image reference.
bash infra/scripts/deploy-aws-application.sh \
  --env dev \
  --skip-build \
  --image-ref <warehouse-image-digest-ref> \
  --mdm-image-ref <mdm-image-digest-ref> \
  --enable-mdm
```

**Rollback to a previous SHA**

```bash
ECR=<account>.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-warehouse
SHA=sha-abc1234
docker pull $ECR:$SHA
docker tag  $ECR:$SHA $ECR:dev
docker push $ECR:dev
```

## Key Large Files (Read in Chunks)

These files exceed 30 KB. When modifying them, read section by section rather than all at once:

| File | Size | Contents |
|------|------|----------|
| `edgar_warehouse/runtime.py` | ~92 KB | Core ETL loop, form dispatch, S3 writes |
| `edgar_warehouse/silver.py` | ~78 KB | Record cleaning and transformation logic |
| `edgar_warehouse/gold.py` | ~39 KB | Python-side gold aggregations |

## Setup

See `docs/runbook.md` for end-to-end environment setup including AWS credentials, Snowflake keypair auth, S3 bucket provisioning, dbt profiles configuration, and first-run bootstrap.
