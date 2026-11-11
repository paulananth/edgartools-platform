# AWS: Terraform, principals, infra flow, image publish, MDM, runtime settings

Moved out of AGENTS.md (ticket 63) unchanged: reference read when a task touches AWS. Before any AWS command, use the [aws-snowflake-operations](../../skills/aws-snowflake-operations/SKILL.md) skill: it holds the one live account and what is decommissioned.

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
- Do not create runner access keys. Runtime and deployment use IAM roles; the former
  `edgartools-<env>-runner-credentials` empty container is retired.

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

## AWS Image Publish

The AWS pipeline deploy script (`deploy-aws-application.sh`: ECS task
definitions and Step Functions) was retired with the commands it ran
(platform validation 2b, 2026-09-30). Terraform and the live AWS objects are
untouched until a teardown the operator approves. Publish images with
`infra/scripts/publish-warehouse-image.sh`.

## AWS MDM

MDM runtime writes use Snowflake Postgres through `MDM_DATABASE_URL`. AWS Terraform manages only empty Secrets Manager containers:

- `edgartools-<env>/mdm/postgres_dsn`
- `edgartools-<env>/mdm/snowflake`

The unused, never-populated `mdm/neo4j` and `mdm/api_keys` containers are
retired. Use `scripts/ops/delete_unused_aws_secrets.py` for reviewed cleanup;
its apply mode requires reconciled Terraform state and live no-use evidence.

Populate the MDM PostgreSQL DSN with the Snowflake Postgres `application` role DSN:

Write it to the secret `<prefix>/mdm/postgres_dsn` with `aws secretsmanager put-secret-value`, the value read from stdin and never printed.

Snowflake Postgres cutover and RDS removal runbook:

```bash
docs/aws-mdm-snowflake-postgres-cutover.md
```

MDM CLI commands (MDM only; the legacy MDM commands are deleted,
platform validation slice 2a):

```bash
edgar-warehouse mdm migrate --application-role <runtime-role>
edgar-warehouse mdm check-connectivity
edgar-warehouse mdm prepare-capture --source <source> ...
```

**One-time backfill CLIs must expose a `--limit`/bounded-sample mode, not just `--dry-run`.**
A full unbounded `--dry-run` still walks the entire live candidate set — for
`mdm collapse-attribute-stage-history` that was 139,349 entities at one
Postgres round trip each (~57ms/entity, cross-region latency), projecting a
multi-hour dry run just to confirm the logic works on real data. `--dry-run`
proves nothing a bounded sample (tens of rows) wouldn't also prove, at a
fraction of the cost — confirm on a small sample first, then either trust the
existing test suite + code review for the full run or let the full run
double as its own dry run (it's already the resumable, batched-commit path,
so an interrupted full run costs nothing extra to retry). Build the `--limit`
flag in from the start next time; retrofitting one after a slow prod dry run
is already underway is the wrong order.

## Runtime Settings

Warehouse commands require:

```bash
export EDGAR_IDENTITY="EdgarTools Platform thepaulananth@gmail.com"
export WAREHOUSE_ENVIRONMENT="dev"
export WAREHOUSE_RUNTIME_MODE="bronze_capture"
export WAREHOUSE_BRONZE_ROOT="s3://edgartools-dev-bronze/warehouse/bronze"
export WAREHOUSE_STORAGE_ROOT="s3://edgartools-dev-warehouse/warehouse"
export SERVING_EXPORT_ROOT="s3://edgartools-dev-snowflake-export/warehouse/artifacts/snowflake_exports/"
export AWS_DEFAULT_REGION=us-east-1
```

Notes:

- `EDGAR_IDENTITY` must include an email address or the runtime rejects the command.
- `WAREHOUSE_RUNTIME_MODE` is `bronze_capture` or `infrastructure_validation`.
- Gold-affecting commands require `SERVING_EXPORT_ROOT`; `SNOWFLAKE_EXPORT_ROOT` is accepted as a compatibility fallback.
- For AWS work, prefer S3 roots. Do not introduce other storage roots into new AWS guidance.
- Local MDM, RDM, Rules, Bookkeeping and Change Journal connections come from the shared server's private `worker.env`. See [Initialize shared local PostgreSQL](docs/local-agent-testing.md). Hosted MDM uses its secret. Never print either value.
