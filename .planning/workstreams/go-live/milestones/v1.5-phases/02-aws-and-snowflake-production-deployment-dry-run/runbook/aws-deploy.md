# AWS Production Deploy Runbook

This runbook documents the production AWS active-application deploy
(`infra/scripts/deploy-aws-application.sh --env prod`) and the ECR
image-promotion procedure (D-05/D-06). It is non-secret: every value below is
a placeholder, a `<DIGEST>` slot, or a freshly-resolved-at-runtime expression.
No ARNs, secret values, account locators with embedded secrets, or compiled
output are included.

Per D-05, `aws-admin-dev` and `aws-admin-prod` resolve to the SAME AWS account
(`077127448006`, IAM user `cli-access`). "Prod" is a same-account,
prefix-distinguished resource set (Terraform root
`infra/terraform/accounts/prod/`, `:prod`-tagged ECR images, a future
`infra/aws-prod-application.json`) — there is NO separate prod AWS account or
ECR registry.

## 1. ECR image promotion (`:dev` -> `:prod`, in place — D-06 / Pattern 3, interpretation A1)

Per D-05 + D-01/D-02, the only repos that exist are `edgartools-dev-warehouse`
and `edgartools-dev-mdm` — `edgartools-prod-warehouse`/`edgartools-prod-mdm` do
NOT exist and creating them would require a Terraform `apply` (out of scope).
**Interpretation A1 is therefore the only interpretation consistent with
D-05 + D-01 + D-02**: promotion means re-tagging the existing dev-named repos'
images with a `:prod` tag, in place, in the same account.

### 1a. Resolve current `:dev` digests (read-only, registry API)

```bash
# 1. Resolve current :dev image digests — read-only, no docker pull needed.
export ECR="077127448006.dkr.ecr.us-east-1.amazonaws.com"

WAREHOUSE_DEV_DIGEST=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --image-ids imageTag=dev \
  --query 'imageDetails[0].imageDigest' --output text)

MDM_DEV_DIGEST=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-mdm \
  --image-ids imageTag=dev \
  --query 'imageDetails[0].imageDigest' --output text)
```

This step is read-only and was run during Phase 2 (see
`evidence/aws.md` "Image-Promotion Digest Capture (read-only)") — both repos
resolved a digest in the standard `sha256:<64-hex-chars>` format. Digest
values themselves are not recorded in evidence (non-secret but ephemeral —
they change on every image rebuild).

### 1b. Re-tag as `:prod` within the same repo (state-changing — operator-executed at cutover, NOT run during Phase 2)

```bash
# 2. Re-tag :dev digest as :prod within the same repo via registry-side
#    manifest copy (no local docker pull/push, no Colima required).
WAREHOUSE_MANIFEST=$(aws ecr batch-get-image --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --image-ids imageDigest="$WAREHOUSE_DEV_DIGEST" \
  --query 'images[0].imageManifest' --output text)
aws ecr put-image --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --image-tag prod \
  --image-manifest "$WAREHOUSE_MANIFEST"

MDM_MANIFEST=$(aws ecr batch-get-image --region us-east-1 \
  --repository-name edgartools-dev-mdm \
  --image-ids imageDigest="$MDM_DEV_DIGEST" \
  --query 'images[0].imageManifest' --output text)
aws ecr put-image --region us-east-1 \
  --repository-name edgartools-dev-mdm \
  --image-tag prod \
  --image-manifest "$MDM_MANIFEST"
```

### 1c. Capture the immutable digest form for `--image-ref` / `--mdm-image-ref`

The digest is identical regardless of which tag points to it, so the values
captured in step 1a remain valid immediately after re-tagging:

```bash
echo "${ECR}/edgartools-dev-warehouse@${WAREHOUSE_DEV_DIGEST}"
echo "${ECR}/edgartools-dev-mdm@${MDM_DEV_DIGEST}"
```

**IMPORTANT — see section 4 (Pre-deploy ordering requirement):** the deploy
script in section 2 runs ECR cleanup BEFORE the deploy. Re-resolve these
digests immediately before invoking the deploy command, in the same session,
AFTER cleanup has run — never reuse a digest captured in an earlier session.

## 2. Production deploy command (`deploy-aws-application.sh --env prod`)

```bash
# 3. Freshly resolve the EDGAR identity secret ARN immediately before deploy
#    (matrix row "Stale edgar-identity secret ARN mitigation" — never reuse a
#    cached/manifest ARN value after secret recreation or rotation).
export EDGAR_IDENTITY_SECRET_ARN="$(aws secretsmanager describe-secret \
  --secret-id edgartools-prod-edgar-identity \
  --query ARN --output text)"

# 4. Run the production deploy with explicit image refs and MDM enabled.
bash infra/scripts/deploy-aws-application.sh \
  --env prod \
  --image-ref "077127448006.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-warehouse@<DIGEST>" \
  --mdm-image-ref "077127448006.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-mdm@<DIGEST>" \
  --enable-mdm \
  --skip-build \
  --edgar-identity-secret-arn "$EDGAR_IDENTITY_SECRET_ARN"
```

`<DIGEST>` is the `sha256:<64-hex-chars>` value captured (and re-resolved per
section 4) in step 1c — for `--image-ref`/`--mdm-image-ref` the full form is
`<repo-url>@sha256:<digest>`.

### Parameter resolution order

`deploy-aws-application.sh` resolves each required identifier in this order:

1. Explicit CLI flag (e.g. `--image-ref`, `--cluster-arn`, `--edgar-identity-secret-arn`).
2. `infra/aws-prod-application.json` manifest value, if the file is present
   (e.g. `manifest_value cluster.arn`, `manifest_value mdm.secrets.postgres_dsn`).
3. AWS API discovery / `edgartools-prod-*` naming convention (e.g.
   `${NAME_PREFIX}-warehouse-${ACCOUNT_ID}` for bucket names, IAM
   `get-role --role-name` lookups for execution/task/Step-Functions roles,
   `secretsmanager` lookups by fixed secret name for the EDGAR identity and
   MDM secrets, EC2 tag-based subnet/security-group discovery).

### `--skip-build` requires `--image-ref`

If `BUILD_IMAGE` is not enabled (i.e. `--skip-build` is passed, or no
`--build-image` flag is given) and `--image-ref` is empty, the script
hard-fails with `--skip-build requires --image-ref`. The documented command
above always supplies `--image-ref` together with `--skip-build`.

### `--enable-mdm` required secret names

`--enable-mdm` requires all four MDM Secrets Manager secret ARNs to resolve
(via `${NAME_PREFIX}/mdm/<name>` lookup, where `NAME_PREFIX=edgartools-prod`),
or the script hard-fails with `--enable-mdm requires MDM secret ARNs; missing: ...`.
The four required secret names (names only — Terraform creates these as empty
containers; Phase 3/MDM-01 populates values):

- `edgartools-prod/mdm/postgres_dsn`
- `edgartools-prod/mdm/neo4j`
- `edgartools-prod/mdm/api_keys`
- `edgartools-prod/mdm/snowflake`

These four names are recorded as required-identifier `BLOCKED` items in
`evidence/aws.md` ("Required MDM Secret Names") and in
`01-LAUNCH-GATE-MATRIX.md` `## Required Production Identifiers`.

### Identifiers the script hard-fails on today (prod passive infra not yet applied)

Because `infra/terraform/accounts/prod/` has not been `apply`'d (D-01/D-02 —
only a read-only `terraform plan` has been run, see `evidence/aws.md`), none
of the following identifiers can be discovered today, and the script
hard-fails on each if not supplied:

- ECS cluster ARN (`could not resolve ECS cluster ARN`)
- ECS cluster name (`could not resolve ECS cluster name`)
- ECR repository URL (`could not resolve ECR repository URL`)
- 3 S3 buckets: bronze, warehouse, Snowflake-export
  (`could not resolve {bronze,warehouse,snowflake export} bucket name`)
- EDGAR identity secret ARN (`could not resolve EDGAR identity secret ARN`)
- 3 IAM role ARNs: execution role, task role, Step Functions role
  (`could not resolve ECS task execution/task/Step Functions role ARN`)
- Public subnet IDs (`could not resolve public subnet IDs`)
- ECS security group IDs (`could not resolve ECS security group IDs`)

**This is the structural reason "AWS active application deploy
(`infra/scripts/deploy-aws-application.sh`)" stays `BLOCKED`** in
`01-LAUNCH-GATE-MATRIX.md` — every one of these identifiers depends on the
prod Terraform `network`/`storage`/`runtime` modules having been `apply`'d, which
is explicitly out of scope for Phase 2 (D-01). The 22 output names that WILL
supply most of these values once `apply` runs are listed in `evidence/aws.md`
(Phase 2 Pattern 1 terraform-plan section).

## 3. Seed production bronze from existing dev bronze

Run this once after prod passive storage exists and before the first production
bootstrap/capture workload. SEC filing artifacts in bronze are additive and
immutable after capture, so production can reuse the already-downloaded dev
bronze source files instead of re-fetching the same historical SEC artifacts.

Only copy the bronze source tree. Do not copy dev warehouse/silver/gold outputs
into prod, and do not use `--delete`: prod bronze is protected, append-only
launch input.

```bash
# 5. Resolve source/destination bronze roots after prod Terraform apply.
REPO_ROOT="$(git rev-parse --show-toplevel)"
export AWS_REGION="us-east-1"
export DEV_BRONZE_ROOT="s3://edgartools-dev-bronze-077127448006/warehouse/bronze/"

PROD_BRONZE_BUCKET="$(terraform -chdir="${REPO_ROOT}/infra/terraform/accounts/prod" output -raw bronze_bucket_name)"
export PROD_BRONZE_ROOT="s3://${PROD_BRONZE_BUCKET}/warehouse/bronze/"

# 6. Preview the one-time copy. Keep the dry-run summary as operator evidence,
#    but do not paste full object listings into launch evidence.
aws s3 sync "$DEV_BRONZE_ROOT" "$PROD_BRONZE_ROOT" \
  --source-region "$AWS_REGION" \
  --region "$AWS_REGION" \
  --size-only \
  --dryrun

# 7. Copy immutable bronze artifacts into prod. No --delete.
aws s3 sync "$DEV_BRONZE_ROOT" "$PROD_BRONZE_ROOT" \
  --source-region "$AWS_REGION" \
  --region "$AWS_REGION" \
  --size-only \
  --only-show-errors

# 8. Capture non-secret proof: source/destination prefixes, object count, and
#    total size only. Do not paste full key lists.
aws s3api list-objects-v2 \
  --bucket "$PROD_BRONZE_BUCKET" \
  --prefix "warehouse/bronze/" \
  --query '{object_count: length(Contents[]), total_bytes: sum(Contents[].Size)}' \
  --output json
```

After this copy, run normal production warehouse commands without `--force`.
The loaders should keep their default idempotent behavior and skip already
captured SEC files; use `--force` only for explicit operator repair. Daily or
bounded production capture still runs afterward to pick up any filings not
present in the dev bronze snapshot at copy time.

This step remains `BLOCKED` until prod passive infrastructure has been applied
and `terraform output -raw bronze_bucket_name` returns a live bucket name.

## 4. Pre-deploy ordering requirement (Pitfall 3 / matrix row "ECR cleanup deleting in-flight image digest mitigation")

**Known issue:** `deploy-aws-application.sh` unconditionally (non-fatally)
runs `cleanup-ecr-images.sh --env prod --apply` before any build/publish step,
with a retention policy of `:dev` (or `:prod`, mutable) plus the 2 newest
`:sha-<hash>` tags per repo. If a `:prod`-tagged image's only OTHER tag
(`:sha-<hash>`) falls outside that keep-2 window, cleanup can delete the
underlying image manifest even though a `:prod` tag still points at it —
leaving a previously-captured `--image-ref @sha256:<digest>` referencing a
now-deleted manifest (`ManifestNotFoundException` at deploy time).

**Required mitigation:** ALWAYS re-resolve `--image-ref`/`--mdm-image-ref`
digests (step 1a/1c above) IMMEDIATELY BEFORE the deploy invocation (step 4),
in the same shell session, AFTER any cleanup step has executed. Never reuse a
digest captured in an earlier session or a digest written into a stale
`infra/aws-prod-application.json`.

This ordering requirement is what keeps the "ECR cleanup deleting in-flight
image digest mitigation" matrix row addressed by runbook command/ordering
documentation, even though the row itself stays `BLOCKED` pending a real prod
deploy to prove the ordering in practice.

## 5. Generated manifest (`infra/aws-prod-application.json`)

Once a production deploy succeeds, `deploy-aws-application.sh` writes
`infra/aws-prod-application.json` (parallel to the existing
`infra/aws-dev-application.json`). Per the Generated-JSON Summary Rule
(`01-LAUNCH-GATE-MATRIX.md`, `evidence/aws.md`), this file is summarized only
as:

- file presence,
- top-level keys (expected to match the dev manifest's set: `bronze_bucket_name`,
  `cluster`, `ecr_repository_url`, `edgar_identity_secret_arn`, `environment`,
  `execution_role_arn`, `image_ref`, `log_groups`, `mdm`, `mdm_image_ref`,
  `name_prefix`, `region`, `snowflake_export_bucket_name`, `state_machines`,
  `step_functions_role_arn`, `task_definitions`, `task_role_arn`,
  `warehouse_bucket_name`),
- the `state_machines` key-name list,
- `image_ref`/`mdm_image_ref` FORMAT only (`@sha256:` digest vs mutable tag).

The JSON body is never pasted into evidence files or this runbook.

## References

- `infra/scripts/deploy-aws-application.sh` — read in full for flag inventory,
  resolution order, and hard-fail identifiers (Phase 2 research session).
- `infra/scripts/cleanup-ecr-images.sh` — retention policy (`:dev`/`:prod` +
  2 newest `:sha-*` per repo).
- `01-LAUNCH-GATE-MATRIX.md` rows "AWS passive infrastructure outputs",
  "Production bronze data reuse from dev bronze",
  "AWS active application deploy (`infra/scripts/deploy-aws-application.sh`)",
  "Stale `edgar-identity` secret ARN mitigation", "ECR cleanup deleting
  in-flight image digest mitigation".
- `evidence/aws.md` — Phase 2 Pattern 1 terraform-plan evidence and
  image-digest-format capture.
