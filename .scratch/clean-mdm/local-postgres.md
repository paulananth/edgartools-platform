# Local PostgreSQL 16 for Clean MDM

Operator note for other agents on this Mac. The live database is a Colima
Docker volume, not git. This file is the recipe and the last observed state.

Branch: `grok/clean-mdm-local-postgres`
Worktree: `../edgartools-platform-grok-local-postgres`

## Connect

Same instance, three databases. Password `test` is local-only.

```bash
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
export MDM_DATABASE_URL="postgresql://postgres:test@127.0.0.1:5432/mdm"
export BOOKKEEPING_DATABASE_URL="postgresql://postgres:test@127.0.0.1:5432/bookkeeping"
export CHANGE_LEDGER_DATABASE_URL="postgresql://postgres:test@127.0.0.1:5432/change_ledger"
```

| Database | DSN | What lives here |
|---|---|---|
| `mdm` | `postgresql://postgres:test@127.0.0.1:5432/mdm` | Current MDM schema (migrations 001–022 minus Change Ledger tables) |
| `bookkeeping` | `postgresql://postgres:test@127.0.0.1:5432/bookkeeping` | 10 warehouse operational tables |
| `change_ledger` | `postgresql://postgres:test@127.0.0.1:5432/change_ledger` | 11 acquisition `source_*` tables |

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

## Observed state (2026-09-18)

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
`/tmp/edgartools-local-fewco/silver-landing/`, 0 SEC calls. `mdm_company` is
still empty (10 seeded audit-firm entities only). Change Ledger was unused.

`mdm mastering` for those three CIKs failed: Snowflake account
`PRJEDJU-QJB05385` (CLI connections and `edgartools-prod/mdm/snowflake`) has a
ended free trial and suspended warehouses. Mastering reads Snowflake
`EDGARTOOLS_SILVER`, not local landing Parquet.

## Guardrails

- Read prod S3; do not point `WAREHOUSE_BRONZE_ROOT` at prod for a local run
  that writes run markers. Use a local bronze copy.
- Do not start `one_click_data_refresh` from this laptop.
- Do not treat this instance as production MDM, bookkeeping, or Change Ledger.
