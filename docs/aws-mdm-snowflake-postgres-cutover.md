# AWS MDM Snowflake Postgres Cutover

This runbook moves MDM runtime writes from AWS RDS PostgreSQL to Snowflake Postgres. Runtime code still reads `MDM_DATABASE_URL`; the cutover is instance provisioning, restore, Secrets Manager update, redeploy, audit, and RDS removal.

Snowflake Postgres is created with Snowflake SQL, not Terraform. The SQL syntax follows Snowflake's `CREATE POSTGRES INSTANCE` command reference: https://docs.snowflake.com/en/sql-reference/sql/create-postgres-instance

## 1. Provision Snowflake Postgres

Edit `infra/snowflake/postgres/mdm_create_instance.sql` for the target environment, then run it with Snowflake CLI credentials:

```bash
export SNOW_CONNECTION=snowconn
snow sql --connection "$SNOW_CONNECTION" --filename infra/snowflake/postgres/mdm_create_instance.sql
```

Capture the generated `snowflake_admin` and `application` credentials out of band. Keep the MDM database name `mdm` and schema `public`.

Create the runtime database before restore if the instance only has the default database:

```bash
psql "$SNOWFLAKE_ADMIN_POSTGRES_DSN" \
  --set=ON_ERROR_STOP=1 \
  --command "CREATE DATABASE mdm"
```

## 2. Restore RDS Into Snowflake Postgres

Use PostgreSQL 16 client tools:

```bash
pg_dump "$AWS_RDS_MDM_DSN" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file /tmp/mdm-rds.dump

pg_restore \
  --dbname "$SNOWFLAKE_ADMIN_MDM_DSN" \
  --no-owner \
  --role snowflake_admin \
  --clean \
  --if-exists \
  /tmp/mdm-rds.dump

psql "$SNOWFLAKE_ADMIN_MDM_DSN" \
  --set=ON_ERROR_STOP=1 \
  --file infra/snowflake/postgres/mdm_post_restore.sql
```

Compare source and target:

```bash
uv run --extra mdm-runtime python infra/scripts/compare-mdm-postgres-databases.py \
  --source-dsn "$AWS_RDS_MDM_DSN" \
  --target-dsn "$SNOWFLAKE_ADMIN_MDM_DSN" \
  --analyze-target
```

## 3. Write Runtime DSN

Write the Snowflake Postgres `application` role DSN to the existing AWS secret. Use `sslmode=require`.

```bash
printf '%s' "$SNOWFLAKE_APPLICATION_MDM_DSN" | \
  bash infra/scripts/bootstrap-aws-mdm-secrets.sh \
    --env dev \
    --aws-profile aws-admin-dev \
    --aws-region us-east-1 \
    --dsn-stdin
```

The helper validates the host suffix, database name, and `sslmode=require`, then writes only the secret value. It logs a masked DSN.

## 4. Redeploy AWS Runtime

Deploy with the Snowflake Postgres database source so the deploy script does not overwrite the secret from RDS:

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

## 5. Audit Gate

Before RDS removal, run:

```bash
python3 infra/scripts/audit-mdm-snowflake-postgres-cutover.py \
  --env dev \
  --aws-profile sec_platform_deployer \
  --aws-region us-east-1 \
  --run-runtime-smoke
```

The audit fails if:

- any deployed Step Functions execution is running.
- the MDM DSN secret does not resolve to a Snowflake Postgres host.
- warehouse or MDM task definitions do not inject the same `MDM_DATABASE_URL` secret ARN.
- deployed state machines reference stale task definition revisions.
- `mdm check-connectivity`, `mdm counts`, representative `mdm run`, or the warehouse tracked-CIK read smoke fails.

## 6. Remove AWS RDS

After the strict audit passes, remove the legacy RDS instance with no final snapshot and reconcile Terraform:

```bash
bash infra/scripts/remove-aws-mdm-rds-after-cutover.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --aws-region us-east-1 \
  --confirm-rds-removal
```

Terraform now owns the empty MDM secret containers from `warehouse_runtime`. RDS, private subnets, and the RDS security group are removed from the passive AWS account roots.
