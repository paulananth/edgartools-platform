# Snowflake Native S3 Pull Stack Production Deploy Runbook

This runbook documents the production Snowflake native-pull stack deploy
(`infra/scripts/deploy-snowflake-stack.sh --env prod`, SNOW-01). It is
non-secret: every value below is a placeholder or a names-only resource
list. No account locators, passwords, secret ARNs, DSNs, or compiled output
are included.

## 1. Documented production invocation (NOT run beyond the structural-blocker
   smoke test below)

```bash
bash infra/scripts/deploy-snowflake-stack.sh \
  --env prod \
  --snow-connection edgartools-prod \
  --run-validation \
  --run-dbt
```

This is the full production command an operator would eventually run: the
native-pull Terraform stack (storage integration + source mirror objects),
followed by an optional validation pass (`--run-validation`) and an optional
dbt gold build (`--run-dbt`). Neither flag-gated tail executes today — the
command dies during its mandatory preamble (see Section 2).

## 2. Structural blocker (proven, not declined)

**The script is a 3-root Terraform orchestrator FIRST.** Before any
`--run-validation`, `--run-dbt`, or `--upload-dashboard` opt-in tail can run,
`deploy-snowflake-stack.sh --env prod` executes a fixed apply sequence across
three Terraform roots in this order:

1. AWS bootstrap trust (`infra/terraform/access/aws/accounts/prod/`) —
   `terraform_apply` (AWS bootstrap overlay).
2. Snowflake storage integration only
   (`infra/terraform/snowflake/accounts/prod/`) —
   `terraform_apply_storage_integration_only`.
3. AWS reconcile (`infra/terraform/access/aws/accounts/prod/`) —
   `terraform_apply` (AWS reconcile overlay).
4. Snowflake full apply (`infra/terraform/snowflake/accounts/prod/`) —
   `terraform_apply` (Snowflake overlay).
5. Snowflake access apply
   (`infra/terraform/access/snowflake/accounts/prod/`) —
   `terraform_apply_root`.

Only after all 5 apply steps succeed does the script reach the
`--run-validation` (manifest task query via `snow sql --connection`),
`--run-dbt` (`dbt run --target <env>`), and `--upload-dashboard`
(`infra/snowflake/streamlit/deploy.sh`) opt-in tails.

**Root cause:** before step 1 can run, the script performs a mandatory
preflight that calls `die` if any of the 3 Terraform roots is missing its
`backend.hcl` file:

```
[[ -f "${AWS_ROOT}/backend.hcl" ]]            || die "Missing backend.hcl in ${AWS_ROOT}"
[[ -f "${SNOWFLAKE_ROOT}/backend.hcl" ]]       || die "Missing backend.hcl in ${SNOWFLAKE_ROOT}"
[[ -f "${SNOWFLAKE_ACCESS_ROOT}/backend.hcl" ]] || die "Missing backend.hcl in ${SNOWFLAKE_ACCESS_ROOT}"
```

These checks run before `terraform_init`/`terraform_apply` for any root —
i.e. before any state-changing Terraform, Snowflake SQL, dbt, or dashboard
action. **`bash infra/scripts/deploy-snowflake-stack.sh --env prod
--snow-connection edgartools-prod --run-validation` exits non-zero (`rc=1`)
with a `Missing backend.hcl in <AWS_ROOT path>` message** — the first of the
three checks fails because only `.example` files exist for all 3 prod roots
today (`infra/terraform/access/aws/accounts/prod/backend.hcl.example`,
`infra/terraform/snowflake/accounts/prod/backend.hcl.example`,
`infra/terraform/access/snowflake/accounts/prod/backend.hcl.example`). No
`terraform apply`, `snow sql`, dbt, or dashboard-upload action is reached.

## 3. Required fix

Before `deploy-snowflake-stack.sh --env prod` can proceed past its preamble,
an operator must supply, for each of the 3 prod Terraform roots:

1. A real `backend.hcl` (copied from the `.example` template and filled in
   with a real S3 backend bucket — an `edgartools-prod-tfstate`-equivalent
   bucket — plus key/region/`use_lockfile = true` per DEC-017):
   - `infra/terraform/access/aws/accounts/prod/backend.hcl`
   - `infra/terraform/snowflake/accounts/prod/backend.hcl`
   - `infra/terraform/access/snowflake/accounts/prod/backend.hcl`
2. A real `terraform.tfvars` (copied from each root's
   `terraform.tfvars.example`) containing the production Snowflake account
   locator, organization identifier, and any AWS account/role identifiers
   the AWS bootstrap/reconcile roots require.

All of the above require a **production Snowflake account to exist** —
explicitly out of scope for this phase (D-01). Until a production Snowflake
account exists and these files are created, `deploy-snowflake-stack.sh
--env prod` will continue to fail at this exact preamble check, and the
"Snowflake native S3 pull stack" gate row stays `BLOCKED`.

## 4. `native_pull` target-state resource list

Once the 3 prod roots can apply, the
`infra/terraform/snowflake/modules/native_pull/main.tf` module creates the
following Snowflake objects (names/categories only — no values):

| Category | Resource type | Identifier |
|---|---|---|
| Storage integration | `snowflake_storage_integration_aws` | `native_pull` |
| File format | `snowflake_file_format` | `parquet` |
| File format | `snowflake_file_format` | `manifest` |
| External stage | `snowflake_stage_external_s3` | `export_stage` |
| Source mirror tables | `snowflake_table` | `tables` (multiple source tables) |
| Pipe | `snowflake_pipe` | `manifest` |
| Stream | `snowflake_stream_on_table` | `manifest` |
| Stored procedure | `snowflake_execute` | `source_load_procedure` |
| Stored procedure | `snowflake_execute` | `refresh_procedure` |
| Stored procedure | `snowflake_execute` | `stream_processor_procedure` |
| Task | `snowflake_task` | `manifest_processor` |

This is the full `EDGARTOOLS_SOURCE` native-pull surface: 1 storage
integration, 2 file formats, 1 external stage, N source mirror tables, 1
pipe, 1 stream, 3 stored procedures, and 1 task
(`SNOWFLAKE_RUN_MANIFEST_TASK`, which DEC-005/CLAUDE.md requires to remain in
`STARTED` state once it exists).

## References

- `infra/scripts/deploy-snowflake-stack.sh` lines 226-228 (backend.hcl
  preflight checks), lines 349-378 (5-step apply sequence), lines 385-440
  (`--run-validation`/`--run-dbt`/`--upload-dashboard` opt-in tails).
- `infra/terraform/snowflake/modules/native_pull/main.tf` (target-state
  resource list).
- `01-LAUNCH-GATE-MATRIX.md` row `Snowflake native S3 pull stack
  (infra/scripts/deploy-snowflake-stack.sh)`.
- [evidence/snowflake.md](../../01-production-readiness-inventory-and-launch-gate-contract/evidence/snowflake.md)
  Phase 2 structural-blocker smoke-test result.
