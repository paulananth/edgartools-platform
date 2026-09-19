# Local PostgreSQL 16 for Clean MDM

Operator note for other agents on this Mac. The live database is a Colima
Docker volume, not git. This file is the recipe and the last observed state.

Snowflake is unavailable for this workstream (trial ended on
`PRJEDJU-QJB05385`). Test warehouse → silver → MDM mastering locally against
this instance. Production still reads `EDGARTOOLS_SILVER` when
`SILVER_DATABASE_URL` is unset.

Branch: `grok/local-mdm-bounded-mastering`
Worktree: `../edgartools-platform-grok-local-postgres`
Earlier DSN/provision PR: `grok/clean-mdm-local-postgres` (#655)

## Connect

Same instance, four databases. Password `test` is local-only.

```bash
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
export MDM_DATABASE_URL="postgresql://postgres:test@127.0.0.1:5432/mdm"
export BOOKKEEPING_DATABASE_URL="postgresql://postgres:test@127.0.0.1:5432/bookkeeping"
export CHANGE_LEDGER_DATABASE_URL="postgresql://postgres:test@127.0.0.1:5432/change_ledger"
export SILVER_DATABASE_URL="postgresql://postgres:test@127.0.0.1:5432/silver"
```

| Database | DSN | What lives here |
|---|---|---|
| `mdm` | `postgresql://postgres:test@127.0.0.1:5432/mdm` | Current MDM schema (migrations 001–022 minus Change Ledger tables) |
| `bookkeeping` | `postgresql://postgres:test@127.0.0.1:5432/bookkeeping` | 10 warehouse operational tables |
| `change_ledger` | `postgresql://postgres:test@127.0.0.1:5432/change_ledger` | 11 acquisition `source_*` tables |
| `silver` | `postgresql://postgres:test@127.0.0.1:5432/silver` | Silver landing Parquet loaded for local mastering |

Container: `edgartools-clean-mdm-pg16` (`postgres:16-alpine`, 16.15), bound to `127.0.0.1:5432`.

## Start or recreate

```bash
bash infra/scripts/start-local-postgres.sh
bash infra/scripts/provision-local-postgres-stores.sh
# only if Change Ledger tables have reappeared inside mdm:
bash infra/scripts/provision-local-postgres-stores.sh --drop-ledger-from-mdm
```

`mdm migrate` against `mdm` recreates `source_*` tables there. Keep
`CHANGE_LEDGER_DATABASE_URL` set; do not remigrate MDM to preserve the split.
Acquisition workflows honor that env var and fall back to `MDM_DATABASE_URL`
(production co-hosted layout).

## Observed state (2026-09-18 / 2026-09-19)

AWS account `690839588395` can read prod bronze. A bounded load of Apple
(`320193`), Microsoft (`789019`), and Amazon (`1018724`) copied submissions
JSON to `/tmp/edgartools-local-fewco/bronze` (not committed) and ran:

```text
edgar-warehouse bootstrap-batch \
  --cik-list 320193,789019,1018724 \
  --artifact-policy skip --parser-policy skip --no-include-pagination \
  --run-id local-fewco-20260917
```

Result: bookkeeping run succeeded, 3,024 silver landing rows under
`/tmp/edgartools-local-fewco/silver-landing/`, 0 SEC calls. Change Ledger
was unused.

Those Parquet files were loaded into database `silver`:

```text
uv run python infra/scripts/load_local_silver_landing.py \
  --landing-root /tmp/edgartools-local-fewco/silver-landing \
  --database-url postgresql://postgres:test@127.0.0.1:5432/silver
```

| Silver table | Rows |
|---|---|
| `sec_company` | 3 |
| `sec_company_address` | 6 |
| `sec_company_filing` | 3007 |
| `sec_company_former_name` | 3 |
| `sec_company_submission_file` | 5 |
| `sec_company_ticker` | 0 (created empty; tickers optional) |

With `SILVER_DATABASE_URL` set, `_silver_reader()` uses
`PostgresSilverReader` instead of Snowflake. Bounded company mastering:

```text
edgar-warehouse mdm mastering --entity-type company \
  --cik 320193 --cik 789019 --cik 1018724 \
  --run-id local-fewco-mastering-20260918
```

First run: `companies: 3`, `processed: 3`, `skipped_unchanged: 0`.
Identical rerun: `processed: 3`, `skipped_unchanged: 3` (CIK match +
content-hash skip). Golden records:

| cik | canonical_name | tracking_status |
|---|---|---|
| 320193 | Apple | active |
| 789019 | Microsoft | active |
| 1018724 | Amazon Com | active |

`mdm_entity` now has 3 `company` + 10 seeded `audit_firm` rows.
`mdm_source_ref` has 3 `edgar_cik` rows. `mdm_change_log` has 3 company
rows after the first run and did not grow on the rerun.

This is the legacy `mdm mastering` path, not Clean MDM `mdm_v2`.

## What still cannot run locally on this landing set

`--artifact-policy skip` did not capture ownership XML, ADV, or 13F
holdings. Person, security, fund, adviser mastering and
`derive-relationships` have no source tables here.

Person/security/relationship silver SQL still uses Snowflake/DuckDB
`QUALIFY`. `PostgresSilverReader` rewrites `COUNT_IF` and `?` binds only.
Do not run those commands against local silver until that dialect gap is
closed and the missing tables are loaded.

Graph publish/reconcile/activate still need Snowflake.

## Guardrails

- Read prod S3; do not point `WAREHOUSE_BRONZE_ROOT` at prod for a local run
  that writes run markers. Use a local bronze copy.
- Do not start `one_click_data_refresh` from this laptop.
- Do not treat this instance as production MDM, bookkeeping, or Change Ledger.
