# Snowflake Evidence - Phase 1 Production Readiness

Date: 2026-06-14 UTC
Environment: production required; dev rows are precedent only and require separate production proof.
Snowflake connection: production connection required.
Snowflake database: production database required.

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs, full task logs, secret ARNs, and raw Native App job logs.

## Source-Of-Truth Note

Live Snowflake command checks are authoritative for production readiness. Manifests and documentation are supporting evidence only. Production native-pull, dbt, gold status, freshness, and grant checks remain blocked until production identifiers and live access are available.

## Phase 1 Read-Only Checks Actually Run

```bash
for v in DBT_SNOWFLAKE_ACCOUNT DBT_SNOWFLAKE_USER DBT_SNOWFLAKE_PASSWORD DBT_SNOWFLAKE_DATABASE SNOW_CONNECTION SNOWFLAKE_CONNECTION; do
  if [ -n "${!v:-}" ]; then echo "$v=set"; else echo "$v=unset"; fi
done
```

Result: succeeded.

- `DBT_SNOWFLAKE_ACCOUNT`: unset.
- `DBT_SNOWFLAKE_USER`: unset.
- `DBT_SNOWFLAKE_PASSWORD`: unset.
- `DBT_SNOWFLAKE_DATABASE`: unset.
- `SNOW_CONNECTION`: unset.
- `SNOWFLAKE_CONNECTION`: unset.
- `dbt compile` was not run because this shell has no Snowflake/dbt target configuration. This is recorded as a blocked production step, not as evidence.

```bash
find infra/snowflake/dbt/edgartools_gold/models/gold -maxdepth 1 -type f \
  \( -name '*.sql' -o -name '*.yml' -o -name '*.yaml' \) | sort | wc -l
find infra/snowflake/dbt/edgartools_gold/models/gold -maxdepth 1 -type f -name '*.sql' | sort
```

Result: succeeded.

- Gold model/config files at this level: `18`.
- Gold SQL models found: `16`.
- `infra/snowflake/dbt/edgartools_gold/models/gold/edgartools_gold_status.sql` is present.
- Static model inventory is supporting context only. It is not production dbt proof.

## Not-Yet-Runnable Production Steps

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake native S3 pull stack (infra/scripts/deploy-snowflake-stack.sh)`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake deployer direct grants for gold dynamic tables`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `dbt compile/run/test for production target`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `EDGARTOOLS_GOLD_STATUS and dynamic-table freshness`.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Strict edgar-warehouse mdm verify-graph`.

Planned production `deploy-snowflake-stack.sh --run-validation`, `dbt run`, `dbt test`, and gold freshness SQL checks are not evidence entries here because they were not run during Phase 1.

## Known Grant Gap

`TODOS.md` records that `EDGARTOOLS_DEV_DEPLOYER` lacked direct `SELECT` on `EDGARTOOLS_SOURCE`, which blocked `dbt run --full-refresh` for any gold dynamic table until an ad-hoc dev grant was applied. If `EDGARTOOLS_PROD_DEPLOYER` has the analogous direct-grant gap, production dynamic-table refresh can fail even when ad-hoc queries work through secondary roles.

This is recorded as a matrix blocker, not a pass:

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake deployer direct grants for gold dynamic tables`.

### Required-fix check (Task 02-02-03)

The required-fix command for matrix row 7 (`Snowflake deployer direct grants
for gold dynamic tables`), parallel to the resolved
`EDGARTOOLS_DEV_DEPLOYER` dev gap recorded in `TODOS.md`:

```sql
SHOW GRANTS TO ROLE EDGARTOOLS_PROD_DEPLOYER;
```

This must be run (or live discovery performed) against a production
Snowflake account to confirm `EDGARTOOLS_PROD_DEPLOYER` has direct `SELECT`
on the `EDGARTOOLS_SOURCE` tables consumed by gold dynamic-table refresh.
This is recorded as a matrix blocker, not a pass, until that check runs:

- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake deployer direct grants for gold dynamic tables`.

## Dev Precedent Reconciliation

dev precedent only — prod proof required separately

Existing project evidence shows dev Snowflake-hosted graph verification and dbt/gold workflows have been exercised in prior workstreams, including strict dev `mdm verify-graph` success after Native App compute pool activation. The dev static dbt model inventory in this checkout includes `EDGARTOOLS_GOLD_STATUS`.

Production still requires:

- production Snowflake connection and database,
- production native-pull validation or live discovery,
- production dbt compile/run/test evidence,
- production deployer direct-grant proof for dynamic-table refresh,
- production `EDGARTOOLS_GOLD_STATUS` and freshness summary.

## Gold Status And Freshness Summary Shape

To be filled only after production checks actually run:

| Model/Table | Status | Last refresh |
| --- | --- | --- |
| `EDGARTOOLS_GOLD_STATUS` | pending production proof | pending production proof |
| dynamic tables | pending production proof | pending production proof |

## Generated-JSON Summary Rule

Any generated Snowflake or dbt artifact referenced by go-live evidence must be summarized only as path, existence, top-level purpose, and pass/fail result. Do not paste raw logs, compiled SQL containing sensitive values, Terraform state, or full generated JSON bodies.

## Phase 2 Read-Only Checks Actually Run

### SNOW-01 structural-blocker smoke test

Preflight guard (run before the smoke test, per Task 02-02-01): confirmed
the 3 prod `backend.hcl` files
(`infra/terraform/access/aws/accounts/prod/backend.hcl`,
`infra/terraform/snowflake/accounts/prod/backend.hcl`,
`infra/terraform/access/snowflake/accounts/prod/backend.hcl`) are absent
(only `.example` files exist), and statically confirmed in
`infra/scripts/deploy-snowflake-stack.sh` that the `backend.hcl` existence
checks (lines 226-228) occur before the first state-changing call site
(`terraform_apply` at line 349, the first of 5 sequential apply steps across
the 3 Terraform roots).

```bash
bash infra/scripts/deploy-snowflake-stack.sh --env prod --snow-connection edgartools-prod --run-validation
```

Result: failed (structural blocker proven) — exited non-zero (`rc=1`) with a
`backend.hcl` message.

- The script exited non-zero (`rc=1`) before any output other than the error
  message.
- The first (and only) failure reached was the `backend.hcl` existence check
  for the AWS bootstrap root (`infra/terraform/access/aws/accounts/prod`) —
  no `terraform apply`/`terraform init`, Snowflake SQL (`snow sql`), dbt
  (`--run-validation`/`--run-dbt`), or dashboard-upload
  (`--upload-dashboard`) action was reached.
- This proves the documented structural blocker (02-RESEARCH.md Pitfall 2)
  is real and repeatable: the script is a 5-step, 3-root Terraform apply
  orchestrator that runs unconditionally BEFORE any opt-in flag tail, and it
  cannot proceed without the 3 prod `backend.hcl` files (which require a
  production Snowflake account + real S3 tfstate backend to create — out of
  scope, D-01).
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake native S3 pull
  stack (infra/scripts/deploy-snowflake-stack.sh)`. See
  [runbook/snowflake-native-pull.md](../../02-aws-and-snowflake-production-deployment-dry-run/runbook/snowflake-native-pull.md)
  for the full invocation, root cause, required fix (3 missing
  `backend.hcl` files + real tfvars + prod Snowflake account), and the
  `native_pull` target-state resource list (1 storage integration, 2 file
  formats, 1 external stage, source mirror tables, 1 pipe, 1 stream, 3
  stored procedures, 1 task).

### SNOW-02 dev-target dbt gate (Task 02-02-02)

dev precedent only — prod proof required separately

The operator confirmed that the following dev dbt/Snowflake credential
environment variables are NOT set in this shell:

- `DBT_SNOWFLAKE_ACCOUNT`
- `DBT_SNOWFLAKE_USER`
- `DBT_SNOWFLAKE_PASSWORD`
- `DBT_SNOWFLAKE_ROLE`
- `DBT_SNOWFLAKE_DATABASE`
- `DBT_SNOWFLAKE_WAREHOUSE`

Result: BLOCKED — `dbt compile --target dev`, `dbt run --target dev`, and
`dbt test --target dev` were NOT executed.

- No dbt command was run (per the plan's action: do not run dbt without the
  required credentials).
- This is recorded as a failed prerequisite for SNOW-02's dev-target dbt
  gate (D-03), not a silent documentation-only downgrade: the dev-target
  dbt compile/run/test gate remains BLOCKED until an operator supplies all
  6 variables above as environment variables outside git.
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `dbt compile/run/test for
  production target`. The prod-target command surface and this dev-gate
  cross-reference are documented in
  [runbook/dbt-gold.md](../../02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md).

## Phase 7 Production Execution Attempt

### SNOW-03 native-pull preflight

```bash
for f in infra/terraform/access/aws/accounts/prod/backend.hcl \
  infra/terraform/access/aws/accounts/prod/terraform.tfvars \
  infra/terraform/snowflake/accounts/prod/backend.hcl \
  infra/terraform/snowflake/accounts/prod/terraform.tfvars \
  infra/terraform/access/snowflake/accounts/prod/backend.hcl \
  infra/terraform/access/snowflake/accounts/prod/terraform.tfvars
do
  test -f "$f"
done
```

Result: failed preflight; state-changing Snowflake/native-pull execution was
not started.

- All six prod operator-local Terraform input files checked by Phase 7 Plan
  07-01 were absent in this worktree.
- Terraform output reads for the AWS access, Snowflake, and Snowflake access
  prod roots were skipped because backend configuration is absent.
- `deploy-snowflake-stack.sh --env prod --snow-connection edgartools-prod --run-validation`
  was not run; no `terraform init`, `terraform apply`, Snowflake SQL, dbt, or
  dashboard upload action was reached.
- Detailed non-secret evidence is in
  [../../07-production-snowflake-native-pull-and-gold/evidence/native-pull.md](../../07-production-snowflake-native-pull-and-gold/evidence/native-pull.md).
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` row `Snowflake native S3 pull
  stack (infra/scripts/deploy-snowflake-stack.sh)`.

### SNOW-04 dbt/gold dependency preflight

Result: dependency blocked; production dbt/gold execution was not started.

- Phase 7 Plan 07-02 was not allowed to run dbt because Phase 7 Plan 07-01
  recorded SNOW-03 as BLOCKED.
- The six required `DBT_SNOWFLAKE_*` environment variables were unset in this
  shell, and `infra/snowflake/dbt/edgartools_gold/profiles.yml` was absent.
- `profiles.yml` was intentionally not created because the native-pull
  prerequisite stopped execution before dbt setup.
- No grant discovery, dbt deps/run/test, `EDGARTOOLS_GOLD_STATUS`, dynamic-table
  freshness, task-history, or source row-count query ran.
- Detailed non-secret evidence is in
  [../../07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md](../../07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md).
- BLOCKED - see `01-LAUNCH-GATE-MATRIX.md` rows `Snowflake deployer direct
  grants for gold dynamic tables`, `dbt compile/run/test for production target`,
  and `EDGARTOOLS_GOLD_STATUS and dynamic-table freshness`.

### SNOW-04 dbt/gold — PASS (2026-06-20, branch takeover continuation)

`dbt deps`, `dbt run --target prod`, and `dbt test --target prod` ran against
production using `EDGARTOOLS_PROD_DEPLOYER` credentials sourced live from
`edgartools-prod/dbt/snowflake` (never written to disk or printed).

- `dbt deps`: exit 0, no external packages.
- `dbt run --target prod` (first attempt): 15 of 16 models succeeded;
  `FINANCIAL_FACTS` failed with a genuine schema-drift bug (live
  `SEC_FINANCIAL_FACT` table missing a `PERIOD_START` column that the model,
  the Python silver parser, and the Python serving schema all already
  expected). This is a pre-existing gap, not caused by this deploy — full
  5-whys and fix are documented in `TODOS.md` ("SEC_FINANCIAL_FACT missing
  PERIOD_START column blocked `dbt run --target prod`"). Confirmed the
  identical gap exists in `EDGARTOOLS_DEV`'s table too (not fixed there —
  out of scope for this prod-only task).
- Fix applied directly to `EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT`
  via the `snowconn` (ACCOUNTADMIN) connection: added `PERIOD_START DATE NOT
  NULL` via a 3-step migration (`ADD COLUMN` nullable -> backfill `UPDATE`,
  0 rows affected, table was empty -> `SET NOT NULL`). No data loss; the
  checked-in single-statement `ADD COLUMN ... DEFAULT '0001-01-01'` form
  failed on this Snowflake account with a type-coercion error, and Snowflake
  does not support `ALTER COLUMN ... SET DEFAULT` on an existing column at
  all, so the column carries no stored default (acceptable — the loader
  always supplies the value explicitly on insert).
- `dbt run --target prod --select financial_facts` (retry): SUCCESS,
  `PASS=1 ERROR=0`.
- `dbt test --target prod` (full suite): `PASS=47 WARN=0 ERROR=0 SKIP=0
  NO-OP=0 TOTAL=47` (36 data tests + 11 unit tests, including all
  `financial_derived` YoY tiebreaker/amendment/multi-company-isolation unit
  tests against real production data).
- `SHOW DYNAMIC TABLES IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_GOLD`: all 15
  dynamic tables report `scheduling_state = ACTIVE`, `target_lag =
  DOWNSTREAM`, never suspended.
- `SELECT * FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS`:
  no rows (expected — this build used dbt's direct `CREATE OR REPLACE
  DYNAMIC TABLE` path, not a completed Snowflake-managed manifest refresh
  cycle, which is what populates this status view).
- Full detail in
  [../../07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md](../../07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md).
- PASS - matrix rows `dbt compile/run/test for production target` and
  `EDGARTOOLS_GOLD_STATUS and dynamic-table freshness` flip to PASS.
- Note: matrix row `Snowflake deployer direct grants for gold dynamic
  tables` is satisfied as a side effect (the deployer already had the
  `SELECT`/`CREATE` grants needed for these 16 models to build and refresh)
  but the original required-fix check (`SHOW GRANTS TO ROLE
  EDGARTOOLS_PROD_DEPLOYER`) was not separately re-run in this continuation;
  leave that row's disposition to whichever check explicitly covers it.
