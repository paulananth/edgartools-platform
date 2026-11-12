# Development and deploy commands

Part of the `aws-snowflake-operations` skill: [SKILL.md](SKILL.md) says when to read this.

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
environment name — `deploy-snowflake-stack.sh` fails closed without it, and no script derives one from the environment. Prod's connection is
`edgartools-prod`; pass it explicitly.

**Environment identifier.** The same ticket replaced `--env <dev|prod>` with
`--env-name <slug>` across `deploy-snowflake-stack.sh` and `create-deployer.sh`
(positional). A slug is lowercase letters/digits in hyphen-separated words
(`prod`, `eu-prod`); hyphens map to underscores for Snowflake identifiers
(`eu-prod` → `EDGARTOOLS_EU_PROD`). There is **no `--env` back-compat alias** — the
rename was clean, since dev is decommissioned and prod was the only live caller.
The AWS-side scripts that took `--env` (`deploy-aws-application.sh`, `run-aws-mdm-e2e.sh`)
were retired (platform validation 2b, 2026-09-30).
