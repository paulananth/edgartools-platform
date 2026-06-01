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

- Treat the current Codex work as protected unless the user explicitly hands it off.
- Prefer separate git worktrees or branches for concurrent Claude and Codex work.
- Use separate GSD workstream directories under `.planning/workstreams/<name>/`; do not edit another runtime's active workstream files.
- Before editing, run `git status --short` and inspect `.planning/active-workstream` when present.
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
| AWS MDM scripts | `infra/scripts/bootstrap-aws-mdm-secrets.sh`, `infra/scripts/run-aws-mdm-e2e.sh` |
| Docker images | `Dockerfile`, `Dockerfile.warehouse-deps`, `Dockerfile.mdm-deps`, `Dockerfile.mdm-neo4j` |

Large files should be read in chunks before editing: `edgar_warehouse/runtime.py`, `edgar_warehouse/silver.py`, and `edgar_warehouse/gold.py`.

## Tooling Rules

- Use `uv` for Python dependency management and Python command execution.
- Do not use bare `pip` for repo workflows. Use `uv sync`, `uv pip install` for deliberate one-off installs, or `uv run --with <package>` for transient tools.
- Prefer `uv run --with dbt-snowflake dbt ...` over bare `dbt`.
- Project dependency source is PyPI. `edgartools>=5.29.0` is not vendored here.
- Docker images use AWS ECR for deployable artifacts.
- On macOS, use Colima for local Docker fast feedback. On Linux/CI, `docker buildx` with registry cache is the default path.

Common setup:

```bash
uv sync --extra s3 --extra snowflake

# MDM runtime/dev work when needed:
uv sync --extra s3 --extra mdm-runtime
```

## Runtime Settings

Warehouse commands require:

```bash
export EDGAR_IDENTITY="Your Name your@email.com"
export WAREHOUSE_ENVIRONMENT="dev"
export WAREHOUSE_RUNTIME_MODE="bronze_capture"
export WAREHOUSE_BRONZE_ROOT="s3://edgartools-dev-bronze"
export WAREHOUSE_STORAGE_ROOT="s3://edgartools-dev-warehouse/warehouse"
export SERVING_EXPORT_ROOT="s3://edgartools-dev-snowflake-export/warehouse/artifacts/snowflake_exports/"
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
- Optional MDM RDS PostgreSQL data plane when `mdm_enabled = true`.

AWS Terraform must not create runnable ECS task definitions, Step Functions state machines, schedules, workload commands, image rollouts, or runtime secret values. Those are explicit operator actions.

Default resource names:

| Env | Bronze bucket | Warehouse bucket | Snowflake export bucket | Prefix |
| --- | --- | --- | --- | --- |
| dev | `edgartools-dev-bronze` | `edgartools-dev-warehouse` | `edgartools-dev-snowflake-export` | `edgartools-dev` |
| prod | `edgartools-prod-bronze` | `edgartools-prod-warehouse` | `edgartools-prod-snowflake-export` | `edgartools-prod` |

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

Standalone image publish:

```bash
bash infra/scripts/publish-warehouse-image.sh \
  --aws-region us-east-1 \
  --ecr-repository edgartools-dev-warehouse \
  --role warehouse \
  --image-tag sha-$(git rev-parse --short=12 HEAD) \
  --mode docker \
  --cache-from-tag dev \
  --also-tag dev
```

Use `--role mdm` with repository `edgartools-<env>-mdm` when publishing the separate MDM image.

Image tags:

- `dev`: mutable latest dev image.
- `sha-<hash>`: immutable rollback/audit tag.
- `prod`: manually promoted production tag.

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

Enable the AWS MDM data plane with `mdm_enabled = true` in the AWS account root. It creates:

- Private subnets.
- RDS PostgreSQL with encrypted gp3 storage.
- RDS security group allowing PostgreSQL only from the ECS task security group.
- AWS-managed RDS master user secret.
- Empty Secrets Manager containers for:
  - `edgartools-<env>/mdm/postgres_dsn`
  - `edgartools-<env>/mdm/neo4j`
  - `edgartools-<env>/mdm/api_keys`

Populate the MDM PostgreSQL DSN after Terraform apply:

```bash
bash infra/scripts/bootstrap-aws-mdm-secrets.sh \
  --env dev \
  --aws-profile aws-admin-dev \
  --aws-region us-east-1
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
  --output-file infra/aws-dev-application.json
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
bash infra/scripts/deploy-snowflake-stack.sh --env prod --run-validation
bash infra/scripts/deploy-snowflake-stack.sh --env prod --run-dbt
bash infra/scripts/deploy-snowflake-stack.sh --env prod --upload-dashboard
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
