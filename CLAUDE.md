# EdgarTools Platform

This repo is the full data platform built on top of the `edgartools` PyPI package. It extracts SEC EDGAR filings data via an ETL runtime, stages Parquet files in S3, loads them into Snowflake, and transforms them into production-ready dynamic tables consumed by a Streamlit dashboard. The platform is designed to track a universe of public companies and investment advisers across all major SEC form types.

## AWS account map (READ THIS before running any AWS command)

**The platform lives in AWS account `690839588395` (current/active).** All `edgartools-*`
resources, ECR images, ECS clusters, and Terraform state should target `690839588395`.

**Account `077127448006` is DECOMMISSIONED (emptied 2026-07-11, `claude/destroy-old-account`).**
Everything was migrated to `690839588395` first, then the old account was torn down with
`infra/scripts/destroy-aws-complete.sh --env all` plus an all-regions + tagging-API sweep:
all S3 buckets (incl. the 198 GB warehouse and both `*-tfstate` buckets), 45 Step Functions,
ECS, ECR, 13 secrets, all IAM roles, dev+prod VPCs, 17 default VPCs, and 280 ECS task
definitions. Verified zero billable resources remaining.
- **Final closure is a ROOT action.** The `cli-access` IAM user in `077127448006` *cannot*
  close the account — closure/suspension must be done via root sign-in or the AWS
  Organizations management account. `cli-access`, 2 `PendingDeletion` KMS keys (auto-delete
  2026-07-18), INACTIVE ECS cluster tombstones, and the payment-instrument were left in place
  and are reaped automatically when the account is closed.
- **State backups** (the only surviving record of the destroyed account) live at
  `~/edgartools-077-tfstate-backups-FINAL` and `infra/.aws-tfstate-backups/`.
- Do NOT reprovision anything into `077127448006`. If an old ARN/bucket/`aws-prod-application.json`
  still references `077127448006`, it is stale — the live target is `690839588395`.

## Parallel Agent Workstreams

Claude and Codex may work on this repository independently, but they must not share an uncoordinated edit surface.

- **HARD RULE: Claude and Codex must NEVER commit to the same branch.** Each
  runtime works on its own dedicated branch (or worktree). If you find
  yourself about to commit and `git log -1` shows a commit authored by the
  other runtime's current work that you did not expect, STOP — do not
  commit — and ask the user how to proceed (e.g. branch off, rebase onto a
  new branch, or hand off).
- Branch naming convention: prefix branches with the owning runtime, e.g.
  `claude/<topic>` or `codex/<topic>`. Before starting work or committing,
  run `git branch --show-current` — if the current branch is prefixed for
  the *other* runtime (or is a shared branch like `main`/`codex/main-sync`
  that the other runtime is actively using), create/check out your own
  branch (or worktree) before making any commits.
- Treat current Codex work as protected unless the user explicitly hands it off.
- Use separate GSD workstream directories under `.planning/workstreams/<name>/`; do not edit another runtime's active workstream files.
- Before editing, run `git status --short` and `git log -1` and inspect
  `.planning/active-workstream` when present.
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
| MDM graph (Snowflake-hosted, NOT external Neo4j) | `edgar_warehouse/mdm/graph_readonly.py`, `mdm sync-graph`/`mdm verify-graph` CLI, `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` |
| Operator MDM/graph review dashboard | `examples/mdm_graph_dashboard/` |
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

## Debugging discipline: 5-whys

When fixing **any** error (CLI failures, ECS task crashes, CI failures, data
bugs, infra errors), do a 5-whys root-cause pass before applying a fix:

1. State the observed symptom (error message, exit code, wrong output).
2. Ask "why" repeatedly (3-5 times) until you reach a root cause, not just
   the proximate trigger.
3. Apply the fix at the root cause, not just the symptom.
4. If the issue is non-trivial or likely to recur, document the chain
   (problem → whys → resolution) in this file or `TODOS.md` so future
   sessions don't re-debug it from scratch.

The "Long-load 5-whys (resolved)" section below is the template for this —
follow that format for new entries.

## Long-load 5-whys (resolved)

**Problem:** Loading 100 companies sequentially took 30–90 minutes.

1. `bootstrap-next` fetches all 100 CIKs sequentially — no parallelism at the CIK level.
2. Each CIK requires N SEC API calls (submissions.json + all pagination files). A well-filed
   company has 50+ pagination files × 200–500 ms = 10–25 s per company.
3. `bootstrap-batch` (Step Functions Distributed Map) was in `GOLD_AFFECTING_COMMANDS`, so
   every parallel batch task rebuilt gold tables and uploaded silver.duckdb — work that
   operates on the whole warehouse state and multiplies I/O by batch count.
4. The three phases (bronze, MDM, gold) were mixed into a single command, preventing the
   MDM entity resolution + graph sync (Snowflake-hosted Neo4j Graph Analytics Native App —
   see "Graph storage" note below) from running against the complete silver dataset.
5. There was no single Step Function that encoded the correct sequence: parallel bronze
   → MDM in bulk → gold once.

**Resolution:** `bootstrap-batch` removed from `GOLD_AFFECTING_COMMANDS`. New `gold-refresh`
command builds gold once. New `load_history` Step Function chains all four phases correctly.

## Artifact-throttle 5-whys (resolved 2026-07-12)

**Problem:** A 20-CIK `load_history` re-run spent ~20+ min (est. ~93 min floor) in
`filing_artifact_pipeline` over 5,583 accessions with flat ~416 MiB memory, looking like it
was re-loading immutable, already-captured SEC data.

1. Why iterate 5,583 accessions? Per-window `bootstrap-next` runs with the default
   `--artifact-policy all_attachments`; `_configured_parser_accessions` selects every
   ownership/ADV-form accession in the window (heavy insiders → 5,583 Form 3/4/5).
2. Why revisit immutable data? Idempotency lives at the **download** layer, not the
   **iteration** layer — `fetch_filing_artifacts` returns cached artifacts with no SEC call
   when `existing_rows and not force`, but the orchestrator loop still visits every accession
   to check the cache. No "universe already captured → skip the pass" short-circuit.
3. Why does checking cached accessions cost ~93 min? The loop ran
   `time.sleep(WAREHOUSE_ARTIFACT_REQUEST_DELAY)` (default **1.0s**) after **every**
   accession, **unconditionally, even on a pure cache hit**. 5,583 × 1s ≈ 93 min of no-op
   throttle. **Root cause:** the SEC rate-limit sleep was paid on the idempotent no-op path,
   not just on real network fetches.

**Resolution (root-cause fix):** `fetch_filing_artifacts` now returns `network_fetches`
(count of real SEC round-trips: edgartools `get_filing` + each `download_bytes`); the
orchestrator loop throttles only when `network_fetches > 0`. Cache hits (immutable,
already-captured artifacts) return `network_fetches=0` and skip the sleep, so re-runs against
loaded bronze no longer pay the ~93-min dead-time throttle while new filings are still fully
rate-limited. Locked in by `tests/unit/test_loader_idempotency.py` (`network_fetches` = 0 on
cache hit, 1 on fetch). NOTE: takes effect only after a warehouse image rebuild + deploy.

## AWS teardown 5-whys (resolved 2026-07-11)

`destroy-aws-complete.sh` is authored/tested for Linux/CI and failed three times on macOS
(Colima host, default bash 3.2, GNU-vs-BSD tool differences) during the `077127448006`
decommission. Fixes are in the script; re-record here if they regress.

**Problem 1 — `mktemp: mkstemp failed ... File exists`, aborted at the first S3 bucket.**
1. `mktemp "${TMP_DIR}/s3-versions-XXXXXX.json"` failed. 2. BSD/macOS `mktemp` only substitutes
*trailing* `X`s; the `.json` suffix after the X's makes the template literal. 3. Written for GNU
`mktemp` (substitutes X's anywhere). 4. `set -e` aborts the whole run. **Root cause:** GNU-vs-BSD
`mktemp`. **Fix:** drop the `.json` suffix so X's are trailing (portable; `aws … file://` ignores
the extension).

**Problem 2 — `DeleteObjects MalformedXML`, aborted emptying a small bucket.**
1. `delete-objects` rejected the payload on `snowflake-export` (only ~75 live objects). 2. A single
`list-object-versions --max-items 1000` page returned 537 Versions + 473 DeleteMarkers = **1010**
combined; the Python summed both into one request. 3. S3 `delete-objects` accepts at most **1000
keys** per call. **Root cause:** versioned buckets can return >1000 combined versions+markers per
page. **Fix:** cap each delete batch to `objects[:1000]`; the outer loop re-lists from the start and
converges.

**Problem 3 — `mapfile: command not found`, task-def cleanup silently no-op'd.**
1. Ad-hoc cleanup used `mapfile -t`. 2. macOS ships bash 3.2, which lacks `mapfile` (bash 4+).
**Root cause:** bash-3.2 host. **Fix:** build arrays with `while IFS= read -r … do ARR+=("$line"); done < <(cmd)`.

**Also:** prod `infra/terraform/accounts/prod/backend.hcl` pointed at the stale
`edgartools-dev-tfstate-077127448006/accounts/prod` state (6 resources: leftover notifications
module) instead of the real `edgartools-prod-tfstate/accounts/prod` (44 resources). A naive
`terraform destroy` would have orphaned the entire prod VPC/ECS/KMS stack. **Lesson:** verify a
teardown's backend resolves to the *current* state (`terraform state list` count) before trusting it.

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
  • Derives IS_INSIDER, MANAGES_FUND etc. and syncs to the graph (Snowflake, not external Neo4j)

Stage 3 — Gold refresh (single ECS task)
  gold-refresh
  • Reads complete silver DuckDB, builds all 9 gold tables, writes Snowflake export manifests
  • SNOWFLAKE_RUN_MANIFEST_TASK picks up the manifest and refreshes EDGARTOOLS_GOLD within 1 min
```

**Graph storage (read this before assuming "Neo4j" means an external service):**
As of the `neo4j-snowflake` workstream (v1.3, completed 2026-06-12), graph data lives
*inside* Snowflake — the Neo4j Graph Analytics Native App, installed in the same Snowflake
account as gold. There is no separate Neo4j database, no `NEO4J_URI`/`NEO4J_PASSWORD`
secret, and no external Bolt connection. `mdm sync-graph` materializes
`MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES` (plus per-label/per-type compatibility views) into a
Snowflake schema (e.g. `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`); `mdm verify-graph` runs a
strict SQL parity check plus Native App checks (compute pool, `GRAPH_INFO`, `BFS`, `WCC`)
against that same Snowflake target. One credential (the same `MDM_SNOWFLAKE_*`/
`DBT_SNOWFLAKE_*`/Snowflake CLI connection used everywhere else), one platform. Native App
grants: `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`. Full migration history:
`.planning/workstreams/neo4j-snowflake/`.

**MDM database (read this before assuming a separate AWS RDS instance):**
MDM's operational Postgres database was cut over from AWS RDS (private VPC) to Snowflake's
native Postgres service — provisioned and managed inside the same Snowflake account as
gold and the graph (`infra/scripts/bootstrap-prod-mdm.sh` provisions a "Snowflake Postgres
instance," e.g. `EDGARTOOLS_PROD_MDM`; connects via `snowflake_admin`). No AWS RDS module,
no VPC subnet group, no RDS security group remain for MDM — confirmed via repo-wide search,
zero `rds_mdm`/`mdm_database` Terraform files exist anymore (only `mdm_secret_moves.tf` in
the AWS accounts, handling the Secrets Manager migration). One platform (Snowflake) hosts
gold, the graph, and now MDM's operational store — eliminating the separate AWS RDS
network/credential surface. Note: this is still a distinct Postgres-wire-protocol DSN
(`MDM_DATABASE_URL`, port 5432) from the Snowflake SQL connection used for dbt/gold/graph
(`DBT_SNOWFLAKE_*`/`MDM_SNOWFLAKE_*`, HTTPS) — "one platform" means one Snowflake account
and governance boundary, not literally one shared connection string for both protocols.

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
  --state-machine-arn arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-dev-load-history \
  --name "load-history-$(date +%s)" \
  --input '{}'
# Runs ~15 min for 100 companies (vs 30-90 min sequential)
# Monitor: aws stepfunctions describe-execution --execution-arn <arn> --query status
```

**Do NOT run `bootstrap-next` locally for large batches** — it is sequential, so throughput
alone rules it out at scale. Reserve it for single-company ad-hoc loads with explicit
`--cik-list`. (Historical note: this guidance originally also cited "cannot reach MDM
Postgres, private VPC" — that no longer applies. MDM Postgres moved off AWS RDS onto
Snowflake's native Postgres service; see "MDM database" note below. Local reachability to
the current Snowflake-hosted instance has not been re-verified, so treat the sequential-
throughput reason as the one to rely on.)

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
export WAREHOUSE_BRONZE_ROOT="s3://edgartools-dev-bronze/warehouse/bronze"
export WAREHOUSE_STORAGE_ROOT="s3://edgartools-dev-warehouse/warehouse"
export SERVING_EXPORT_ROOT="s3://edgartools-dev-snowflake-export/warehouse/artifacts/snowflake_exports/"
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
# Requires a SnowCLI connection (configured in ~/.snowflake/config.toml) and keeps
# Snowflake secrets out of repo files.
bash infra/scripts/deploy-snowflake-stack.sh \
  --env dev \
  --snow-connection snowconn \
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
    690839588395.dkr.ecr.us-east-1.amazonaws.com
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

## dbt gold model SQL changes — smoke test convention

When a gold model's SQL body changes (not just its config), `dbt run`
**will not** detect the change for `materialized='dynamic_table'` models —
dbt-snowflake's dynamic-table materialization only diffs *configuration*
(target_lag, warehouse, refresh_mode, etc.), not the SQL body. An unchanged
config means `dbt run` is a silent no-op even though the deployed dynamic
table still runs the old SQL.

To force redeploy of a changed dynamic table, use:

```bash
uv run --with dbt-snowflake dbt run --select <model_name> --full-refresh
```

This issues `CREATE OR REPLACE DYNAMIC TABLE ... initialize = ON_CREATE`,
which triggers an immediate INITIAL refresh.

**Known gap blocking `--full-refresh` (dev, as of 2026-06-13):** the
`EDGARTOOLS_DEV_DEPLOYER` role lacks a direct `SELECT` grant on
`EDGARTOOLS_SOURCE` tables. Ad-hoc queries succeed (via the
`ACCOUNTADMIN`/`ORGADMIN` secondary roles), but Snowflake's dynamic-table
INITIAL refresh checks the table owner role's *direct* grants only —
`CREATE OR REPLACE DYNAMIC TABLE` makes `EDGARTOOLS_DEV_DEPLOYER` the new
owner, so the refresh fails with "not authorized ... (Note: the primary role
is the owner role of the dynamic table)". This affects **any**
`EDGARTOOLS_GOLD` dynamic table's `--full-refresh`, not just one model. See
`TODOS.md` ("EDGARTOOLS_DEV_DEPLOYER lacks direct SELECT on
EDGARTOOLS_SOURCE") for the fix and status.

Required env vars for `dbt run`/`dbt compile` against Snowflake (none have
defaults except role/database/warehouse, which fall back to the dev target's
values in `profiles.yml`):

```bash
export DBT_SNOWFLAKE_ACCOUNT=<account_locator.region.cloud>
export DBT_SNOWFLAKE_USER=<user>
export DBT_SNOWFLAKE_PASSWORD=<password>
export DBT_SNOWFLAKE_WAREHOUSE=EDGARTOOLS_DEV_REFRESH_WH
```

**SnowCLI connection naming.** No literal Snowflake account locator is ever committed to
this repo (always a placeholder like `<account_locator.region.cloud>` above) — the only
project-level convention is the **connection name**, resolved from
`~/.snowflake/config.toml`. `infra/scripts/go-live.sh`'s `default_snow_connection_for_env()`
defines: **`snowconn`** for dev, **`edgartools-prod`** for prod. `go-live.sh` is the
current orchestration entry point and always passes `--snow-connection` explicitly to
`deploy-snowflake-stack.sh`, so its own internal fallback default
(`edgartools-${ENVIRONMENT}`, i.e. `edgartools-dev` for dev) only matters if you invoke
`deploy-snowflake-stack.sh` directly without `--snow-connection` — prefer passing
`--snow-connection snowconn` explicitly for dev rather than relying on either script's
default, since the two scripts disagree.

## Image management

Use AWS ECR only for deployable images. Do not add non-AWS registry targets,
SDKs, ODBC drivers, or deployment steps back into this repo unless the platform
architecture changes explicitly.

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
    690839588395.dkr.ecr.us-east-1.amazonaws.com

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
  --output text | xargs -I{} echo "690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-warehouse@{}")
MDM_REF=$(aws ecr describe-images \
  --region us-east-1 \
  --repository-name edgartools-dev-mdm \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageDigest" \
  --output text | xargs -I{} echo "690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-mdm@{}")

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

ECR="690839588395.dkr.ecr.us-east-1.amazonaws.com"
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
ECR="690839588395.dkr.ecr.us-east-1.amazonaws.com"
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

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools directly.

Available gstack skills:

| Skill | Purpose |
|-------|---------|
| `/office-hours` | Async Q&A and coaching sessions |
| `/plan-ceo-review` | CEO-lens plan review |
| `/plan-eng-review` | Engineering-lens plan review |
| `/plan-design-review` | Design-lens plan review |
| `/design-consultation` | Design consultation session |
| `/design-shotgun` | Rapid parallel design exploration |
| `/design-html` | Generate HTML design artifacts |
| `/review` | Code review |
| `/ship` | Ship a change end-to-end |
| `/land-and-deploy` | Land PR and deploy |
| `/canary` | Canary deploy workflow |
| `/benchmark` | Run benchmarks |
| `/browse` | Web browsing (use this for all browsing) |
| `/connect-chrome` | Connect to Chrome for browser automation |
| `/qa` | Full QA pass |
| `/qa-only` | QA without implementation |
| `/design-review` | Design review pass |
| `/setup-browser-cookies` | Configure browser cookies |
| `/setup-deploy` | Configure deploy settings |
| `/setup-gbrain` | Configure gbrain |
| `/retro` | Retrospective |
| `/investigate` | Investigate an issue |
| `/document-release` | Document a release |
| `/document-generate` | Generate documentation |
| `/codex` | Codex integration |
| `/cso` | CSO workflow |
| `/autoplan` | Automated planning |
| `/plan-devex-review` | Developer experience plan review |
| `/devex-review` | Developer experience review |
| `/careful` | Extra-careful execution mode |
| `/freeze` | Freeze a dependency or config |
| `/guard` | Guard a file or section |
| `/unfreeze` | Unfreeze a dependency or config |
| `/gstack-upgrade` | Upgrade gstack |
| `/learn` | Learn about a topic or codebase |

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
