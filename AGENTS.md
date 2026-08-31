# EdgarTools Platform Agent Guide

## Scope

This repository is an SEC EDGAR data platform built on the `edgartools` PyPI package. The active AWS path is:

```text
SEC EDGAR API
  -> edgar-warehouse Python CLI
  -> S3 bronze and warehouse Parquet/object storage
  -> Snowflake native S3 pull
  -> dbt gold dynamic tables
  -> Streamlit dashboard
```

Keep agent work AWS-focused. Do not add or revive non-AWS deployment paths, registry targets, storage targets, workflow engines, or secret-management steps unless the user explicitly asks for that architecture change.

## Parallel Agent Workstreams

Claude and Codex may work on this repository independently, but they must not share an uncoordinated edit surface.

- **HARD RULE: never commit directly to `main`, for any reason, including a
  quick fix or a single-file doc change.** The moment you pick up a ticket or
  issue — before writing any code, before the first edit — create your own
  `<runtime>/<topic>` branch (in your own worktree per the rule below) and
  commit there. Confirmed live 2026-08-28: a Codex session started and
  finished real implementation work for ecs-cost-sizing Ticket 08 (rollback
  registry, CLI, deploy script, tests) as a local, unpushed commit sitting
  directly on `main` in the shared working directory — no branch at all, not
  even a wrongly-prefixed one. It was only caught because a Claude session
  happened to notice local `main` was one commit ahead of `origin/main`
  before pushing anything; had that push happened first, it would have put
  unreviewed work straight on `main` with no branch, no PR, and no review
  gate. Recovered by branching off that commit
  (`codex/ecs-cost-sizing-revision-retirement-gates`), pushing it, then
  hard-resetting local `main` back to `origin/main`. If you ever find
  yourself with uncommitted or committed changes on `main` for ticket/issue
  work, stop, branch off `HEAD` immediately, and reset `main` back to
  `origin/main` before doing anything else.
- **HARD RULE: no two runtimes may ever commit to the same branch.** Each
  runtime works on its own dedicated branch. If you find yourself about to
  commit and `git log -1` shows a commit authored by another runtime's
  current work that you did not expect, STOP — do not commit — and ask the
  user how to proceed (e.g. branch off, rebase onto a new branch, or hand
  off).
- **HARD RULE: use a dedicated git worktree per active runtime session, not
  a bare checkout in one shared working directory, whenever more than one
  runtime (or more than one session of the same runtime) may be active at
  the same time.** A bare shared checkout only has *one* branch checked out
  at once — a second session switching that checkout disrupts a first
  session's in-progress work even when nothing is actually lost (git
  preserves the underlying commits/stashes either way). Create your own
  worktree (`git worktree add ../<repo>-<topic> <branch>`) and work there
  instead. If you notice your working directory's checked-out branch changed
  unexpectedly mid-session, do not assume anything was lost — check
  `git branch --show-current`, `git reflog`, and that your own
  commits/stash still resolve by name before taking any recovery action, and
  push your own branch to `origin` as soon as it's in a good state so it no
  longer depends on the shared working directory's state.
- Branch naming convention: prefix branches with the owning runtime, e.g.
  `claude/<topic>` or `codex/<topic>`. Before starting work or committing,
  run `git branch --show-current` — if the current branch is prefixed for a
  *different* runtime (or is a shared branch like `main`/`codex/main-sync`
  that another runtime is actively using), create/check out your own branch
  (in your own worktree) before making any commits.
- Treat the current Codex work as protected unless the user explicitly hands it off.
- Use separate GSD workstream directories under `.planning/workstreams/<name>/`; do not edit another runtime's active workstream files.
- Before editing, run `git status --short` and `git log -1` and inspect `.planning/active-workstream` when present.
- Avoid overlapping source files, Terraform roots, generated application JSON, and planning artifacts across runtimes unless the user assigns the same task to both.
- If overlap is unavoidable, stop and ask for an ownership decision instead of merging assumptions.
- Do not overwrite, revert, stage, or commit changes created by the other runtime unless explicitly instructed.

## High-Value Files

| Need | Location |
| --- | --- |
| CLI entry point | `edgar_warehouse/cli.py` |
| Runtime command shim | `edgar_warehouse/runtime.py` |
| Command registry and workflows | `edgar_warehouse/application/` |
| Runtime settings | `edgar_warehouse/infrastructure/warehouse_settings.py` |
| Object storage adapter | `edgar_warehouse/infrastructure/object_storage.py` |
| Bronze path catalog | `edgar_warehouse/infrastructure/dataset_path_catalog.py` |
| Packaged path templates | `edgar_warehouse/config/warehouse_paths.properties` |
| Silver transforms | `edgar_warehouse/silver.py` |
| Gold export/aggregation | `edgar_warehouse/gold.py` |
| Ownership parser | `edgar_warehouse/parsers/ownership.py` |
| ADV parser | `edgar_warehouse/parsers/adv.py` |
| AWS account Terraform | `infra/terraform/accounts/{dev,prod}/` |
| AWS access Terraform | `infra/terraform/access/aws/accounts/{dev,prod}/` |
| AWS Terraform modules | `infra/terraform/modules/` |
| Snowflake AWS native-pull Terraform | `infra/terraform/snowflake/accounts/{dev,prod}/` |
| Snowflake access Terraform | `infra/terraform/access/snowflake/accounts/{dev,prod}/` |
| dbt gold models | `infra/snowflake/dbt/edgartools_gold/` |
| AWS deploy/publish scripts | `infra/scripts/deploy-aws-application.sh`, `infra/scripts/publish-warehouse-image.sh` |
| AWS MDM scripts | `infra/scripts/bootstrap-aws-mdm-secrets.sh`, `infra/scripts/audit-mdm-snowflake-postgres-cutover.py`, `infra/scripts/remove-aws-mdm-rds-after-cutover.sh`, `infra/scripts/run-aws-mdm-e2e.sh` |
| Docker images | `Dockerfile`, `Dockerfile.warehouse-deps`, `Dockerfile.mdm-deps`, `Dockerfile.mdm-neo4j` |

Large files should be read in chunks before editing: `edgar_warehouse/runtime.py`, `edgar_warehouse/silver.py`, and `edgar_warehouse/gold.py`.

## Tooling Rules

- Use `uv` for Python dependency management and Python command execution.
- Do not use bare `pip` for repo workflows. Use `uv sync`, `uv pip install` for deliberate one-off installs, or `uv run --with <package>` for transient tools.
- Prefer `uv run --with dbt-snowflake dbt ...` over bare `dbt`.
- Project dependency source is PyPI. `edgartools>=5.29.0` is not vendored here.
- Docker images use AWS ECR for deployable artifacts.
- On macOS, use Colima for local Docker fast feedback. On Linux/CI, `docker buildx` with registry cache is the default path.

## GoF Design Review

- Before writing or modifying code, use the `gof-refactor-reviewer` skill to review the relevant existing code and its git history for evidence-backed Gang of Four refactoring opportunities. If the work is a new design with no existing code to review, use `gof-pattern-selector` instead.
- During code review, explicitly check whether `gof-refactor-reviewer` is available. When available, invoke it as part of the review; when unavailable, state that limitation and perform a focused manual design-pattern review.
- Do not force a design pattern into the code. Follow the skill's default of leaving the current design in place unless demonstrated change history and present-day costs justify the refactor.

Common setup:

```bash
uv sync --extra s3 --extra snowflake

# MDM runtime/dev work when needed:
uv sync --extra s3 --extra mdm-runtime
```

## Runtime Settings

Warehouse commands require:

```bash
export EDGAR_IDENTITY="EdgarTools Platform thepaulananth@gmail.com"
export WAREHOUSE_ENVIRONMENT="dev"
export WAREHOUSE_RUNTIME_MODE="bronze_capture"
export WAREHOUSE_BRONZE_ROOT="s3://edgartools-dev-bronze/warehouse/bronze"
export WAREHOUSE_STORAGE_ROOT="s3://edgartools-dev-warehouse/warehouse"
export SERVING_EXPORT_ROOT="s3://edgartools-dev-snowflake-export/warehouse/artifacts/snowflake_exports/"
export MDM_DATABASE_URL="postgresql://postgres:test@localhost:5432/mdm"
export AWS_DEFAULT_REGION=us-east-1
```

Notes:

- `EDGAR_IDENTITY` must include an email address or the runtime rejects the command.
- `WAREHOUSE_RUNTIME_MODE` is `bronze_capture` or `infrastructure_validation`.
- Gold-affecting commands require `SERVING_EXPORT_ROOT`; `SNOWFLAKE_EXPORT_ROOT` is accepted as a compatibility fallback.
- For AWS work, prefer S3 roots. Do not introduce other storage roots into new AWS guidance.

## Data And Parser Notes

- Raw SEC download and bronze persistence are implemented by this repo, not by `edgartools`.
- `edgartools` currently enters the warehouse runtime for Forms 3, 4, and 5 ownership parsing through `edgar.ownership.Ownership.from_xml(...)`.
- ADV parsing is local in `edgar_warehouse/parsers/adv.py`.
- SEC filing artifacts are additive and immutable after capture.
- Loaders should skip already loaded SEC files by default. Use explicit `--force` only for operator repair.
- When bumping `edgartools`, run the relevant scripts in `scripts/batch/` to smoke-test parser surfaces.

## AWS Terraform Model

AWS Terraform is split into passive infrastructure and access control.

Passive infrastructure roots:

```text
infra/terraform/bootstrap-state/
infra/terraform/accounts/dev/
infra/terraform/accounts/prod/
```

Access-control roots:

```text
infra/terraform/access/aws/accounts/dev/
infra/terraform/access/aws/accounts/prod/
```

Passive AWS Terraform creates infrastructure shells only:

- VPC, public subnets, route table, internet gateway, and S3 VPC endpoint.
- Outbound-only ECS task security group.
- S3 bronze bucket, warehouse bucket, and Snowflake export bucket.
- KMS key for Snowflake export artifacts.
- ECR warehouse repository.
- ECS cluster and CloudWatch log group.
- SNS topic for Snowflake manifest events.
- Empty Secrets Manager containers.
- Empty MDM Secrets Manager containers for Snowflake Postgres, Neo4j, API keys, and Snowflake graph/export settings.

AWS Terraform must not create runnable ECS task definitions, Step Functions state machines, schedules, workload commands, image rollouts, or runtime secret values. Those are explicit operator actions.

Default S3 bucket names:

S3 bucket names are globally unique, so data buckets include the 12-digit AWS account ID suffix. The non-S3 resource prefix remains `edgartools-<env>` unless a Terraform variable overrides it.

| Env | Bronze bucket | Warehouse bucket | Snowflake export bucket | Prefix |
| --- | --- | --- | --- | --- |
| dev | `edgartools-dev-bronze-<aws_account_id>` | `edgartools-dev-warehouse-<aws_account_id>` | `edgartools-dev-snowflake-export-<aws_account_id>` | `edgartools-dev` |
| prod | `edgartools-prod-bronze-<aws_account_id>` | `edgartools-prod-warehouse-<aws_account_id>` | `edgartools-prod-snowflake-export-<aws_account_id>` | `edgartools-prod` |

Important differences:

- `dev` uses destroyable bucket modules and ECR `force_delete = true`.
- `prod` uses protected storage; the bronze bucket has `prevent_destroy = true`.
- S3 backend state locking uses `use_lockfile = true`; no DynamoDB lock table is required.

## AWS Principal Model

- Use an AWS admin profile for `bootstrap-state`, AWS provisioning Terraform, and AWS access Terraform.
- Use `sec_platform_deployer` for application rollout: image push, ECS task definitions, Step Functions state machines, and executions.
- Runtime uses service-assumed roles, not a runner IAM user:
  - `sec_platform_runner_execution`
  - `sec_platform_runner_task`
  - `sec_platform_runner_step_functions`
- Do not create runner access keys. `edgartools-<env>-runner-credentials` is a legacy empty container only.

## AWS Infra Flow

Bootstrap Terraform state:

```bash
export AWS_PROFILE=aws-admin-prod
cd infra/terraform/bootstrap-state
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

Apply passive AWS infrastructure:

```bash
cd infra/terraform/accounts/prod
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

Apply AWS access:

```bash
cd infra/terraform/access/aws/accounts/prod
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

Useful outputs:

```bash
terraform output ecr_repository_url
terraform output cluster_arn
terraform output public_subnet_ids
terraform output public_ecs_security_group_id
terraform output log_group_name
terraform output edgar_identity_secret_arn
terraform output snowflake_manifest_sns_topic_arn
terraform output snowflake_export_root_url
```

Populate the EDGAR identity secret out of band:

```bash
aws secretsmanager put-secret-value \
  --secret-id edgartools-prod-edgar-identity \
  --secret-string "Your Name your@email.com"
```

## AWS Image And Application Rollout

Deploy active AWS components outside Terraform:

```bash
bash infra/scripts/deploy-aws-application.sh \
  --env prod \
  --aws-profile sec_platform_deployer \
  --aws-region us-east-1 \
  --build-image \
  --publish-mode linux \
  --output-file infra/aws-prod-application.json
```

The deploy script can:

- Build and push the warehouse image.
- Register ECS Fargate task definitions.
- Create or update Step Functions state machines.
- Discover passive resources from Terraform outputs.
- Deploy MDM task definitions/state machines when `--enable-mdm` is used and MDM secret ARNs exist.

Standalone image publish. One shared repo (`edgartools-<env>-images`) holds
both warehouse and mdm images (final and deps); role is encoded in the tag
prefix, applied automatically from `--role`:

```bash
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-images \
  --role warehouse \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev
```

Use `--role mdm` with the same `--ecr-repository edgartools-<env>-images` when
publishing the separate MDM image — it lands as `mdm-*` tags instead of
`warehouse-*`.

Image tags (role-prefixed: `warehouse-*` / `mdm-*`):

- `warehouse-dev` / `mdm-dev`: mutable latest dev image, per role.
- `warehouse-sha-<hash>` / `mdm-sha-<hash>`: immutable rollback/audit tag, per role.
- `warehouse-prod` / `mdm-prod`: manually promoted production tag, per role.

## ECS Cost-Sizing Evidence Rules

- Size for cost per **successful validated output**, not for low CPU/memory or
  a Step Functions `SUCCEEDED` status alone. A profile change needs repeated
  current-image candidate runs and a matched control with the same immutable
  orchestration, input envelope, and record funnel.
- Promotion is fail-closed unless correctness, completeness, identity parity,
  recovery, and cross-run idempotency pass; candidate p95 duration is no more
  than 5% slower; and validated-output cost is at least 10% lower.
- Ticket 28 rejected the `mdm.residual_security` medium downgrade despite low
  memory use and three execution-local successes: cross-run idempotency failed,
  shared mutable input broke control-funnel comparability, equal-work
  `MdmSecurities` was 17.07% slower, and comparable p95 cost improvement was
  not demonstrated.
  Keep `mdm-large` operational for this workload; do not infer that
  `mdm-small` is safe or change production references from this cohort.
- The current-image unbounded `sync-graph` canary on `mdm-large` passed its
  execution-local gates. This does not approve the residual-security profile
  downgrade.
- Do not run candidate and control concurrently against the same mutable MDM
  state. Any residual-pipeline parallelization must first pass the disposable
  two-wave canary in `.scratch/ecs-parallel-runs/`, including failure,
  retry/recovery, parity, quota, p95, and validated-output cost gates; only then
  may its implementation ticket proceed.
- Canonical Ticket 28 analysis and durable evidence live in
  `.scratch/ecs-cost-sizing/issues/28-run-mdm-residual-security-medium-canaries-and-unbounded-graph-sync-canary.md`
  and `.scratch/ecs-cost-sizing/evidence/ticket28/`.

## Warehouse Commands

Core CLI commands live in `edgar_warehouse/cli.py`:

```bash
edgar-warehouse --help
edgar-warehouse seed-universe --limit 100
edgar-warehouse bootstrap --tracking-status-filter active
edgar-warehouse bootstrap-full --tracking-status-filter active
edgar-warehouse bootstrap-next --limit 100
edgar-warehouse bootstrap-batch --cik-list 0000320193,0000789019
edgar-warehouse daily-incremental --start-date YYYY-MM-DD --end-date YYYY-MM-DD
edgar-warehouse load-daily-form-index-for-date YYYY-MM-DD
edgar-warehouse catch-up-daily-form-index --end-date YYYY-MM-DD
edgar-warehouse targeted-resync --scope-type cik --scope-key 0000320193
edgar-warehouse full-reconcile --sample-limit 100
```

Step Functions execution example:

```bash
STATE_MACHINE_ARN="$(
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["state_machines"]["bootstrap"])' \
    infra/aws-prod-application.json
)"

aws stepfunctions start-execution \
  --profile sec_platform_deployer \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --input '{"trigger":"operator","workflow":"bootstrap"}'
```

For bounded replay:

```bash
aws stepfunctions start-execution \
  --profile sec_platform_deployer \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --input '{"trigger":"operator","workflow":"bootstrap","cik_list":"0000320193,0000789019"}'
```

## AWS MDM

MDM runtime writes use Snowflake Postgres through `MDM_DATABASE_URL`. AWS Terraform manages only empty Secrets Manager containers:

- `edgartools-<env>/mdm/postgres_dsn`
- `edgartools-<env>/mdm/neo4j`
- `edgartools-<env>/mdm/api_keys`
- `edgartools-<env>/mdm/snowflake`

Populate the MDM PostgreSQL DSN with the Snowflake Postgres `application` role DSN:

```bash
printf '%s' "$SNOWFLAKE_APPLICATION_MDM_DSN" | \
  bash infra/scripts/bootstrap-aws-mdm-secrets.sh \
    --env dev \
    --aws-profile aws-admin-dev \
    --aws-region us-east-1 \
    --dsn-stdin
```

Then deploy app components with MDM enabled:

```bash
bash infra/scripts/deploy-aws-application.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --aws-region us-east-1 \
  --skip-build \
  --image-ref <warehouse-image-digest-ref> \
  --mdm-image-ref <mdm-image-digest-ref> \
  --enable-mdm \
  --mdm-database-source snowflake-postgres \
  --output-file infra/aws-dev-application.json
```

Snowflake Postgres cutover and RDS removal runbook:

```bash
docs/aws-mdm-snowflake-postgres-cutover.md
```

MDM CLI commands:

```bash
edgar-warehouse mdm check-connectivity --neo4j
edgar-warehouse mdm migrate
edgar-warehouse mdm seed-universe --tracking-status bootstrap_pending
edgar-warehouse mdm run --entity-type all --limit 100
edgar-warehouse mdm derive-relationships --target-per-type 100
edgar-warehouse mdm sync-graph --limit 100
edgar-warehouse mdm verify-graph
edgar-warehouse mdm counts
```

AWS-only MDM e2e:

```bash
bash infra/scripts/run-aws-mdm-e2e.sh --env dev --aws-profile sec_platform_deployer
bash infra/scripts/run-aws-mdm-e2e.sh --env dev --status-only
```

## Snowflake Native S3 Pull

Snowflake is the analytics target for the AWS path. Use the wrapper for normal AWS/Snowflake native-pull deployment:

```bash
bash infra/scripts/deploy-snowflake-stack.sh \
  --env prod \
  --snow-connection edgartools-prod
```

The wrapper coordinates:

1. AWS access bootstrap apply with temporary Snowflake trust and deterministic external ID.
2. Snowflake provisioning for storage integration, S3 stage, source mirror tables, pipe, stream, procedures, and task.
3. AWS access reconcile apply narrowed to the Snowflake-managed AWS principal.
4. Snowflake provisioning re-apply.
5. Snowflake access Terraform apply.
6. Optional native-pull validation, dbt run/test, and dashboard upload.

Useful flags:

```bash
bash infra/scripts/deploy-snowflake-stack.sh --env-name prod --snow-connection edgartools-prod --run-validation
bash infra/scripts/deploy-snowflake-stack.sh --env-name prod --snow-connection edgartools-prod --run-dbt
bash infra/scripts/deploy-snowflake-stack.sh --env-name prod --snow-connection edgartools-prod --upload-dashboard
```

Native-pull gotchas:

- `snowflake_export_root_url` must include the trailing slash on `snowflake_exports/`.
- Capture `snowflake_manifest_sns_topic_arn` from AWS provisioning outputs.
- The SnowCLI connection must exist before running the wrapper.
- Snowflake Enterprise or higher is required for dynamic tables.

### Dev Snowflake Connection

For all local verification, DDL deployment, and `snow sql` commands targeting the dev Snowflake account, always use:

```bash
export SNOW_CONNECTION=snowconn
```

The `snowconn` connection uses ACCOUNTADMIN role, which is required for `CREATE STORAGE INTEGRATION` (needed by `01_source_stage.sql`) and all other DDL operations in the dev account. Do not use `YG91578` or `edgartools-dev` for verification scripts — those connections lack the required privileges.

## dbt And Dashboard

dbt project root:

```bash
cd infra/snowflake/dbt/edgartools_gold
```

Use environment-backed profiles:

```bash
cp profiles.yml.example profiles.yml
export DBT_SNOWFLAKE_ACCOUNT="ORGNAME-ACCOUNTNAME"
export DBT_SNOWFLAKE_USER="your_user"
export DBT_SNOWFLAKE_PASSWORD="your_password"
export DBT_SNOWFLAKE_ROLE="EDGARTOOLS_PROD_DEPLOYER"
export DBT_SNOWFLAKE_DATABASE="EDGARTOOLS_PROD"
export DBT_SNOWFLAKE_WAREHOUSE="EDGARTOOLS_PROD_REFRESH_WH"
```

Run with `uv`:

```bash
uv run --with dbt-snowflake dbt deps
uv run --with dbt-snowflake dbt compile --target prod
uv run --with dbt-snowflake dbt run --target prod
uv run --with dbt-snowflake dbt test --target prod
```

Dashboard artifact upload:

```bash
SNOW_CONNECTION=edgartools-prod \
DASHBOARD_DATABASE=EDGARTOOLS_PROD \
bash infra/snowflake/streamlit/deploy.sh
```

## Tests And Verification

Fast local tests:

```bash
uv run pytest tests/unit tests/architecture
```

MDM tests:

```bash
uv run pytest tests/mdm
```

Validation checks after deploy:

```bash
edgar-warehouse --help
python -c "from edgar_warehouse.cli import main; print('OK')"
uv run --with dbt-snowflake dbt test --target prod
```

Snowflake status query:

```sql
SELECT *
FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS
LIMIT 10;
```

## Safety Rules

- Do not commit local secrets, `.tfvars` with live values, generated Terraform state, or application JSON containing sensitive values.
- Do not put image digests, workflow rollout, schedules, or EDGAR identity values into AWS Terraform inputs.
- Do not change the ownership parser import without checking the `edgartools` changelog:

```python
from edgar.ownership import Ownership

parsed = Ownership.from_xml(content)
```

- Do not broaden IAM policies casually. Keep runner roles service-assumed and scoped.
- Do not remove S3 object/versioning/encryption/public-access protections.
- Do not destroy prod bronze storage without an explicit operator request and a reviewed migration plan.
- Preserve loader idempotency: default behavior skips already captured SEC files; repair paths require `--force`.
