---
name: aws-snowflake-operations
description: This platform's AWS and Snowflake operations - the one live AWS account, the decommissioned dev environments, Snowflake SQL and grant rules learned from incidents, the hosted MDM store, gold refresh, dbt dynamic-table redeploys, Terraform, ECR images and deploy recipes. Use before running any AWS, Snowflake, dbt, Terraform, image build or deploy command.
---

# AWS and Snowflake Operations

Read before any AWS, Snowflake, dbt, Terraform, image or deploy command. Moved
from CLAUDE.md on 2026-10-28 (operator, 2026-10-28: "specific occasional tasks
move it to a skill or rules file"); the rules are unchanged and live.

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

## Snowflake DEV is DECOMMISSIONED (2026-07-29) — READ THIS before running any `snowconn`/dev Snowflake command

**AWS-side dev (`edgartools-dev-*` S3/ECS/Step Functions, incl. the `edgartools-dev-tfstate`
Terraform state bucket) was decommissioned first, separately from this Snowflake teardown.**
By the time this Snowflake decommission ran, the `edgartools-dev-tfstate` bucket no longer
existed — so `terraform destroy` was **not** viable for either
`infra/terraform/snowflake/accounts/dev` or `infra/terraform/access/snowflake/accounts/dev`
(no remote state to read). Decommissioned instead via a direct live-object sweep against
Snowflake account `xcpclkf-kb19989` (same account prod lives in — dev/prod are separate
**databases**, not separate accounts): `EDGARTOOLS_DEV` database (dropped CASCADE — all 8
schemas: `EDGARTOOLS_GOLD`, `EDGARTOOLS_SOURCE`, `EDGARTOOLS_DASHBOARD`, `MDM`,
`MDM_GRAPH_REVIEW`, `NEO4J_GRAPH_MIGRATION`, `PUBLIC`, plus `INFORMATION_SCHEMA`), both
warehouses (`EDGARTOOLS_DEV_READER_WH`, `EDGARTOOLS_DEV_REFRESH_WH`), all 4 roles
(`EDGARTOOLS_DEV_LOADER`, `EDGARTOOLS_DEV_DASHBOARD_OWNER`, `EDGARTOOLS_DEV_DEPLOYER`,
`EDGARTOOLS_DEV_READER`), the `EDGARTOOLS_DEV_EXPORT_INTEGRATION` storage integration, and
the account-level `EDGARTOOLS_DEV_MDM` Snowflake Postgres instance (MDM's dev operational
store — a distinct object type from the database, `retention_time=0`, no undrop safety net;
its `EDGARTOOLS_DEV_MDM_POSTGRES_POLICY` network policy had to be dropped first since a
network rule inside `EDGARTOOLS_DEV.MDM` was bound to it, which otherwise blocks
`DROP DATABASE ... CASCADE` with "includes network rule - policy associations"). Verified
live afterward: zero `EDGARTOOLS_DEV%`-named objects of any kind remain in the account.

**No state backup exists for this teardown** — unlike the AWS `077127448006` decommission,
which had `~/edgartools-077-tfstate-backups-FINAL`, dev Snowflake's Terraform backend was
already gone before this ran, so there was nothing to pull. The live-object inventory
gathered immediately before the drop (captured in this session's transcript) is the only
record of what existed.

**Anything that still references dev Snowflake is stale**, including but
not limited to: the `snowconn` SnowCLI connection convention,
`EDGARTOOLS_DEV_LOADER`/`EDGARTOOLS_DEV_DEPLOYER` role references, `dbt run --target dev` (the default target), and the
`WAREHOUSE_BRONZE_ROOT="s3://edgartools-dev-bronze/..."` env-var example. Do not run any
dev-targeted command (`dbt ... --target dev`, `deploy-snowflake-stack.sh --env dev`,
`bootstrap-*` against dev) without first reprovisioning the dev Terraform roots from
scratch — there is currently no dev Snowflake environment to target. Prod
(`EDGARTOOLS_PROD`, `edgartools-prod` connection) is unaffected and was not touched by this
teardown.

## Data Layer Definitions

| Layer | Location | Description |
|-------|----------|-------------|
| **Bronze** | S3 (`s3://<bucket>/`) and local captures | Provider files as captured, one receipt per file. Never mutated. |
| **Source** | Snowflake `EDGARTOOLS_SOURCE` | External stage + tables auto-refreshed from S3 via Snowflake native S3 pull (bootstrap SQL). Read-only raw layer. |
| **Silver** | Snowflake `EDGARTOOLS_SILVER` (landing zone `EDGARTOOLS_SILVER_LANDING` + dbt collapse); the rebuild's writer is `edgar_warehouse/silver_writer/` (PostgreSQL 16 today; a Snowflake sink is its own ticket) | Cleaned, typed, deduplicated records. The old landing writer and the local DuckDB store are deleted. |
| **Gold** | `EDGARTOOLS_GOLD` (23 dbt dynamic tables) | Business-ready tables, e.g. `company`, `ownership_holdings`, `ownership_activity`, `filing_detail`, `filing_activity`, `adviser_disclosures`, `adviser_offices`, `private_funds`, `ticker_reference`, `edgartools_gold_status`, plus 13 more added since this table was first written (`accounting_flags`, `adv_fund_count_reconciliation`, `consensus_estimates`, `earnings_calendar`, `earnings_releases`, `executive_records`, `financial_derived`, `financial_factors`, `financial_facts`, `guidance_facts`, `institutional_holdings`, `mdm_company`, `transcript_events`) — see `infra/snowflake/dbt/edgartools_gold/models/gold/` for the current, authoritative list rather than trusting this count to stay accurate. Refreshed on a Snowflake-managed schedule. |

## Snowflake rules learned from incidents

- Do not use the shorthand multi-column `FOR row IN (SELECT a, b, ...) DO` cursor form in this account —
  it fails with `Unsupported: Scalar subquery with multi-column SELECT clause`. Use an explicit
  `DECLARE ... CURSOR ... OPEN ... FOR i IN 1 TO <precomputed COUNT(*)> DO FETCH ... END FOR` (a "loop
  until FETCH returns nothing" pattern hangs and needs `SYSTEM$CANCEL_QUERY`). Live in
  `04_refresh_wrapper.sql`.
- `GRANT OWNERSHIP ... REVOKE CURRENT GRANTS` strips *all* outbound grants, not just the previous
  owner's — it once silently dropped the dashboard reader role's `SELECT` on all 20 gold tables. Use
  `COPY CURRENT GRANTS`, or additive `GRANT ... ON ALL/FUTURE TABLES`.
- `NOW()` is rejected in a column `DEFAULT` clause specifically (it works fine as an ordinary function
  call) — use `CURRENT_TIMESTAMP()`.
- `CREATE SCHEMA IF NOT EXISTS` evaluates the `CREATE SCHEMA` privilege *before* checking whether the
  schema already exists, so pre-creating it as `ACCOUNTADMIN` does not let an under-privileged role skip
  the check.
- Streamlit-in-Snowflake apps run with the app **owner's** privileges, and
  `GRANT/REVOKE OWNERSHIP ON STREAMLIT` is unsupported — ownership is fixed at creation. The only way to
  change it is to create the object while running *as* the target role. Terraform tracks no owner
  attribute, so any `-replace`/destroy-recreate silently reverts ownership to the admin role and
  `infra/snowflake/sql/graph_review/02_dashboard_reader_grants.sql` must be re-run. Check
  `SHOW STREAMLITS`' `owner` column before trusting any "access limited to a dedicated read role" claim.
- Before adding any new Snowflake `TASK`: a fixed-interval poll task pays a per-resume warehouse charge
  close to every tick unless the interval is wide enough for a real suspend in between. Size it against an
  explicit credit budget up front, or gate it (`WHEN SYSTEM$STREAM_HAS_DATA(...)`) — never ship a "tune
  later" cadence. `LOAD_SILVER_LANDING_TASK` ran at 5 MIN (~9 credits/day) until this was caught; it is
  now 180 MIN.
- Loading Parquet with `USE_LOGICAL_TYPE = false` reads a UTC timestamp as zone-less clock time and labels
  it with the session `TIMEZONE`, defaulting to `America/Los_Angeles`. Pin `TIMEZONE = 'UTC'` on every
  loading session, including owner's-rights procedures, which run with the *caller's* timezone. Guarded by
  `tests/unit/test_loader_task_timezone_sql.py`.
- `snowflake-connector-python` reads the module-global `paramstyle` once, at `connect()` time, and caches
  it on the connection — mutating the global afterward has no effect. Set it before `connect()` for `?`-style placeholders.
- `EDGARTOOLS_PROD_LOADER` owns the gold objects `REFRESH_AFTER_LOAD` refreshes, so it needs `OPERATE` +
  `SELECT` on everything a gold model references, `EDGARTOOLS_SILVER` included. Its secret
  (`MDM_SNOWFLAKE_SECRET_JSON`) keeps `MDM_SNOWFLAKE_SCHEMA` at `EDGARTOOLS_GOLD`.

## The hosted MDM store

- `mdm migrate` does not run automatically on deploy. Treat any prod deploy carrying new migration files
  as incomplete until it has been re-run explicitly — "the image is current" and "the migration was
  applied" are separate facts.
- Snowflake-hosted Postgres re-grants `snowflake_write`'s baseline DML as a platform side effect of
  `ALTER POSTGRES INSTANCE ... RESET ACCESS FOR '<role>'` for *either* role, so `bootstrap-prod-mdm.sh`
  runs `mdm migrate` as its true last database-mutating step.

## Pipeline and runtime rules

- Bounded work and idempotent output are the `bookkeeping` skill's (DESIGN: a bounded, validated
  child-work manifest; immutable output by conditional creation, `IfNoneMatch: *`), the one source for them.
- Any "same calendar day" check needs an explicit timezone, and the right one is the business
  process's — `America/New_York` via `pytz` (`zoneinfo` needs a tz database these images don't install).
- A one-time backfill CLI's `--dry-run` needs a `--limit` from the start: proving the logic on real data
  needs tens of rows; only estimating full-run cost needs the whole table.
- Before running a multi-step workflow step by step by hand, look for the one already built (a
  Bookkeeping run, a committed script). The old AWS Step Functions are leftovers, never that workflow.
- Provisioning that isn't Terraform or a committed script does not survive an account rebuild, however
  carefully a runbook describes it. And when one stage turns out to have been an uncommitted manual step,
  assume every later stage in the same family is too.
- A check that can silently run against stale, superseded infrastructure makes a false positive and a
  false negative look identical to success. Confirm the *code* under test is what is actually running
  before treating a clean result as evidence — a SQL contract "applied successfully" says nothing about
  the image that writes to it.

## Credentials on the command line

- Never pipe `snow sql ... RESET ACCESS` or `aws secretsmanager get-secret-value` output to
  `head`/`tail`/`cat`/a bare variable capture, for any reason including debugging a downstream parsing
  error — pipe straight into the credential-consuming script and put debug output (`type(pw)`, length,
  key presence) *inside* that script. This leaked a live plaintext password into a transcript twice in one
  session.

## Known open items

Deploy status below is as last recorded on each item's own date — re-check against the running image
before trusting it.

- **The `EDGARTOOLS_DECISION` schema does not exist**, leaving 5 Terraform-managed grants unapplied.
  `infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql`'s "MDM active-company universe"
  join is an explicit placeholder that self-joins `COMPANY`, and
  `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql`'s `BUNDLE_AUDITOR` references
  `EDGARTOOLS_GOLD.SEC_AUDITOR_REPORT_EVIDENCE`, which exists only in `EDGARTOOLS_SOURCE`. The real
  blocker behind both: no Snowflake-side source has been chosen for "MDM active company universe" (MDM's
  authority is Postgres; the closest reflection is `NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES`).
- **The original `EDGARTOOLS_DASHBOARD` Streamlit app is still ACCOUNTADMIN-owned** — the same gap already
  fixed for `MDM_GRAPH_DASHBOARD`, with the same drop/recreate-as-target-role recipe.
- **Release-readiness Ticket 74, items 1-2:** repairing the two known stale accessions, and a proactive
  scan for other pre-2026-07-31 stale bronze objects.

## Snowflake-side facts from the old pipeline (still live)

The old AWS pipeline (`load_history`, `daily_incremental`, `targeted_resync`,
`gold_refresh`, `one_click_data_refresh` and their ECS commands) is deleted
from this repository: its Step Function builders and commands are gone, so
anything of it still deployed in AWS is a leftover, never something to run.
What it left in Snowflake is live:

- **Gold refresh.** `EDGARTOOLS_GOLD`'s dynamic tables use `target_lag = '6 hours'`
  (`gold_model_config()`); `TARGET_LAG = DOWNSTREAM` never refreshes a gold
  leaf. `SNOWFLAKE_RUN_MANIFEST_TASK` must be STARTED in `EDGARTOOLS_GOLD`: it
  runs `LOAD_EXPORTS_FOR_RUN`, then `REFRESH_AFTER_LOAD`, as an explicit trigger.
- **Graph storage is inside Snowflake**, not an external Neo4j: the Neo4j
  Graph Analytics Native App in the same account, tables in
  `NEO4J_GRAPH_MIGRATION`, the live generation named by
  `GRAPH_ACTIVE_POINTER`. There is no `NEO4J_URI` and no Bolt connection.
  Grants: `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`.
- **MDM's hosted store is Snowflake Postgres**, not AWS RDS
  (`infra/scripts/bootstrap-prod-mdm.sh` provisions the instance; it connects
  as `snowflake_admin`). It is a PostgreSQL-protocol address
  (`MDM_DATABASE_URL`, port 5432), separate from the Snowflake SQL connection
  used for dbt and gold: one account and governance boundary, two protocols.

## Development Commands

> **Tooling:** always use `uv` for Python dependency management and Python CLI
> execution in this repo. The lockfile is `uv.lock`; never invoke bare `pip` or
> bare `dbt` from repo workflows. Use `uv sync` for project deps, `uv pip
> install` for deliberate one-off installs, and `uv run --with <package>` when a
> deploy needs a transient tool such as `dbt-snowflake`.
>
> **Docker runtime:** use the Docker context already configured on the machine.
> Leave `DOCKER_HOST` unset. Publish images with `docker build` and
> `docker push` through `infra/scripts/publish-warehouse-image.sh --mode docker`.
> Local PostgreSQL 16 for agents is the shared server in
> "Initialize shared local PostgreSQL" (`docs/local-agent-testing.md` in the repository).

```bash
# SEC User-Agent for a provider capture (provider_capture); must contain an email
export EDGAR_IDENTITY="EdgarTools Platform <email>"
export AWS_DEFAULT_REGION=us-east-1  # infra is us-east-1, not the default us-east-2
# (deploy-snowflake-stack.sh still reads WAREHOUSE_*_ROOT and SERVING_EXPORT_ROOT for its stage)

# Install project deps (uses uv.lock)
uv sync --extra s3 --extra snowflake

# CLI: start with doctor (the data-platform skill, Setup)
edgar-warehouse --help
edgar-warehouse doctor

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

# Snowflake native-pull deploy (prod; dev is decommissioned, above)
# Requires a SnowCLI connection (configured in ~/.snowflake/config.toml) and keeps
# Snowflake secrets out of repo files. A prod change needs the operator's word.
bash infra/scripts/deploy-snowflake-stack.sh \
  --env-name prod \
  --snow-connection edgartools-prod \
  --run-validation \
  --run-dbt

# Docker image publish (configured Docker context; full recipe below)
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    690839588395.dkr.ecr.us-east-1.amazonaws.com
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-images \
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

A `--full-refresh` makes the deploying role the dynamic table's owner, and the
INITIAL refresh checks that role's *direct* grants only (secondary roles do not
count): give it direct `SELECT` on every table the model reads first.

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
`~/.snowflake/config.toml`. **`--snow-connection` is required and never derived** from the
environment name — as of wayfinder ticket 03 (snowflake-env-provisioning map), both
`install.sh` (renamed from `go-live.sh` per the snowflake-account-cutover map's Ticket 05)
and `deploy-snowflake-stack.sh` fail closed without it. This replaced two
*disagreeing* derivations of the same default (`install.sh` mapped dev to `snowconn`,
while `deploy-snowflake-stack.sh` string-built `edgartools-${ENVIRONMENT}`, i.e.
`edgartools-dev`), which is why neither derives one now. Prod's connection is
`edgartools-prod`; pass it explicitly.

**Environment identifier.** The same ticket replaced `--env <dev|prod>` with
`--env-name <slug>` across `install.sh`, `deploy-snowflake-stack.sh`,
`bootstrap-prod-mdm.sh`, `bootstrap-aws-mdm-secrets.sh`, and `create-deployer.sh`
(positional). A slug is lowercase letters/digits in hyphen-separated words
(`prod`, `eu-prod`); hyphens map to underscores for Snowflake identifiers
(`eu-prod` → `EDGARTOOLS_EU_PROD`). There is **no `--env` back-compat alias** — the
rename was clean, since dev is decommissioned and prod was the only live caller.
The AWS-side scripts that took `--env` (`deploy-aws-application.sh`, `run-aws-mdm-e2e.sh`)
were retired (platform validation 2b, 2026-09-30).

## Image management

Use AWS ECR only for deployable images. Do not add non-AWS registry targets,
SDKs, ODBC drivers, or deployment steps back into this repo unless the platform
architecture changes explicitly.

**One shared ECR repository per environment** (`edgartools-<env>-images`)
holds all four image kinds. Role and build stage are encoded entirely in the
**tag prefix** (`warehouse-*` / `mdm-*` / `warehouse-deps-*` / `mdm-deps-*`),
not the repository name — `publish-warehouse-image.sh` applies this prefix
automatically based on `--role`, so callers keep passing plain tags
(`sha-<hash>`, `dev`, `deps-<hash>`) and only `--ecr-repository` changes.
(Superseded, pre-consolidation repos — `edgartools-<env>-warehouse`,
`-mdm`, `-warehouse-deps`, `-mdm-deps` — are left in place as a read-only
rollback archive; nothing pushes to them anymore.)

| Image kind | Tag prefix | Dockerfile | Installs | Runs |
|------------|------------|------------|----------|------|
| warehouse deps | `warehouse-deps-*` | `Dockerfile.warehouse-deps` | locked `.[s3]` deps via `uv` | dependency base image |
| warehouse final | `warehouse-*` | `Dockerfile` | source copy on warehouse deps | warehouse ECS tasks |
| mdm deps | `mdm-deps-*` | `Dockerfile.mdm-deps` | locked `.[s3,mdm-runtime]` deps via `uv`; no API/admin packages | MDM Step Functions dependency base image |
| mdm final | `mdm-*` | `Dockerfile.mdm-neo4j` | source copy on MDM deps | MDM ECS tasks/API |

**Tagging strategy**

| Tag | Meaning |
|-----|---------|
| `warehouse-dev` / `mdm-dev` | Mutable latest dev image, per role |
| `warehouse-sha-<hash>` / `mdm-sha-<hash>` | Immutable rollback/audit image, per role |
| `warehouse-prod` / `mdm-prod` | Manually promoted production image, per role |
| `warehouse-deps-<hash>` / `mdm-deps-<hash>` | Dependency base image, keyed by lockfile hash |

**Manual AWS build and deploy — configured Docker context**

Publish with `docker build` and `docker push` through
`infra/scripts/publish-warehouse-image.sh --mode docker`.
Prod promotion (build/push under `edgartools-prod-images`) is manual; the AWS
pipeline deploy script was retired (platform validation 2b, 2026-09-30).
Use the steps below for prod promotion and ad-hoc builds.

```bash
# 1. Confirm the configured Docker context answers (`docker info`).

# 2. Authenticate to ECR (token valid for 12 h).
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    690839588395.dkr.ecr.us-east-1.amazonaws.com

# NOTE: the ECR repository must have MUTABLE tags for warehouse-dev/mdm-dev
# to be overwritten. If you see "tag is immutable" on push, run once:
#   aws ecr put-image-tag-mutability --region us-east-1 \
#     --repository-name edgartools-dev-images --image-tag-mutability MUTABLE

# 3a. Build and push the warehouse image (tags as warehouse-sha-<hash>, warehouse-dev).
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-images \
  --role warehouse \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# 3b. Build and push the MDM image (tags as mdm-sha-<hash>, mdm-dev; when edgar_warehouse/mdm/** changed).
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-images \
  --role mdm \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev

# 4. Capture the digest refs that step 3 printed (used for deploy). Query by
#    tag prefix since the repo now holds both roles.
WAREHOUSE_REF=$(aws ecr describe-images \
  --region us-east-1 \
  --repository-name edgartools-dev-images \
  --query "sort_by(imageDetails[?contains(imageTags[0], 'warehouse-sha-')],&imagePushedAt)[-1].imageDigest" \
  --output text | xargs -I{} echo "690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-images@{}")
MDM_REF=$(aws ecr describe-images \
  --region us-east-1 \
  --repository-name edgartools-dev-images \
  --query "sort_by(imageDetails[?contains(imageTags[0], 'mdm-sha-')],&imagePushedAt)[-1].imageDigest" \
  --output text | xargs -I{} echo "690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-images@{}")
```

**If publish-warehouse-image.sh fails with a cache layer error**

```bash
# Look up current deps tags from ECR (avoids stale hardcoded values)
WH_DEPS=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-images \
  --query "sort_by(imageDetails[?contains(imageTags[0], 'warehouse-deps-')],&imagePushedAt)[-1].imageTags[0]" --output text)
MDM_DEPS=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-images \
  --query "sort_by(imageDetails[?contains(imageTags[0], 'mdm-deps-')],&imagePushedAt)[-1].imageTags[0]" --output text)

ECR="690839588395.dkr.ecr.us-east-1.amazonaws.com"
SHA_TAG="sha-$(git rev-parse --short=12 HEAD)"
REPO="edgartools-dev-images"

# Rebuild warehouse directly
docker pull "${ECR}/${REPO}:${WH_DEPS}"
docker build --platform linux/amd64 \
  --build-arg "DEPENDENCY_IMAGE=${ECR}/${REPO}:${WH_DEPS}" \
  -f Dockerfile -t "${ECR}/${REPO}:warehouse-${SHA_TAG}" -t "${ECR}/${REPO}:warehouse-dev" .
docker push "${ECR}/${REPO}:warehouse-${SHA_TAG}"
docker push "${ECR}/${REPO}:warehouse-dev"

# Rebuild MDM directly
docker pull "${ECR}/${REPO}:${MDM_DEPS}"
docker build --platform linux/amd64 \
  --build-arg "DEPENDENCY_IMAGE=${ECR}/${REPO}:${MDM_DEPS}" \
  -f Dockerfile.mdm-neo4j -t "${ECR}/${REPO}:mdm-${SHA_TAG}" -t "${ECR}/${REPO}:mdm-dev" .
docker push "${ECR}/${REPO}:mdm-${SHA_TAG}"
docker push "${ECR}/${REPO}:mdm-dev"
```

**When to rebuild which image**

| Changed paths | Rebuild |
|---------------|---------|
| `edgar_warehouse/**` (excluding `edgar_warehouse/mdm/`) | warehouse only |
| `edgar_warehouse/mdm/**` | MDM only |
| `rules/**` or `edgar_warehouse/rules/**` | MDM (MDM loads its mappings and merge rules from `rules/`); both images copy `rules/`, so rebuild both to keep them equal |
| Both (e.g. `orchestrator.py` + `mdm/cli.py`) | both |
| `Dockerfile` / `Dockerfile.warehouse-deps` | warehouse (+ deps if lock changed) |
| `Dockerfile.mdm-neo4j` / `Dockerfile.mdm-deps` | MDM (+ deps if lock changed) |
| `uv.lock` | deps images for both — run without `--skip-build` |
| `crates/source-contract/**` (the source engine) | deps images for both: they build its wheel, and the deps tag hashes the crate |

**Clean up local images before a build (run this first every time)**

The local Docker daemon accumulates stale images: old SHA tags, debug tags, superseded deps layers. Clean before building to avoid cache confusion and reclaim disk.

```bash
# 1. Show what's on disk
docker system df
docker images --format "{{.Repository}}:{{.Tag}}\t{{.Size}}"

# 2. Remove dangling (untagged) images and unused build cache
docker image prune -f
docker builder prune -f

# 3. Remove old named images — keep only warehouse-dev/mdm-dev and each
#    role's latest sha-* tag. List old tags from the output above and delete
#    explicitly:
ECR="690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-images"
docker rmi \
  "${ECR}:warehouse-sha-<old>" \
  "${ECR}:mdm-sha-<old>" \
  "${ECR}:warehouse-deps-<old>" \
  # ... add any debug/ad-hoc tags (routerfix-*, hydratefix-*, etc.)

# 4. Nuclear option — wipe everything (forces full re-pull of base + deps on next build)
docker system prune -af   # WARNING: removes ALL local images, not just ours
```

**What to keep:**
- `warehouse-dev` / `mdm-dev` — used as build cache source (`--cache-from-tag dev`, per role)
- Latest `warehouse-sha-<hash>` / `mdm-sha-<hash>` — rollback anchor, per role
- Latest `warehouse-deps-<hash>` / `mdm-deps-<hash>` — slow to rebuild; only remove if `uv.lock` changed
- `public.ecr.aws/docker/library/python:3.12-slim-bookworm` — base layer cache

**Rollback to a previous SHA**

```bash
ECR=<account>.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-images
SHA=warehouse-sha-abc1234   # or mdm-sha-abc1234 for the mdm role
docker pull $ECR:$SHA
docker tag  $ECR:$SHA $ECR:warehouse-dev
docker push $ECR:warehouse-dev
```

## ECS cost sizing (old pipeline)

The ECS sizing study (Ticket 28, 2026-08-30) measured MDM commands of the old
pipeline, since deleted; its method stays valid for a future worker runtime:
judge a cheaper profile on validated output (correctness, completeness,
idempotency across reruns, a matched control on the same input), never on
memory use or an exit code. Evidence:
`.scratch/ecs-cost-sizing/issues/28-run-mdm-residual-security-medium-canaries-and-unbounded-graph-sync-canary.md`,
`.scratch/ecs-cost-sizing/evidence/ticket28/`.

## Setup

`docs/runbook.md` covers end-to-end environment setup: AWS credentials, Snowflake keypair auth, S3
buckets, dbt profiles and the first-run bootstrap.
