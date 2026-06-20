# AWS Evidence - Phase 1 Production Readiness

Date: 2026-06-14 UTC
Environment: production required; dev rows are precedent only and require separate production proof.
AWS profile: production profile required; dev status check used `sec_platform_deployer`.
AWS account: production account label required; dev status check referenced the dev account only.

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, full task logs, secret ARNs, and raw Native App job logs.

## Source-Of-Truth Note

Live AWS discovery and command checks are authoritative for production readiness. Deployment manifests and documentation are supporting evidence only. Generated JSON is summarized as file presence, top-level keys, state-machine names, and image-ref format; the JSON body is not pasted.

## Phase 1 Read-Only Checks Actually Run

```bash
ls -l infra/aws-dev-application.json infra/aws-prod-application.json
```

Result: failed for production manifest presence; succeeded for dev manifest presence.

- `infra/aws-dev-application.json`: present.
- `infra/aws-prod-application.json`: absent.
- Production app summary gate remains blocked until live discovery or a successful production deploy creates equivalent evidence.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Production AWS application manifest (infra/aws-prod-application.json)`.

```bash
jq -r 'keys | join(", ")' infra/aws-dev-application.json
jq -r '.state_machines // {} | keys[]' infra/aws-dev-application.json
```

Result: succeeded.

Non-secret dev manifest summary:

- Top-level keys present: `bronze_bucket_name`, `cluster`, `ecr_repository_url`, `edgar_identity_secret_arn`, `environment`, `execution_role_arn`, `image_ref`, `log_groups`, `mdm`, `mdm_image_ref`, `name_prefix`, `region`, `snowflake_export_bucket_name`, `state_machines`, `step_functions_role_arn`, `task_definitions`, `task_role_arn`, `warehouse_bucket_name`.
- State-machine keys include bootstrap, daily/index workflows, gold refresh, and MDM hosted graph workflows.
- This is dev supporting context only. It is not production proof.

```bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --status-only
```

Result: succeeded.

Relevant non-secret dev Step Functions status:

| Workflow | Latest status | Latest execution name |
| --- | --- | --- |
| `mdm_migrate` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-migrate` |
| `mdm_run` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-run` |
| `mdm_backfill_relationships` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-backfill` |
| `mdm_sync_graph` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-sync` |
| `mdm_verify_graph` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-verify` |
| `mdm_counts` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-counts` |

The command also reported lingering Neo4j references in the dev deployment summary and deploy script. Per the hosted graph precedent, those are warning-only in dev unless they block `mdm_sync_graph` or `mdm_verify_graph`, but production dashboard/runbook cleanup remains blocked in the launch matrix.

## Not-Yet-Runnable Production Steps

- PASS - see `01-LAUNCH-GATE-MATRIX.md` row `AWS passive infrastructure outputs` (resolved Phase 6 plan 06-01).
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Production bronze data reuse from dev bronze` (prerequisite bucket now exists; sync not yet run, out of Phase 6 scope).
- PASS - see `01-LAUNCH-GATE-MATRIX.md` row `Production AWS application manifest (infra/aws-prod-application.json)` (resolved Phase 6 plan 06-02).
- PASS - see `01-LAUNCH-GATE-MATRIX.md` row `AWS active application deploy (infra/scripts/deploy-aws-application.sh)` (resolved Phase 6 plan 06-02).
- PASS - see `01-LAUNCH-GATE-MATRIX.md` row `Stale edgar-identity secret ARN mitigation` (resolved Phase 6 plan 06-02).
- PASS - see `01-LAUNCH-GATE-MATRIX.md` row `ECR cleanup deleting in-flight image digest mitigation` (resolved Phase 6 plan 06-02).
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `AWS MDM hosted graph E2E` (depends on Phase 8 / MDM-02 secret population; out of Phase 6 scope).

Planned production deploy commands and full E2E commands are not evidence entries here because they were not run during Phase 1.

## Dev Precedent Reconciliation

dev precedent only — prod proof required separately

The dev app summary exists and the latest dev hosted graph E2E status-only check reports the six acceptance workflows as `SUCCEEDED`: `mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`, and `mdm_counts`.

Production still requires:

- production AWS profile/account label,
- production app summary or equivalent live discovery,
- explicit warehouse and MDM digest image refs,
- stale `edgar-identity` ARN mitigation proof,
- post-cleanup digest re-resolution proof,
- production status and E2E evidence captured without secret values.

## Phase 2 Read-Only Checks Actually Run

```bash
cd infra/terraform/accounts/prod

# 1. TEMPORARY edit (reverted in step 4, never committed):
#    required_version = "~> 1.14.7"  ->  ">= 1.14.7"

# 2. Local-backend override (NOT committed, deleted in step 4)
cat > override.tf <<'EOF'
terraform {
  backend "local" {
    path = "/tmp/edgartools-prod-plan/terraform.tfstate"
  }
}
EOF

terraform init -input=false -no-color
terraform plan -input=false -no-color

# 4. Revert everything
git checkout -- versions.tf
rm -rf override.tf .terraform .terraform.lock.hcl terraform.tfstate* /tmp/edgartools-prod-plan
git status --short infra/terraform/accounts/prod
```

Result: succeeded. `Plan: 37 to add, 0 to change, 0 to destroy.`

- Resource-add count: `Plan: 37 to add, 0 to change, 0 to destroy` against account `077127448006` (per D-05, non-secret account label).
- Output names present in `infra/terraform/accounts/prod/outputs.tf` (22 total, names only): `bronze_bucket_name`, `bronze_bucket_arn`, `warehouse_bucket_name`, `warehouse_bucket_arn`, `snowflake_export_bucket_name`, `snowflake_export_bucket_arn`, `ecr_repository_url`, `cluster_name`, `cluster_arn`, `public_subnet_ids`, `public_ecs_security_group_id`, `log_group_name`, `edgar_identity_secret_arn`, `snowflake_manifest_sns_topic_arn`, `snowflake_export_root_url`, `snowflake_export_prefix`, `snowflake_export_kms_key_arn`, `runner_credentials_secret_arn`, `mdm_postgres_dsn_secret_arn`, `mdm_neo4j_secret_arn`, `mdm_api_keys_secret_arn`, `mdm_snowflake_secret_arn`.
- Revert confirmed: `git status --short infra/terraform/accounts/prod` is empty (clean) after the procedure — `versions.tf` restored to its committed `~> 1.14.7` content, `override.tf`/`.terraform`/`.terraform.lock.hcl`/`terraform.tfstate*`/`/tmp/edgartools-prod-plan` all removed.
- Required-fix note: `infra/terraform/accounts/prod/versions.tf` carries `required_version = "~> 1.14.7"` (pessimistic `~>` constraint, accepts only `1.14.x`), which fails `terraform init` under the locally installed Terraform `1.15.5` until temporarily relaxed to `>= 1.14.7` as in step 1 above. The dev-side equivalent already uses `>= 1.14.7`. This is a real, unfixed repo bug recorded here for a future task to fix permanently — Phase 2 did not fix it (Pattern 1, temporary edit-then-revert only).
- This is plan-only context. It is not production proof — no real backend/state exists; "AWS passive infrastructure outputs" remains BLOCKED (see `01-LAUNCH-GATE-MATRIX.md` row `AWS passive infrastructure outputs`).

### Image-Promotion Digest Capture (read-only)

```bash
aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-warehouse \
  --image-ids imageTag=dev \
  --query 'imageDetails[0].imageDigest' --output text

aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-mdm \
  --image-ids imageTag=dev \
  --query 'imageDetails[0].imageDigest' --output text
```

Result: succeeded for both repositories.

- `edgartools-dev-warehouse:dev` and `edgartools-dev-mdm:dev` each resolved to a digest in the standard `sha256:<64-hex-chars>` format (the `@sha256:` digest form usable for `--image-ref`/`--mdm-image-ref`).
- This is the read-only half of the image-promotion procedure documented in `runbook/aws-deploy.md`; the `aws ecr put-image` re-tag to `:prod` is operator-executed at cutover, not run during Phase 2.
- Digest values themselves are not recorded here (non-secret but ephemeral/mutable-on-rebuild) — only the format was confirmed.

## Required MDM Secret Names

The following MDM Secrets Manager secret names are required by `deploy-aws-application.sh --env prod --enable-mdm` (names only — no ARNs, values, or DSNs):

- `edgartools-prod/mdm/postgres_dsn`
- `edgartools-prod/mdm/neo4j`
- `edgartools-prod/mdm/api_keys`
- `edgartools-prod/mdm/snowflake`

These are required-identifier `BLOCKED` items — see `01-LAUNCH-GATE-MATRIX.md` `## Required Production Identifiers`. Actual secret creation/population is Phase 3 (MDM-01) scope.

## Required Bronze Reuse Prefixes

Production should reuse the already-downloaded dev bronze SEC artifacts before
the first prod bootstrap/capture workload because bronze SEC filing artifacts
are additive and immutable after capture. This is a planned production step,
not Phase 2 evidence, because prod passive storage has not been applied yet.

- Dev bronze source root: `s3://edgartools-dev-bronze-077127448006/warehouse/bronze/`.
- Prod bronze destination root: blocked until `terraform -chdir=infra/terraform/accounts/prod output -raw bronze_bucket_name` resolves after prod apply, then use `s3://<prod-bronze-bucket>/warehouse/bronze/`.
- Required evidence after the operator runs the step: dry-run/final `aws s3 sync` command, source/destination prefixes, object count, and total size only. Do not paste full object key listings.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Production bronze data reuse from dev bronze`.

## Generated-JSON Summary Rule

When `infra/aws-prod-application.json` exists, evidence must summarize only:

- file presence,
- top-level keys,
- state-machine name list,
- image-ref format (`@sha256:` digest vs mutable tag),
- relevant sanitized paths.

Do not paste the JSON body.

## Phase 6 Production Apply

Date: 2026-06-19 UTC
Environment: production (`infra/terraform/accounts/prod/`).
AWS account: `077127448006` (per D-05, non-secret account label).

### tfstate Bucket Bootstrap

```bash
aws s3api create-bucket --bucket edgartools-prod-tfstate --region us-east-1
aws s3api put-bucket-versioning --bucket edgartools-prod-tfstate --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket edgartools-prod-tfstate --server-side-encryption-configuration '{...AES256...}'
aws s3api put-public-access-block --bucket edgartools-prod-tfstate --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api head-bucket --bucket edgartools-prod-tfstate
```

Result: succeeded.

- `edgartools-prod-tfstate` bucket created in `us-east-1`, versioned, SSE (AES256) encrypted.
- All four public-access-block flags confirmed `true` (BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets).
- `head-bucket` returned success, confirming the bucket exists and is reachable before `terraform init`.

### Terraform Plan / Apply (real, non-reverted)

```bash
cd infra/terraform/accounts/prod
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
terraform apply tfplan
```

Result: succeeded.

- Saved plan (`tfplan`): `Plan: 42 to add, 0 to change, 0 to destroy.`
- Apply executed against the exact saved `tfplan` file (no re-plan) per D-04: `Apply complete! Resources: 42 added, 0 changed, 0 destroyed.`
- `versions.tf` permanently fixed to `required_version = ">= 1.14.7"` (committed; no longer requires the Phase 2 temporary-edit-then-revert workaround).
- 22 Terraform output **names** captured (no values): `bronze_bucket_name`, `bronze_bucket_arn`, `warehouse_bucket_name`, `warehouse_bucket_arn`, `snowflake_export_bucket_name`, `snowflake_export_bucket_arn`, `ecr_repository_url`, `cluster_name`, `cluster_arn`, `public_subnet_ids`, `public_ecs_security_group_id`, `log_group_name`, `edgar_identity_secret_arn`, `snowflake_manifest_sns_topic_arn`, `snowflake_export_root_url`, `snowflake_export_prefix`, `snowflake_export_kms_key_arn`, `runner_credentials_secret_arn`, `mdm_postgres_dsn_secret_arn`, `mdm_neo4j_secret_arn`, `mdm_api_keys_secret_arn`, `mdm_snowflake_secret_arn`.
- This is the first real production state-changing Terraform action in the go-live workstream. It remediates Blocker 1 from the v1.5 go/no-go packet.
- BLOCKED item resolved - see `01-LAUNCH-GATE-MATRIX.md` row `AWS passive infrastructure outputs`.

### EDGAR Identity Secret Value

- `aws secretsmanager put-secret-value --secret-id edgartools-prod-edgar-identity` run once with the SEC EDGAR User-Agent string. EDGAR_IDENTITY value set, not pasted (D-06/D-10).
- `describe-secret` confirms exactly one secret version exists (value populated); `get-secret-value` confirms the value is non-empty without printing it.
- None of the 4 MDM secret containers (`edgartools-prod/mdm/postgres_dsn`, `/neo4j`, `/api_keys`, `/snowflake`) received a `put-secret-value` call in this plan — each resolves an ARN via `describe-secret` but has no `AWSCURRENT` version, confirming they remain empty shells per D-05/D-06. MDM value population is deferred to Phase 8 / MDM-02.

### Status

- Blocker 1 (prod AWS infrastructure not yet applied) is remediated. LIVE-04 satisfied.
- Blocker 2 (MDM secret values not populated) remains open — owned by Phase 8 / MDM-02, unchanged by this plan.

## Phase 6 Plan 02 — Active Application Deploy

Date: 2026-06-19 UTC
Environment: production (`infra/scripts/deploy-aws-application.sh --env prod`).
AWS account: `077127448006` (per D-05, non-secret account label).

### ECR Image Promotion (`:dev` -> `:prod`, format only)

```bash
WAREHOUSE_DEV_DIGEST=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-warehouse --image-ids imageTag=dev \
  --query 'imageDetails[0].imageDigest' --output text)
MDM_DEV_DIGEST=$(aws ecr describe-images --region us-east-1 \
  --repository-name edgartools-dev-mdm --image-ids imageTag=dev \
  --query 'imageDetails[0].imageDigest' --output text)
# re-tag via batch-get-image + put-image (registry-side manifest copy)
aws ecr put-image --region us-east-1 --repository-name edgartools-dev-warehouse \
  --image-tag prod --image-manifest "$WAREHOUSE_MANIFEST"
aws ecr put-image --region us-east-1 --repository-name edgartools-dev-mdm \
  --image-tag prod --image-manifest "$MDM_MANIFEST"
```

Result: both digests confirmed in `sha256:<64-hex-chars>` format (format only — no digest value recorded here). `put-image` returned `ImageAlreadyExistsException` for both repositories because the `:prod` tag already pointed at the exact current `:dev` digest (a prior session had already performed this promotion) — confirmed via a follow-up `describe-images --image-ids imageTag=prod` showing the `:prod`-tagged digest matches the freshly-resolved `:dev` digest for both `edgartools-dev-warehouse` and `edgartools-dev-mdm`. This is the intended end state (idempotent promotion), not a failure.

### Active Deploy Command

```bash
export EDGAR_IDENTITY_SECRET_ARN="$(aws secretsmanager describe-secret --region us-east-1 \
  --secret-id edgartools-prod-edgar-identity --query ARN --output text)"
# digests re-resolved fresh, same session, immediately before this call

bash infra/scripts/deploy-aws-application.sh \
  --env prod \
  --cluster-arn "<cluster-arn>" \
  --cluster-name "edgartools-prod-warehouse" \
  --image-ref "077127448006.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-warehouse@<DIGEST>" \
  --mdm-image-ref "077127448006.dkr.ecr.us-east-1.amazonaws.com/edgartools-dev-mdm@<DIGEST>" \
  --enable-mdm \
  --skip-build \
  --edgar-identity-secret-arn "$EDGAR_IDENTITY_SECRET_ARN"
```

Result: succeeded, exit code 0.

- `--cluster-arn`/`--cluster-name` were supplied explicitly (Rule 3 fix): the script has no AWS-API-discovery or naming-convention fallback for the ECS cluster identifier (confirmed by reading `deploy-aws-application.sh` lines 403-409, 432) — it requires either an explicit flag or a pre-existing `infra/aws-prod-application.json` manifest, neither of which existed before this run. Values were read from `terraform -chdir=infra/terraform/accounts/prod output` (non-secret resource identifiers, not credentials).
- Image digests for `--image-ref`/`--mdm-image-ref` were re-resolved in the same shell session immediately before this command (after the ECR promotion step above), and the run included the script's own internal `cleanup-ecr-images.sh --env prod --apply` pre-deploy step (logged "0 images deleted, 0 MB freed" — nothing was at risk because both images carry both `:dev` and `:prod` tags, which the retention policy keeps).
- `--edgar-identity-secret-arn` was a freshly resolved `describe-secret` call in the same session, not a cached value.
- Two non-fatal warnings logged (informational, did not affect exit code): `could not describe RDS instance edgartools-prod-mdm; skipping DSN sync` (expected — `--mdm-database-source` defaults to `rds` and an RDS MDM instance does not exist in this Snowflake-Postgres-backed deployment; population of `MDM_DATABASE_URL` with the Snowflake Postgres DSN is explicitly Phase 8 / MDM-02 scope per D-05/D-06, not fixed here) and `could not set S3 bucket notification (may need s3:PutBucketNotification permission)` (non-blocking, no production data-flow impact observed; recorded here for operator awareness, not auto-fixed per scope-boundary rules).
- 22 ECS task definitions / Step Functions resources created (5 task definitions, 1 ECS log group already existed, 1 new Step Functions log group, 22 state machines) — all-create, zero updates/destroys, consistent with a first prod active deploy.
- `infra/aws-prod-application.json` written to the repo root on success. The file is **not gitignored** (confirmed via `git check-ignore` returning no match) and remains **untracked** (`git status --short` shows `?? infra/aws-prod-application.json`) — it is intentionally never staged or committed (D-10).

### `infra/aws-prod-application.json` Summary (Generated-JSON Summary Rule)

- File presence: confirmed present at repo root after the deploy command above.
- Top-level keys (18 total): `bronze_bucket_name`, `cluster`, `ecr_repository_url`, `edgar_identity_secret_arn`, `environment`, `execution_role_arn`, `image_ref`, `log_groups`, `mdm`, `mdm_image_ref`, `name_prefix`, `region`, `snowflake_export_bucket_name`, `state_machines`, `step_functions_role_arn`, `task_definitions`, `task_role_arn`, `warehouse_bucket_name` — matches the dev manifest's key set (Phase 1 evidence above).
- `state_machines` name list (22 total): `bootstrap`, `bootstrap_batched`, `bootstrap_full`, `catch_up_daily_form_index`, `daily_incremental`, `full_reconcile`, `gold_refresh`, `load_daily_form_index_for_date`, `load_history`, `mdm_backfill_relationships`, `mdm_check_connectivity`, `mdm_counts`, `mdm_gold`, `mdm_migrate`, `mdm_run`, `mdm_seed_from_silver`, `mdm_seed_universe`, `mdm_sync_graph`, `mdm_verify_graph`, `ownership_mdm_gold`, `silver_mdm_gold`, `targeted_resync`.
- `image_ref`/`mdm_image_ref` format: both use the immutable `@sha256:<64-hex-chars>` digest form (not a mutable tag) — confirmed via pattern match, no digest value pasted.
- The JSON body, all ARNs, and all digest values are intentionally omitted from this evidence entry (D-10).

### Status

- Blocker 1 is now fully remediated: both prod passive infrastructure (06-01) and the active application deploy manifest (06-02) exist. LIVE-05 satisfied.
- Row 13 (dev->prod bronze sync) remains out of scope for this plan; the prod bronze bucket (`edgartools-prod-bronze-077127448006`) now exists per the 06-01 evidence above, satisfying its prerequisite, but the sync itself has not been run.
- Blocker 2 (MDM secret values not populated) remains open — owned by Phase 8 / MDM-02, unchanged by this plan. The MDM database source warning above is a related but distinct observation, not a fix attempted in this plan.
