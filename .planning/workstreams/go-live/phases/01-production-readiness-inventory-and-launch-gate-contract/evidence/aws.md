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

## Generated-JSON Summary Rule

When `infra/aws-prod-application.json` exists, evidence must summarize only:

- file presence,
- top-level keys,
- state-machine name list,
- image-ref format (`@sha256:` digest vs mutable tag),
- relevant sanitized paths.

Do not paste the JSON body.
