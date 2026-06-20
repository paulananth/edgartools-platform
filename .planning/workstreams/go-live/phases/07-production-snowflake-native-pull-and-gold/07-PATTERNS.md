# Phase 7: Production Snowflake Native Pull And Gold - Pattern Map

**Mapped:** 2026-06-19
**Files analyzed:** 12
**Analogs found:** 5 / 5

Phase 7 is an execution-and-evidence phase. No application source code is
changed by the plan itself. The important patterns are runbook command shapes,
secret-safe evidence summaries, matrix row updates, and local generated-file
handling.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `evidence/native-pull.md` | doc (production evidence) | event-driven command log | Phase 1 `evidence/snowflake.md` and Phase 6 `evidence/aws.md` append-only sections | exact |
| `evidence/native-pull-validation-sanitized.json` | doc/data (sanitized validation artifact) | transform raw validation JSON to safe summary | Phase 6 generated-JSON summary rule for `infra/aws-prod-application.json` | role-match |
| `evidence/dbt-gold.md` | doc (production dbt evidence) | event-driven command log | Phase 1 `evidence/snowflake.md` dbt/gold placeholders | exact |
| Phase 1 `evidence/snowflake.md` | doc (launch evidence rollup) | append concise pass/block citations | same file, Phase 2 Snowflake evidence sections | exact |
| Phase 1 `01-LAUNCH-GATE-MATRIX.md` rows 18-21 | doc (status ledger) | BLOCKED to PASS or BLOCKED-with-new-proof | Phase 6 matrix rows 12/14/15/16/17 and Phase 1 row 27 | exact |

## Pattern Assignments

### `evidence/native-pull.md`

**Analog:** `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/snowflake.md`

Use the existing evidence style:

1. Fenced `bash` block with the exact command.
2. `Result: succeeded` or `Result: failed` line.
3. Bullets with non-secret facts only.
4. PASS/BLOCKED pointer to the exact launch matrix row.

For Phase 7, this file owns detailed production proof for SNOW-03:

- wrapper command and exit code,
- Terraform root readiness and local-input checks,
- storage integration metadata validation summary,
- stage/list and manifest copy-history validation summary,
- manifest stream processor task state/history summary,
- native-pull Terraform output readiness,
- access reconcile/apply summary,
- raw artifact handling note.

Do not paste raw wrapper output, raw Snowflake rows, Terraform state, ARNs,
external IDs, S3 URLs, account identifiers, manifest file names, or raw
connector error text.

### `evidence/native-pull-validation-sanitized.json`

**Analog:** Phase 6 `infra/aws-prod-application.json` summary discipline.

The raw helper output (`infra/snowflake/sql/prod_native_pull_handshake.json`)
is local and may contain sensitive values. The committed JSON is a structured,
sanitized summary only.

Allowed fields:

- `environment`
- `generated_at`
- `status`
- `database_name`
- `source_schema_name`
- `gold_schema_name`
- `storage_integration_name`
- `stage_name`
- `manifest_task_name`
- `native_pull_ready`
- `validation_checks`
- `safe_counts`
- `retry_count`
- `blocked_reason_category`

Forbidden fields:

- ARNs,
- external IDs,
- S3 URLs,
- manifest object names or paths,
- account identifiers,
- raw Snowflake rows,
- raw connector errors,
- Terraform output values that identify infrastructure beyond safe object names.

### `evidence/dbt-gold.md`

**Analog:** Phase 1 `evidence/snowflake.md` dbt/gold placeholder sections and
Phase 2 `runbook/dbt-gold.md`.

Use exact dbt commands from the Phase 7 context:

```bash
cd infra/snowflake/dbt/edgartools_gold
uv run --with dbt-snowflake dbt deps
uv run --with dbt-snowflake dbt run --target prod
uv run --with dbt-snowflake dbt test --target prod
```

Evidence may include model names, selected status lines, counts, timings, and
failed test names. It must not include compiled SQL, account locators,
passwords, tokens, raw adapter traces, or raw connector exceptions.

### Phase 1 `evidence/snowflake.md`

**Analog:** same file's "Phase 2 Read-Only Checks Actually Run" append style.

Phase 7 appends concise production sections after the detailed Phase 7-local
evidence exists:

- Plan 07-01: native-pull production deploy and validation summary.
- Plan 07-02: deployer grants, dbt run/test, gold status, and freshness
  summary.

Keep Phase 1 evidence concise. Link or cite the Phase 7-local evidence paths
instead of duplicating detailed validation text.

### Phase 1 `01-LAUNCH-GATE-MATRIX.md` Rows 18-21

**Analog:** Phase 6 rows 12/14/15/16/17, which flip only after real production
proof exists and keep blocked rows blocked when scope is not executed.

Plan ownership:

- 07-01 owns row `Snowflake native S3 pull stack (infra/scripts/deploy-snowflake-stack.sh)`.
- 07-02 owns rows `Snowflake deployer direct grants for gold dynamic tables`,
  `dbt compile/run/test for production target`, and
  `EDGARTOOLS_GOLD_STATUS and dynamic-table freshness`.

Allowed statuses remain `PASS` and `BLOCKED`. If a live operation fails, keep
the row `BLOCKED` and replace generic prerequisite text with the new
non-secret failure category, owner, and remediation. Do not mark a row `PASS`
based on wrapper success alone.

## Shared Patterns

### Operator-Local Inputs

These files are inputs or generated outputs, not committed artifacts:

- `infra/aws-prod-application.json`
- `infra/terraform/access/aws/accounts/prod/backend.hcl`
- `infra/terraform/access/aws/accounts/prod/terraform.tfvars`
- `infra/terraform/snowflake/accounts/prod/backend.hcl`
- `infra/terraform/snowflake/accounts/prod/terraform.tfvars`
- `infra/terraform/access/snowflake/accounts/prod/backend.hcl`
- `infra/terraform/access/snowflake/accounts/prod/terraform.tfvars`
- `infra/snowflake/sql/prod_native_pull_handshake.json`
- `infra/snowflake/dbt/edgartools_gold/profiles.yml`

Plans may read or create these locally, but committed evidence must summarize
only safe facts such as path presence, command success/failure, safe object
names, counts, and status categories.

### Production Approval Gates

Use explicit checkpoints before state-changing production Snowflake operations:

- 07-01 wrapper execution changes AWS IAM trust and Snowflake objects.
- 07-02 dbt run creates or replaces production gold dynamic tables.

Read-only preflights can run before approval. State-changing commands wait for
operator approval in the execution workflow.

### Secret-Safety Scan

Before committing evidence, run a focused scan of newly authored Phase 7 files
and touched Phase 1 evidence/matrix files for obvious forbidden strings:

```bash
rg -n "arn:aws|external_id|s3://|password|token|SecretString|account_locator|@sha256:[a-f0-9]{64}" \
  .planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold \
  .planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/snowflake.md \
  .planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md
```

The command may match prose that names forbidden categories. Investigate every
hit and ensure no actual value is committed.
