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

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `AWS passive infrastructure outputs`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Production AWS application manifest (infra/aws-prod-application.json)`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `AWS active application deploy (infra/scripts/deploy-aws-application.sh)`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Stale edgar-identity secret ARN mitigation`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `ECR cleanup deleting in-flight image digest mitigation`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `AWS MDM hosted graph E2E`.

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

## Generated-JSON Summary Rule

When `infra/aws-prod-application.json` exists, evidence must summarize only:

- file presence,
- top-level keys,
- state-machine name list,
- image-ref format (`@sha256:` digest vs mutable tag),
- relevant sanitized paths.

Do not paste the JSON body.
