# Codex: Fix Data Architecture Issues

The full 5-whys analysis is in `docs/data-architecture-issues.md` (12 issues).

## Quick Start

Read the issues doc first, then work in priority order below.

## Phase 1 — High Severity

| # | Issue | Instructions |
|---|-------|-------------|
| 1 | Silver DuckDB sharding — no distributed write guarantees | Add a `reconcile_shards()` method that compares per-table row counts and newest `last_synced_at` across all 4 shards. Report divergence. Wrap per-CIK writes in a shard-level advisory lock. |
| 3 | Branch A & B silver — no referential integrity | Move all fundamentals `CREATE TABLE` DDL (`sec_financial_fact`, `sec_financial_derived`, `sec_earnings_release`, `sec_accounting_flag`, `sec_executive_record`, `sec_thirteenf_holding`) from `silver_store.py` into the main `_DDL` constant. Delete the separate fundamentals shard path. |
| 4 | No pipeline-level transaction | Add a `pipeline_run` table. Every command that touches multiple layers writes a row. Add `verify-pipeline-run` CLI command that re-checks hashes. |
| 10 | Destructive PK migrations | Replace `DROP TABLE` in both `_migrate_financial_*_pk()` methods with `CREATE TABLE new_* AS SELECT ...` then `RENAME TABLE old_* TO backup_*` then `RENAME TABLE new_* TO *`. |
| 11 | No data quality validation | Add `validate-data-quality` command: row count monotonic check, FK-style consistency check, gold-vs-silver row count comparison, NULL ratio report. |

## Phase 2 — Medium Severity

| # | Issue | Instructions |
|---|-------|-------------|
| 2 | Gold is transient | Add `gold_manifest` table to silver recording run_id, per-table row counts, Parquet sha256. Next gold-refresh diffs against previous. |
| 5 | Gold schema evolution | Move PyArrow `pa.schema(...)` constants to `config/gold_schemas.yaml` with a `SCHEMA_VERSION` key. Validate on startup. |
| 6 | MDM overloaded | Move CIK tracking status to `sec_company_sync_state.tracking_status` (already exists). Stop requiring `MDM_DATABASE_URL` for gold commands. |
| 8 | Two discovery mechanisms | Add `discovery_checkpoint` table. Both `daily-incremental` and `bootstrap-next` read/write it to avoid overlap. |
| 9 | No migration framework | Add `schema_migration` table. Convert `_ensure_schema_evolution()` to apply named migrations in order. |

## Phase 3 — Low Severity

| # | Issue | Instructions |
|---|-------|-------------|
| 7 | Leaky serving abstraction | Rename `snowflake_export_*` to `serving_export_*`. Create `ServingTarget` protocol with `SnowflakeTarget` and `DatabricksTarget` implementations. |
| 12 | Manifest fragmentation | Add a `run_manifest.json` at run root listing all per-layer manifests with S3 paths, row counts, timestamps. |

## Testing

```bash
uv run pytest tests/unit tests/architecture   # after each fix
uv run pytest tests/mdm                       # for MDM-related changes
uv run edgar-warehouse --help                 # verify CLI
```

## Rules

- One commit per issue fix: `fix(data-architecture): issue-N <description>`
- Preserve loader idempotency (skip already-captured files by default)
- Do not change `from edgar.ownership import Ownership` import path
- Do not commit secrets or `.tfvars` with live values
- Do not broaden IAM policies
- Gold-affecting changes must respect `SERVING_EXPORT_ROOT` env var
