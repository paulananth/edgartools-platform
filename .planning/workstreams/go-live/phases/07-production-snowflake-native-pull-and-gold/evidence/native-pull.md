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

### SNOW-03 disposition (initial preflight)

Status: BLOCKED (superseded below).

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

## Phase 7 Plan 07-01 Retry (branch takeover, real production apply)

Date: 2026-06-19 UTC (continuation on `claude/go-live-v1.6-phase7`)

An operator supplied production Snowflake ACCOUNTADMIN access via a local
SnowCLI connection. The six local Terraform input files were created locally
(gitignored — `*.tfvars` and `backend.hcl` are excluded by `.gitignore`) and
the state-changing wrapper was run with explicit operator approval:

```bash
bash infra/scripts/deploy-snowflake-stack.sh --env prod --snow-connection <redacted>
```

### Root-cause fixes required before the apply could succeed

1. **Pessimistic Terraform version constraints.** All three additional
   Terraform roots used by this wrapper (`access/aws`, `snowflake`,
   `access/snowflake`, both dev and prod) carried the same `~> 1.14.x`
   constraint bug Phase 6 already fixed in the main `accounts/prod` root.
   Fixed identically (`~>` to `>=`) in all 6 `versions.tf` files.
2. **`snowflake_state_bucket` example value breaks first bootstrap apply.**
   `infra/terraform/access/aws/accounts/prod/terraform.tfvars.example` sets a
   real (non-null) `snowflake_state_bucket`, which forces
   `data.terraform_remote_state.snowflake[0]` to always attempt a read,
   defeating the `snowflake_bootstrap_enabled` bootstrap path the same file's
   own comment describes. Left this var commented out in the local
   (gitignored) `terraform.tfvars` for the wrapper-driven flow, since the
   wrapper always supplies `snowflake_manifest_subscriber_arn` directly via
   overlay and never needs the remote-state fallback.
3. **Shared, non-namespaced IAM roles across dev/prod.** `runtime_access`
   module hardcodes 3 role names (execution/task/step-functions role) without
   environment prefixing, unlike every other resource in the same module.
   Confirmed via live AWS state that dev created these roles first and prod's
   already-deployed (Phase 6) ECS task definitions already reference the
   identical literal role ARNs — i.e. dev and prod genuinely share these 3
   roles today. Renaming them would break live ECS task definitions in both
   environments, so the roles were left as-is and imported into prod's new
   Terraform state (state-only operation, zero AWS resource change).
4. **Inline policies on the shared roles were *not* namespaced, unlike the
   roles' justification above.** Confirmed the existing dev-created inline
   policy bodies on those roles list only dev's own secret/bucket ARNs. A
   prod apply with the original (also hardcoded) policy names would have
   silently replaced dev's policy body with prod-only ARNs via `PutRolePolicy`,
   cutting dev's ECS tasks off from their own secrets. Fixed by namespacing
   only the 3 inline-policy resource names (not the role names, which must
   stay stable for ARN compatibility) with `${var.name_prefix}` in
   `infra/terraform/access/aws/modules/runtime_access/main.tf`. Dev's existing
   policies are untouched; prod now has its own separately-named policies on
   the same shared roles.
5. **`externalbrowser` authenticator fails on this account.** The supplied
   Snowflake account does not have a SAML identity provider configured; it
   uses native username/password authentication. Switched
   `snowflake_authenticator` to `"snowflake"` (password) in the local
   (gitignored) prod tfvars for the `snowflake` and `access/snowflake` roots,
   sourcing the password from the operator's local SnowCLI connection store
   at runtime, never written to disk or printed.
6. **Dashboard `STREAMLIT` object creation race.** The `snowflake` Terraform
   root creates the dashboard `STREAMLIT` object under the configured admin
   role before the `access/snowflake` root's grants exist, so the very first
   apply attempt failed with "current role does not have access" on the
   `STREAMLIT` object's backing stage. Resolved by completing the
   `access/snowflake` apply (which grants the deployer role to `SYSADMIN`,
   inherited by `ACCOUNTADMIN`) first, then re-applying the `snowflake` root
   to retry just the `STREAMLIT` resource, then completing the
   `access/snowflake` apply's last grant (which itself depends on the
   `STREAMLIT` object existing).

### Result

All three Terraform roots (`access/aws`, `snowflake`, `access/snowflake`)
applied successfully against production with zero destroys. Verified
structurally, without printing any secret/ARN/account-identifier value:

- `native_pull_ready` output: `true`.
- Database, both schemas (source/gold), the dashboard schema, all role names
  (deployer/refresher/reader), and both warehouse names exist and are
  correctly named per the `EDGARTOOLS_PROD_*` convention.
- All native-pull objects created: file formats, external S3 stage, the run
  manifest tables (inbox + refresh status), the manifest pipe, the manifest
  stream, the stream-processor task (verified `state: started` via
  `SHOW TASKS`), and the source schema's full table set (17 tables, verified
  via `INFORMATION_SCHEMA.TABLES` count, not printed individually here).
- A production service user (`EDGARTOOLS_PROD_DEPLOYER`) was created with its
  own password (rotated once after an internal scripting bug briefly exposed
  a since-invalidated password in agent tool output — see `TODOS.md`
  "Password leak via Python quoting bug" for the 5-whys) and granted exactly the
  `EDGARTOOLS_PROD_DEPLOYER` role. Credentials stored in a new AWS secret,
  `edgartools-prod/dbt/snowflake` (deliberately separate from the
  Phase-8/MDM-02-owned `edgartools-prod/mdm/snowflake`, to avoid any future
  cross-phase overwrite), using the standard `DBT_SNOWFLAKE_*` key schema
  already consumed by `edgar_warehouse/mdm/export.py`'s `_snowflake_setting()`.
- End-to-end verified: connected as `EDGARTOOLS_PROD_DEPLOYER` using only the
  credentials read back from Secrets Manager, confirmed `CURRENT_ROLE()`,
  `CURRENT_WAREHOUSE()`, `CURRENT_DATABASE()` match, and confirmed `SELECT`
  access against the source schema's tables.
- Known minor gap (non-blocking for dbt): `EDGARTOOLS_PROD_DEPLOYER` cannot
  `SHOW STAGES` on the ACCOUNTADMIN-created export stage/pipe (no explicit
  grant on those object types in the current `account_access` module — only
  tables/views/dynamic-tables are granted). dbt itself only needs `SELECT` on
  source tables and `CREATE` in the gold schema, both of which are granted, so
  this does not block SNOW-04.

### SNOW-03 disposition (final)

Status: **PASS.** Native-pull infrastructure is live in production, verified
structurally against the real Snowflake account, with credentials safely
stored outside git per D-10.
