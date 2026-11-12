---
name: aws-snowflake-operations
description: This platform's AWS and Snowflake operations - the one live AWS account, the decommissioned dev environments, Snowflake SQL and grant rules learned from incidents, the hosted MDM store, gold refresh, dbt dynamic-table redeploys, Terraform, ECR images and deploy recipes. Use before running any AWS, Snowflake, dbt, Terraform, image build or deploy command.
---

# AWS and Snowflake Operations

Read before any AWS, Snowflake, dbt, Terraform, image or deploy command.

## AWS account map (READ THIS before running any AWS command)

**The platform lives in AWS account `690839588395` (current/active).** All `edgartools-*`
resources, ECR images, ECS clusters, and Terraform state should target `690839588395`.

**Account `077127448006` is DECOMMISSIONED and empty.** Everything was migrated to
`690839588395` first, then the old account was torn down.
- **Final closure is a ROOT action.** The `cli-access` IAM user in `077127448006` *cannot*
  close the account: closure or suspension is done through root sign-in or the AWS
  Organizations management account. What was left in place is reaped when the account is closed.
- **State backups** (the only surviving record of the destroyed account) live at
  `~/edgartools-077-tfstate-backups-FINAL` and `infra/.aws-tfstate-backups/`.
- Do NOT reprovision anything into `077127448006`. If an old ARN/bucket/`aws-prod-application.json`
  still references `077127448006`, it is stale — the live target is `690839588395`.

## Snowflake DEV is DECOMMISSIONED — READ THIS before running any `snowconn`/dev Snowflake command

**There is no dev environment, on AWS or on Snowflake.** Dev was removed by a direct sweep of
live objects, with no Terraform state and no backup, so it can only be reprovisioned from scratch.

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
  until FETCH returns nothing" pattern hangs and needs `SYSTEM$CANCEL_QUERY`). The manifest
  procedures `REFRESH_AFTER_LOAD` and `PROCESS_RUN_MANIFEST_STREAM` have one definition, Terraform's
  `native_pull` module (`infra/terraform/snowflake/modules/native_pull/sql/`); the stream processor is
  JavaScript (a temp table, then a loop), so it uses no cursor. Edit them there, never as a second copy
  in `infra/snowflake/sql/bootstrap/` (the `04_refresh_wrapper.sql` copy was deleted).
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
  `ALTER POSTGRES INSTANCE ... RESET ACCESS FOR '<role>'` for *either* role, so run `mdm migrate` as the last
  database-mutating step after any reset. A reset also replaces that role's password, so it needs the operator's word.

### Creating the hosted store in an empty account

Check the account first: `snow sql --connection <name> -q "SHOW DATABASES"` and `"SHOW POSTGRES INSTANCES"`.
A rebuilt account holds neither the `EDGARTOOLS_<ENV>` database nor an instance, and the account named in older
notes is not the live one. The order:

1. The database and its `MDM` schema (the network rule and policy live in that schema).
2. `infra/snowflake/postgres/mdm_create_network_policy.sql`, then `mdm_create_instance.sql`.
3. `bootstrap-prod-mdm.sh`, which rotates both credentials and runs `mdm migrate` last. It rotates on every run
   with no way to skip it, and a rotation needs the operator's word; without it, build the connection file from the
   instance's saved credentials and run `mdm migrate` directly.

- Every `snow sql --filename ... -D name=value` run of those two files needs `--enable-templating JINJA`. Without
  it the CLI leaves `{{ name }}` unreplaced and fails with `syntax error ... unexpected '{'`.
- `CREATE POSTGRES INSTANCE` returns the generated admin and application credentials once, inside the `access_roles`
  value. Send its output to a private file (`umask 077`, a folder outside the repository) and never to the terminal.
  The instance stays `CREATING` for a short while; wait for `state` to read `READY` before connecting.
- A Snowflake CLI result with a credential in it is redacted by key *and by value*: print only the named keys
  you know are public (`state`, `host`, `compute_family`), never a slice of a value, since a slice of a password is a
  leak.

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
  (`infra/snowflake/postgres/mdm_create_instance.sql` creates the instance; the owner connects
  as `snowflake_admin`). It is a PostgreSQL-protocol address
  (`MDM_DATABASE_URL`, port 5432), separate from the Snowflake SQL connection
  used for dbt and gold: one account and governance boundary, two protocols.

## Development Commands

Read [COMMANDS.md](COMMANDS.md) for the exact command before a setup, Terraform, dbt or deploy step.

## dbt gold model SQL changes — smoke test convention

Read [COMMANDS.md](COMMANDS.md), "dbt gold model SQL changes", before changing a gold model's SQL body: `dbt run` alone does not redeploy a dynamic table whose configuration is unchanged.

## Image management

Read [IMAGES.md](IMAGES.md) before building, tagging, publishing or pruning a container image, or changing an ECR repository.

## Sizing a worker runtime

Judge a cheaper profile on validated output (correctness, completeness,
idempotency across reruns, a matched control on the same input), never on
memory use or an exit code. The method and its evidence are in
`.scratch/ecs-cost-sizing/`.

## Setup

`docs/runbook.md` covers end-to-end environment setup: AWS credentials, Snowflake keypair auth, S3
buckets, dbt profiles and the first-run bootstrap.
