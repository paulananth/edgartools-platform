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

### ⚠️ Known issue: stale `edgar-identity` secret ARN breaks ALL ECS task launches

**Symptom:** Every ECS task registered by this deploy (`small`, `medium`, `large`,
`mdm-small`, `mdm-medium` — not just MDM) fails to start with:

```
ResourceInitializationError: unable to pull secrets or registry auth: ...
AccessDeniedException: ... is not authorized to perform secretsmanager:GetSecretValue
on resource: arn:aws:secretsmanager:...:secret:edgartools-dev-edgar-identity-<OLD_SUFFIX>
```

**Root cause:** AWS Secrets Manager appends a random 6-character suffix to a
secret's ARN (e.g. `edgartools-dev-edgar-identity-ptNAkm`); the suffix changes
whenever the secret is *recreated* (not merely value-rotated — e.g. after a
credential-exposure incident that requires deleting and recreating the secret).
`deploy-aws-application.sh` resolves `EDGAR_IDENTITY_SECRET_ARN` via
`first_nonempty(<flag>, manifest_value(...), secret_arn_by_name(...))` — it
**prefers a cached ARN from the previous run's `infra/aws-dev-application.json`
manifest over a live Secrets Manager lookup by name**. If the secret was
recreated since the last successful deploy, the cached ARN in the manifest is
stale, the deploy silently writes broken task definitions referencing a
nonexistent secret, and *every* subsequent ECS task launch fails at
`ResourceInitializationError` (before the container even starts) — masquerading
as a connectivity problem when run via `mdm-check-connectivity`.

**This bit us live during the Snowflake Postgres cutover** (2026-06-08): the
`edgar-identity` secret had been recreated on 2026-06-05 during an unrelated
credential-exposure incident (suffix changed `UMvCTb` → `ptNAkm`), the cached
manifest still had `UMvCTb`, and Step 4's redeploy registered new revisions of
**every** task definition pointing at the dead `UMvCTb` ARN.

**Fix applied:** re-run the deploy passing `--edgar-identity-secret-arn`
explicitly with the *live* ARN (look it up fresh, don't trust the manifest):

```bash
LIVE_EDGAR_IDENTITY_ARN=$(aws secretsmanager describe-secret \
  --secret-id edgartools-dev-edgar-identity --region us-east-1 \
  --query ARN --output text)

bash infra/scripts/deploy-aws-application.sh \
  --env dev --aws-profile sec_platform_deployer --aws-region us-east-1 \
  --skip-build \
  --image-ref <warehouse-image-digest-ref> \
  --mdm-image-ref <mdm-image-digest-ref> \
  --enable-mdm \
  --mdm-database-source snowflake-postgres \
  --edgar-identity-secret-arn "$LIVE_EDGAR_IDENTITY_ARN" \
  --output-file infra/aws-dev-application.json
```

**Recommended permanent fix (not yet applied):** change
`deploy-aws-application.sh`'s precedence to prefer a live `secret_arn_by_name`
lookup over the cached manifest value (or drop the manifest fallback entirely),
so a recreated secret can never leave a stale ARN cached across deploys. Until
that's fixed, **always pass `--edgar-identity-secret-arn` explicitly with a
freshly looked-up ARN** when redeploying after any secret recreation/rotation —
do not rely on `--skip-build`'s default manifest-based resolution.

### ⚠️ Known issue: deploy's own ECR cleanup deletes the digest it's about to deploy

**Symptom:** ECS task fails with:

```
CannotPullContainerError: failed to resolve ref ...@sha256:<digest>: not found
```
on a task definition that the *same deploy run* just registered, referencing
the *same digest* passed via `--image-ref`/`--mdm-image-ref`.

**5-Whys root cause:**
1. The ECS task can't pull `sha256:46f7a36a...` — `ImageNotFoundException`, the
   digest no longer exists in ECR.
2. It no longer exists because `deploy-aws-application.sh`'s "Cleaning up stale
   ECR images" step deleted it — *during the same invocation* that registered
   the task definition referencing it.
3. The cleanup deleted an image its own run was actively deploying because its
   retention rule ("keep `:dev` + 2 newest `:sha-*` tags per repo") runs as an
   independent pass with **no cross-check** against the `--image-ref`/
   `--mdm-image-ref` digest the same invocation just resolved and is about to
   deploy.
4. The retention rule didn't protect that digest because it was tagged `dev` +
   `0bb535b` — a bare short-commit-hash, **not** the `sha-<12-char-hash>`
   pattern the cleanup's "keep 2 newest `:sha-*`" matcher recognizes — so it
   wasn't counted as keep-worthy and was pruned as stale.
5. That image carried a non-matching tag because it was produced by an earlier
   publish run (2026-06-07) using a short-commit-hash + `:dev` convention,
   which **doesn't match** the `:sha-<hash>` convention documented in the
   platform's image-tagging strategy and assumed by the cleanup matcher.

**Root cause:** a tag-naming-convention mismatch between the image-publish
process (`0bb535b` + `:dev`) and the deploy script's ECR cleanup retention
pattern (`sha-<hash>` + `:dev`), compounded by the cleanup step having no
awareness of the digest the same run is about to deploy — so the only
candidate image newer than the prune cutoff was deleted out from under its
own freshly-registered task definition.

**Fix applied:** re-resolve the *live* (post-cleanup) digests immediately
before redeploying — do not reuse cached `--image-ref`/`--mdm-image-ref`
values from a prior invocation of this same script:

```bash
WAREHOUSE_REF=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageDigest" --output text \
  | xargs -I{} echo "690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-warehouse@{}")
MDM_REF=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-mdm \
  --query "sort_by(imageDetails,&imagePushedAt)[-1].imageDigest" --output text \
  | xargs -I{} echo "690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-mdm@{}")
```

**Recommended permanent fix (not yet applied):** either (a) make the cleanup
step's keep-pattern also recognize bare short-commit-hash tags (or whatever
tags the publish pipeline actually produces), or (b) have the cleanup
explicitly exclude the digest(s) passed via `--image-ref`/`--mdm-image-ref`
from deletion regardless of tag pattern. Until fixed, **re-resolve digests
fresh immediately before each `deploy-aws-application.sh` invocation** —
never reuse a digest ref captured before a prior run of this script, since
that prior run's cleanup may have already deleted it.

## 4b. Regenerate MDM Data From Silver (ECS)

Because the Snowflake Postgres instance is network-isolated (no bastion, no
local VPC access), `pg_dump`/`pg_restore` from the RDS source is unreachable
from a developer laptop. Instead, regenerate every entity domain by re-running
MDM's silver-reader pipeline from ECS — same network path the runtime uses.
Run domains in parallel where possible; relationships must come last.

```bash
# Template — replace <DOMAIN> with: company, adviser, security, person, fund
SG=$(cat /tmp/mdm-cutover-secrets/sg.txt)
aws ecs run-task \
  --region us-east-1 \
  --cluster edgartools-dev-warehouse \
  --task-definition edgartools-dev-mdm-medium:69 \
  --launch-type FARGATE \
  --network-configuration "{\"awsvpcConfiguration\":{\"subnets\":[\"subnet-070406420a32a17c5\"],\"securityGroups\":[\"$SG\"],\"assignPublicIp\":\"ENABLED\"}}" \
  --overrides '{"containerOverrides":[{"name":"edgar-warehouse","command":["mdm","run","--entity-type","<DOMAIN>"],"environment":[{"name":"WAREHOUSE_RUNTIME_MODE","value":"bronze_capture"},{"name":"WAREHOUSE_BRONZE_ROOT","value":"s3://edgartools-dev-bronze/warehouse/bronze"},{"name":"WAREHOUSE_STORAGE_ROOT","value":"s3://edgartools-dev-warehouse/warehouse"},{"name":"SERVING_EXPORT_ROOT","value":"s3://edgartools-dev-snowflake-export/warehouse/artifacts/snowflake_exports/"},{"name":"EDGAR_IDENTITY","value":"EdgarTools Platform thepaulananth@gmail.com"}]}]}'
```

After all entity domains complete, run relationship derivation with the **separate
`derive-relationships` subcommand** (not `run --entity-type`):

```bash
aws ecs run-task \
  --region us-east-1 \
  --cluster edgartools-dev-warehouse \
  --task-definition edgartools-dev-mdm-medium:69 \
  --launch-type FARGATE \
  --network-configuration "{\"awsvpcConfiguration\":{\"subnets\":[\"subnet-070406420a32a17c5\"],\"securityGroups\":[\"$SG\"],\"assignPublicIp\":\"ENABLED\"}}" \
  --overrides '{"containerOverrides":[{"name":"edgar-warehouse","command":["mdm","derive-relationships"],"environment":[{"name":"WAREHOUSE_RUNTIME_MODE","value":"bronze_capture"},{"name":"WAREHOUSE_BRONZE_ROOT","value":"s3://edgartools-dev-bronze/warehouse/bronze"},{"name":"WAREHOUSE_STORAGE_ROOT","value":"s3://edgartools-dev-warehouse/warehouse"},{"name":"SERVING_EXPORT_ROOT","value":"s3://edgartools-dev-snowflake-export/warehouse/artifacts/snowflake_exports/"},{"name":"EDGAR_IDENTITY","value":"EdgarTools Platform thepaulananth@gmail.com"}]}]}'
```

Check completion (ECS task history expires quickly — use CloudWatch):

```bash
aws logs filter-log-events \
  --region us-east-1 \
  --log-group-name /aws/ecs/edgartools-dev-warehouse \
  --log-stream-names "mdm-mdm-medium/edgar-warehouse/<TASK_ID>" \
  --filter-pattern "mdm_command_completed" \
  --query 'events[*].message' --output text
```

Observed throughput (2026-06-08, mdm-medium, Snowflake Postgres):

| Domain | Rows | Duration |
|--------|------|----------|
| companies | 5,500 | ~49 min |
| persons | 25,647 | ~94 min |
| securities | 37,102 | ~155 min |
| relationships | TBD | TBD |

### ⚠️ Known issue: `mdm run --entity-type relationships` is not a valid command

**Symptom:** ECS task exits with code 2 immediately:

```
edgar-warehouse mdm run: error: argument --entity-type: invalid choice: 'relationships'
(choose from company, adviser, security, person, fund, all)
```

**Root cause:** `relationships` is not a valid `--entity-type` value for `mdm run`.
Relationship derivation is a separate pipeline stage exposed via its own subcommand
`mdm derive-relationships`, not via `mdm run`. The MDM CLI has three distinct
relationship commands:
- `mdm derive-relationships` — derives relationship instances from resolved entities + silver facts (no graph sync)
- `mdm load-relationships` — derives relationships AND optionally syncs to Snowflake graph tables
- `mdm backfill-relationships` — legacy backfill from `mdm_fund`/`mdm_security` tables

**Fix:** use `mdm derive-relationships` (not `mdm run --entity-type relationships`)
when running relationship derivation from ECS. This command runs after all entity
domains (`company`, `person`, `security`, etc.) have completed.

### ⚠️ Known issue: `mdm-check-connectivity` Step Functions state machine is broken

**Symptom:** `mdm-check-connectivity` Step Functions execution fails immediately.

**Root cause:** The `edgartools-dev-mdm-check-connectivity` state machine hardcodes
`--neo4j` in its ECS command override. The `--neo4j` flag was removed from the MDM
CLI in commit `8784fd5` when Neo4j was decommissioned. The state machine was never
updated, so every invocation fails at argument parsing before the container does any
useful work.

**Fix:** Do NOT use the `mdm-check-connectivity` Step Functions state machine. Run
connectivity checks directly via `ecs run-task` with command `["mdm","check-connectivity"]`
(no flags):

```bash
SG=$(cat /tmp/mdm-cutover-secrets/sg.txt)
aws ecs run-task \
  --region us-east-1 \
  --cluster edgartools-dev-warehouse \
  --task-definition edgartools-dev-mdm-medium:69 \
  --launch-type FARGATE \
  --network-configuration "{\"awsvpcConfiguration\":{\"subnets\":[\"subnet-070406420a32a17c5\"],\"securityGroups\":[\"$SG\"],\"assignPublicIp\":\"ENABLED\"}}" \
  --overrides '{"containerOverrides":[{"name":"edgar-warehouse","command":["mdm","check-connectivity"]}]}'
```

**Recommended permanent fix (not yet applied):** update the state machine definition
to remove `--neo4j` from the command override, or delete the state machine entirely
if connectivity checks are always run ad-hoc.

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
