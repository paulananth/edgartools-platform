# dbt Gold Production Deploy Runbook

This runbook documents the dbt gold dynamic-table validation surface for
`infra/snowflake/dbt/edgartools_gold/` (SNOW-02). It is non-secret: every
credential value below is a `<placeholder>`. No account locators, passwords,
secret ARNs, DSNs, or compiled SQL are included. No prod dbt command is
executed from this runbook (D-04 — no prod Snowflake connection exists).

## 1. Dev-precedent block (D-03)

dev precedent only — prod proof required separately

This block documents the dev-target dbt validation surface. Task 02-02-02 is
the Phase 2 credential-gated execution/evidence source: the operator
confirmed the required `DBT_SNOWFLAKE_*` dev credential environment variables
were NOT set in this shell, so this block was NOT executed in Phase 2. The
BLOCKED outcome and the missing variable names are recorded in
[evidence/snowflake.md](../../01-production-readiness-inventory-and-launch-gate-contract/evidence/snowflake.md)
under "SNOW-02 dev-target dbt gate (Task 02-02-02)".

```bash
cd infra/snowflake/dbt/edgartools_gold

export DBT_SNOWFLAKE_ACCOUNT="<dev-account-locator.region.cloud>"
export DBT_SNOWFLAKE_USER="<dev-user>"
export DBT_SNOWFLAKE_PASSWORD="<dev-password>"
export DBT_SNOWFLAKE_WAREHOUSE="<dev-warehouse>"

uv run --with dbt-snowflake dbt deps
uv run --with dbt-snowflake dbt compile --target dev
uv run --with dbt-snowflake dbt run --target dev
uv run --with dbt-snowflake dbt test --target dev
```

If an operator supplies these 6 variables (`DBT_SNOWFLAKE_ACCOUNT`,
`DBT_SNOWFLAKE_USER`, `DBT_SNOWFLAKE_PASSWORD`, `DBT_SNOWFLAKE_ROLE`,
`DBT_SNOWFLAKE_DATABASE`, `DBT_SNOWFLAKE_WAREHOUSE`) outside git, this block
can be re-run and the pass/fail outcome appended to `evidence/snowflake.md`
as dev-precedent evidence (D-03) per Task 02-02-02's checkpoint contract.

## 2. Prod-target block (D-04, documentation-only)

This is the BLOCKED row's required-fix command for "dbt compile/run/test for
production target". It is documented only — NOT executed, because no prod
Snowflake connection or credentials exist (D-04).

```bash
cd infra/snowflake/dbt/edgartools_gold

export DBT_SNOWFLAKE_ACCOUNT="<prod-account-locator.region.cloud>"
export DBT_SNOWFLAKE_USER="<prod-user>"
export DBT_SNOWFLAKE_PASSWORD="<prod-password>"
export DBT_SNOWFLAKE_ROLE="EDGARTOOLS_PROD_DEPLOYER"
export DBT_SNOWFLAKE_DATABASE="EDGARTOOLS_PROD"
export DBT_SNOWFLAKE_WAREHOUSE="EDGARTOOLS_PROD_REFRESH_WH"

uv run --with dbt-snowflake dbt deps
uv run --with dbt-snowflake dbt run --target prod
uv run --with dbt-snowflake dbt test --target prod
```

## 3. Known issue: `dbt compile --target prod` requires live prod credentials

**Even a "logic-only" check is not lighter than a full run.** Unlike a
linter, `dbt compile --target prod` opens a live connection to Snowflake to
resolve the target database/schema/warehouse context before it can render
any compiled SQL. There is no placeholder-credential or offline mode for
`dbt compile`. Running it with placeholder values from Section 2 (or with no
credentials at all) fails with a live connector error (a `404 ...
login-request`-class authentication failure) — not a graceful "would
compile" result.

Consequence: SNOW-02's prod-target gate (matrix row 8, "dbt compile/run/test
for production target") cannot be partially de-risked by running `dbt
compile --target prod` ahead of real prod credentials existing. The entire
prod-target dbt gate — `dbt deps`, `dbt run --target prod`, `dbt test
--target prod`, and any `dbt compile --target prod` — requires a real
production Snowflake account, role, database, and warehouse to exist first
(D-01/D-04), and remains BLOCKED until then.

## 4. Gold status / freshness query (matrix row 9 required-fix command)

This is the BLOCKED row's required-fix command for "`EDGARTOOLS_GOLD_STATUS`
and dynamic-table freshness". It is documented only — NOT executed (no prod
Snowflake connection exists).

```sql
SELECT * FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS LIMIT 10;
```

Equivalent via SnowCLI:

```bash
snow sql --connection edgartools-prod -q "SELECT * FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS LIMIT 10;"
```

### `EDGARTOOLS_GOLD_STATUS` column list (names only, no values)

From `infra/snowflake/dbt/edgartools_gold/models/gold/edgartools_gold_status.sql`:

- `environment`
- `source_workflow`
- `run_id`
- `business_date`
- `status`
- `source_load_status`
- `refresh_status`
- `source_row_count`
- `tables_loaded`
- `last_successful_refresh_at`
- `updated_at`

### Gold Status And Freshness Summary Shape

Reuse the existing summary-table shape from `evidence/snowflake.md` for any
future prod freshness result (do not fabricate values until production
checks actually run):

| Model/Table | Status | Last refresh |
| --- | --- | --- |
| `EDGARTOOLS_GOLD_STATUS` | pending production proof | pending production proof |
| dynamic tables | pending production proof | pending production proof |

## References

- `infra/snowflake/dbt/edgartools_gold/` (dbt project root, 16 gold SQL
  models + `edgartools_gold_status.sql`).
- `docs/runbook.md` lines 426-441 (dbt env var conventions).
- CLAUDE.md "dbt gold model SQL changes — smoke test convention" (dynamic
  table `--full-refresh` and the resolved `EDGARTOOLS_DEV_DEPLOYER` grant
  gap, analog for `EDGARTOOLS_PROD_DEPLOYER`).
- `01-LAUNCH-GATE-MATRIX.md` rows `dbt compile/run/test for production
  target` and `EDGARTOOLS_GOLD_STATUS and dynamic-table freshness`.
- [evidence/snowflake.md](../../01-production-readiness-inventory-and-launch-gate-contract/evidence/snowflake.md)
  Task 02-02-02 dev-target dbt gate outcome and "Known Grant Gap" section.
