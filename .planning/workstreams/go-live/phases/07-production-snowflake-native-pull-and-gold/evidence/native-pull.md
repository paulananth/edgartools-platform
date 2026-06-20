# Native-Pull Evidence - Phase 7 Production Snowflake Native Pull And Gold

Date: 2026-06-20 UTC
Environment: production
Requirement: SNOW-03

This artifact captures non-secret evidence only. It omits passwords, tokens,
DSNs, Terraform state, ARNs, external IDs, S3 URLs, Snowflake account
identifiers, manifest file names, raw connector traces, and raw Snowflake rows.

## Phase 7 Plan 07-01 Preflight

### Operator-local Terraform inputs

```bash
for f in \
  infra/terraform/access/aws/accounts/prod/backend.hcl \
  infra/terraform/access/aws/accounts/prod/terraform.tfvars \
  infra/terraform/snowflake/accounts/prod/backend.hcl \
  infra/terraform/snowflake/accounts/prod/terraform.tfvars \
  infra/terraform/access/snowflake/accounts/prod/backend.hcl \
  infra/terraform/access/snowflake/accounts/prod/terraform.tfvars
do
  test -f "$f"
done
```

Result: failed preflight; state-changing execution was not started.

- Missing local input files:
  - `infra/terraform/access/aws/accounts/prod/backend.hcl`
  - `infra/terraform/access/aws/accounts/prod/terraform.tfvars`
  - `infra/terraform/snowflake/accounts/prod/backend.hcl`
  - `infra/terraform/snowflake/accounts/prod/terraform.tfvars`
  - `infra/terraform/access/snowflake/accounts/prod/backend.hcl`
  - `infra/terraform/access/snowflake/accounts/prod/terraform.tfvars`
- Terraform output reads for the AWS access, Snowflake, and Snowflake access
  prod roots were skipped because their backend configuration files are absent.
- `infra/aws-prod-application.json` was absent in this worktree. Phase 7 did not
  require it for this failed preflight because the missing Terraform inputs
  blocked earlier.
- `infra/snowflake/sql/prod_native_pull_handshake.json` was absent; no raw
  native-pull validation artifact was generated.
- The wrapper command was not run. No `terraform init`, `terraform apply`,
  Snowflake SQL, dbt, or dashboard upload action was reached.

### Phase 6 dependency status

Phase 6 remains trusted as complete based on existing committed summaries and
verification:

- 06-01 applied production passive AWS infrastructure and populated only the
  EDGAR identity secret.
- 06-02 deployed the active production AWS application and produced a local,
  untracked application manifest in that execution environment.
- Phase 7 did not rerun Phase 6 AWS deploy actions.

### SNOW-03 disposition

Status: BLOCKED.

Owner: Snowflake operator.

Required remediation:

1. Provide or recreate the six prod local Terraform input files above from the
   checked-in `.example` templates and real production Snowflake/backend values,
   outside git.
2. Re-run Phase 7 Plan 07-01 preflight.
3. If preflight passes, request operator approval for the state-changing wrapper
   command before running:

```bash
bash infra/scripts/deploy-snowflake-stack.sh --env prod --snow-connection edgartools-prod --run-validation
```

This is a launch blocker, not a waiver. SNOW-03 remains BLOCKED until the
native-pull wrapper runs and deep validation proof is captured.
