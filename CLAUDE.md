# EdgarTools Platform

This repo is the full data platform built on top of the `edgartools` PyPI package. It extracts SEC EDGAR filings data via an ETL runtime, stages Parquet files in S3, loads them into Snowflake, and transforms them into production-ready dynamic tables consumed by a Streamlit dashboard. The platform is designed to track a universe of public companies and investment advisers across all major SEC form types.

## Parallel Agent Workstreams

Claude and Codex may work on this repository independently, but they must not share an uncoordinated edit surface.

- Treat current Codex work as protected unless the user explicitly hands it off.
- Prefer separate git worktrees or branches for concurrent Claude and Codex work.
- Use separate GSD workstream directories under `.planning/workstreams/<name>/`; do not edit another runtime's active workstream files.
- Before editing, run `git status --short` and inspect `.planning/active-workstream` when present.
- Avoid overlapping source files, Terraform roots, generated application JSON, and planning artifacts across runtimes unless the user assigns the same task to both.
- If overlap is unavoidable, stop and ask for an ownership decision instead of merging assumptions.
- Do not overwrite, revert, stage, or commit changes created by the other runtime unless explicitly instructed.

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

## Long-load 5-whys (resolved)

**Problem:** Loading 100 companies sequentially took 30–90 minutes.

1. `bootstrap-next` fetches all 100 CIKs sequentially — no parallelism at the CIK level.
2. Each CIK requires N SEC API calls (submissions.json + all pagination files). A well-filed
   company has 50+ pagination files × 200–500 ms = 10–25 s per company.
3. `bootstrap-batch` (Step Functions Distributed Map) was in `GOLD_AFFECTING_COMMANDS`, so
   every parallel batch task rebuilt gold tables and uploaded silver.duckdb — work that
   operates on the whole warehouse state and multiplies I/O by batch count.
4. The three phases (bronze, MDM, gold) were mixed into a single command, preventing the
   MDM entity resolution + Neo4j sync from running against the complete silver dataset.
5. There was no single Step Function that encoded the correct sequence: parallel bronze
   → MDM in bulk → gold once.

**Resolution:** `bootstrap-batch` removed from `GOLD_AFFECTING_COMMANDS`. New `gold-refresh`
command builds gold once. New `load_history` Step Function chains all four phases correctly.

## Phased Pipeline (use this for all bootstraps ≥10 companies)

`load_history` is the canonical way to load companies at scale. It runs in four
sequential stages, each optimised for its workload:

```
Stage 1 — Bronze + Silver (parallel, N×10 concurrent ECS tasks)
  seed-universe  →  bootstrap-batch ×N  (MaxConcurrency=10)
  • Each batch: fetch SEC submissions + pagination → S3 bronze, parse → silver DuckDB
  • NO gold build per batch (bootstrap-batch is NOT in GOLD_AFFECTING_COMMANDS)

Stage 2 — MDM entity resolution (sequential Step Functions)
  mdm-run  →  mdm-backfill-relationships  →  mdm-sync-graph  →  mdm-verify-graph
  • Runs after ALL batches complete so entity resolution sees the full silver dataset
  • Derives IS_INSIDER, MANAGES_FUND etc. and syncs to Neo4j

Stage 3 — Gold refresh (single ECS task)
  gold-refresh
  • Reads complete silver DuckDB, builds all 9 gold tables, writes Snowflake export manifests
  • SNOWFLAKE_RUN_MANIFEST_TASK picks up the manifest and refreshes EDGARTOOLS_GOLD within 1 min
```

**When to use what:**

| Scenario | Command / State Machine |
|----------|------------------------|
| Load 10+ companies (recommended) | `load_history` Step Function |
| Single company debug/resync | `targeted_resync` Step Function |
| Rebuild gold from existing silver | `gold_refresh` Step Function |
| Recent filings only (fast) | `bootstrap` Step Function |
| Daily incremental (ongoing) | `daily_incremental` Step Function |

**Running `load_history` via Step Functions:**

```bash
aws stepfunctions start-execution \
  --region us-east-1 \
  --state-machine-arn arn:aws:states:us-east-1:077127448006:stateMachine:edgartools-dev-load-history \
  --name "load-history-$(date +%s)" \
  --input '{}'
# Runs ~15 min for 100 companies (vs 30-90 min sequential)
# Monitor: aws stepfunctions describe-execution --execution-arn <arn> --query status
```

**Do NOT run `bootstrap-next` locally for large batches** — it is sequential and cannot reach
MDM Postgres (private VPC). Reserve it for single-company ad-hoc loads with explicit `--cik-list`.

**Key invariants (do not break):**
- `bootstrap-batch` must NOT be in `GOLD_AFFECTING_COMMANDS` — enforced in `warehouse_orchestrator.py:79`
- `gold-refresh` must be in `GOLD_AFFECTING_COMMANDS` — it is the sole gold builder in the phased pipeline
- `SNOWFLAKE_RUN_MANIFEST_TASK` must be STARTED in `EDGARTOOLS_GOLD` — verify with
  `snow sql --connection edgartools-dev -q "SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK'"`
- `silver_mdm_gold` map MUST pass `--artifact-policy skip` to `bootstrap-batch` — without it
  the pipeline makes thousands of SEC API calls (fetching ownership XMLs) even though the
  purpose of this pipeline is to reprocess already-loaded bronze with zero SEC calls.
  5-why root cause: the artifact pipeline is a separate SEC fetch pass; "no SEC calls" must
  be encoded as a flag, not assumed from the pipeline name.
- `BOOTSTRAP_BATCH_CONCURRENCY` recommended range: **2–5** concurrent ECS tasks. Current
  default is 3 (already within the recommended range). Values below 2 are not recommended
  for production — throughput is too low. Values above 5 risk triggering SEC rate limiting:
  at 5 tasks × ~9 req/sec theoretical max = ~45 req/sec, well above SEC's 10 req/sec per-IP
  limit without stagger mitigation. The in-process rate limiter in `sec_client.py` (9 req/sec
  per task) enforces per-task throttling but does not coordinate across ECS tasks.

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
>
> **One-time Colima setup (macOS):** Docker 29+ in Colima defaults to the
> containerd image-store snapshotter, which the legacy `docker build` path
> cannot use. Run this once per workstation (and after any Colima/Docker
> upgrade) to disable the snapshotter and provision adequate CPU/RAM/disk:
> ```bash
> bash infra/scripts/setup-colima.sh           # apply + restart Colima
> bash infra/scripts/setup-colima.sh --verify  # check current state
> ```
> `publish-warehouse-image.sh` fails fast with a pointer to this script if
> the daemon is misconfigured.

```bash
# Required env vars before any warehouse command
export EDGAR_IDENTITY="EdgarTools Platform thepaulananth@gmail.com"   # SEC User-Agent; must contain email
export WAREHOUSE_RUNTIME_MODE="bronze_capture"
export WAREHOUSE_BRONZE_ROOT="s3://edgartools-dev-bronze-077127448006/warehouse/bronze"
export WAREHOUSE_STORAGE_ROOT="s3://edgartools-dev-warehouse-077127448006/warehouse"
export SERVING_EXPORT_ROOT="s3://edgartools-dev-snowflake-export-077127448006/warehouse/artifacts/snowflake_exports/"
export MDM_DATABASE_URL="postgresql://postgres:test@localhost:5432/mdm"  # local Colima postgres
export AWS_DEFAULT_REGION=us-east-1  # infra is us-east-1, not the default us-east-2

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

# Docker image publish (macOS Colima — see "Manual AWS build and deploy" below for the full recipe)
colima start
export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    077127448006.dkr.ecr.us-east-1.amazonaws.com
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-warehouse \
  --role warehouse \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
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

**Manual AWS build and deploy — complete recipe (macOS Colima)**

CI (GitHub Actions `build-images.yml`) runs this automatically on every push
to `main`. Use the steps below only for ad-hoc builds or when CI is unavailable.

```bash
# 1. Start Colima and point Docker CLI at it (do once per terminal session).
colima start
export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock

# 2. Authenticate to ECR (token valid for 12 h).
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    077127448006.dkr.ecr.us-east-1.amazonaws.com

# NOTE: ECR repositories must have MUTABLE tags for :dev to be overwritten.
# If you see "tag is immutable" on push, run once per affected repo:
#   aws ecr put-image-tag-mutability --region us-east-1 \
#     --repository-name edgartools-dev-warehouse --image-tag-mutability MUTABLE
#   aws ecr put-image-tag-mutability --region us-east-1 \
#     --repository-name edgartools-dev-mdm --image-tag-mutability MUTABLE

# 3a. Build and push the warehouse image.
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-warehouse \
  --role warehouse \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# 3b. Build and push the MDM image (when edgar_warehouse/mdm/** changed).
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-mdm \
  --role mdm \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# 4. Capture the digest refs that step 3 printed (used for deploy).
WAREHOUSE_REF=$(aws ecr describe-images \
  --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageDigest" \
  --output text | xargs -I{} echo "077127448006.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-warehouse@{}")
MDM_REF=$(aws ecr describe-images \
  --region us-east-1 \
  --repository-name edgartools-dev-mdm \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageDigest" \
  --output text | xargs -I{} echo "077127448006.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-mdm@{}")

# 5. Deploy ECS task definitions and Step Functions state machines.
bash infra/scripts/deploy-aws-application.sh \
  --env dev \
  --skip-build \
  --image-ref "$WAREHOUSE_REF" \
  --mdm-image-ref "$MDM_REF" \
  --enable-mdm
```

**If publish-warehouse-image.sh fails with a cache layer error (Colima cache corruption)**

```bash
# Look up current deps tags from ECR (avoids stale hardcoded values)
WH_DEPS=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-warehouse-deps \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]" --output text)
MDM_DEPS=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-mdm-deps \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]" --output text)

ECR="077127448006.dkr.ecr.us-east-1.amazonaws.com"
SHA_TAG="sha-$(git rev-parse --short=12 HEAD)"

# Rebuild warehouse directly
docker pull "${ECR}/edgartools-dev-warehouse-deps:${WH_DEPS}"
docker build --platform linux/amd64 \
  --build-arg "DEPENDENCY_IMAGE=${ECR}/edgartools-dev-warehouse-deps:${WH_DEPS}" \
  -f Dockerfile -t "${ECR}/edgartools-dev-warehouse:${SHA_TAG}" -t "${ECR}/edgartools-dev-warehouse:dev" .
docker push "${ECR}/edgartools-dev-warehouse:${SHA_TAG}"
docker push "${ECR}/edgartools-dev-warehouse:dev"

# Rebuild MDM directly
docker pull "${ECR}/edgartools-dev-mdm-deps:${MDM_DEPS}"
docker build --platform linux/amd64 \
  --build-arg "DEPENDENCY_IMAGE=${ECR}/edgartools-dev-mdm-deps:${MDM_DEPS}" \
  -f Dockerfile.mdm-neo4j -t "${ECR}/edgartools-dev-mdm:${SHA_TAG}" -t "${ECR}/edgartools-dev-mdm:dev" .
docker push "${ECR}/edgartools-dev-mdm:${SHA_TAG}"
docker push "${ECR}/edgartools-dev-mdm:dev"
```

**When to rebuild which image**

| Changed paths | Rebuild |
|---------------|---------|
| `edgar_warehouse/**` (excluding `edgar_warehouse/mdm/`) | warehouse only |
| `edgar_warehouse/mdm/**` | MDM only |
| Both (e.g. `orchestrator.py` + `mdm/cli.py`) | both |
| `Dockerfile` / `Dockerfile.warehouse-deps` | warehouse (+ deps if lock changed) |
| `Dockerfile.mdm-neo4j` / `Dockerfile.mdm-deps` | MDM (+ deps if lock changed) |
| `uv.lock` | deps images for both — run without `--skip-build` |

**Clean up local images before a build (run this first every time)**

Colima accumulates stale images fast — old SHA tags, debug tags, superseded deps layers. Clean before building to avoid cache confusion and reclaim disk.

```bash
export DOCKER_HOST=unix://$HOME/.colima/default/docker.sock

# 1. Show what's on disk
docker system df
docker images --format "{{.Repository}}:{{.Tag}}\t{{.Size}}"

# 2. Remove dangling (untagged) images and unused build cache
docker image prune -f
docker builder prune -f

# 3. Remove old named images — keep only :dev and the latest :sha-* per repo.
#    List old tags from the output above and delete explicitly:
ECR="077127448006.dkr.ecr.us-east-1.amazonaws.com"
docker rmi \
  "${ECR}/edgartools-dev-warehouse:sha-<old>" \
  "${ECR}/edgartools-dev-mdm:sha-<old>" \
  "${ECR}/edgartools-dev-warehouse-deps:deps-<old>" \
  # ... add any debug/ad-hoc tags (routerfix-*, hydratefix-*, etc.)

# 4. Nuclear option — wipe everything (forces full re-pull of base + deps on next build)
docker system prune -af   # WARNING: removes ALL local images, not just ours
```

**What to keep:**
- `:dev` tag for each repo — used as build cache source (`--cache-from-tag dev`)
- Latest `:sha-<hash>` per repo — rollback anchor
- `:deps-<hash>` for warehouse-deps and mdm-deps — slow to rebuild; only remove if `uv.lock` changed
- `public.ecr.aws/docker/library/python:3.12-slim-bookworm` — base layer cache

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
