# Codex: Fix Data Architecture Issues

PR: https://github.com/paulananth/edgartools-platform/pull/117
Issues doc: `docs/data-architecture-issues.md` (12 issues, 5-whys per issue)

## Priority Order

### Phase 1 — High Severity (start here)

| # | Issue | Approach |
|---|-------|----------|
| 1 | Silver DuckDB sharding — no distributed write guarantees | Consider adding a `ShardedSilverWriter` that acquires a shard-level advisory lock before writing. Or collapse shards back to a single DuckDB if writes are serial per-CIK. Add a `reconcile_shards()` command that compares row counts + latest checksums across shards and reports divergence. |
| 3 | Branch A & B silver databases — no referential integrity | Merge fundamentals tables into the main silver DuckDB schema. Move `sec_financial_fact`, `sec_financial_derived`, `sec_earnings_release`, `sec_accounting_flag`, `sec_executive_record`, `sec_thirteenf_holding` DDL into the main `_DDL` string in `silver_store.py`. Remove the separate fundamentals shard path. |
| 4 | No pipeline-level transaction or versioning | Add a `pipeline_run` table to silver (`pipeline_run_id`, `state`, `bronze_sha256`, `silver_rownum_hash`, `gold_manifest_id`). Every command that touches multiple layers writes a row and updates it atomically. Add `verify_pipeline_run <id>` command that re-checks all hashes and reports drift. |
| 10 | Destructive PK migrations risk data loss | Replace the DROP TABLE pattern in `_migrate_financial_period_end_pk()` and `_migrate_financial_fact_period_start_pk()` with a `CREATE TABLE new_table AS SELECT ...` + `RENAME TABLE` pattern that keeps the old table as a backup until the migration is verified. |
| 11 | No end-to-end data quality validation framework | Add a `validate-data-quality` command that: (1) checks row counts monotonic increase across runs, (2) verifies FK-style consistency between silver tables, (3) compares gold row count to silver row count, (4) reports NULL ratios for critical columns. Wire into CI/Step Functions as a post-gold step. |

### Phase 2 — Medium Severity

| # | Issue | Approach |
|---|-------|----------|
| 2 | Gold is a transient re-export | Add a `gold_manifest` table to silver that records the `run_id`, per-table row counts, sha256 of each Parquet file, and the DuckDB hash used. Next gold-refresh can diff against previous and warn if hash didn't change but row count did (upstream data drift). |
| 5 | Gold schema evolution requires coordinated breaking changes | Move PyArrow schemas from constants to a versioned YAML file (`config/gold_schemas.yaml`). Add a `SCHEMA_VERSION` key. On startup, compare against the version that produced the existing Snowflake external tables and warn on mismatch. |
| 6 | MDM overloaded with pipeline orchestration state | Move the CIK universe tracking status (`active`/`bootstrap_pending`) back into silver (`sec_company_sync_state.tracking_status` already exists and tracks this). Keep MDM for entity resolution only. |
| 8 | Two independent filing discovery mechanisms with no unified schedule | Add a `discovery_checkpoint` table that records which mechanism last checked each CIK/date. The `daily-incremental` and `bootstrap-next` commands both read/write this table so they don't overlap or miss filings. |
| 9 | No database migration framework | Add a `schema_migration` table that records each migration name + applied_at timestamp. Convert `_ensure_schema_evolution()` to read this table and apply migrations in order. Each migration is a named function, not an ALTER TABLE in the constructor. |

### Phase 3 — Low Severity

| # | Issue | Approach |
|---|-------|----------|
| 7 | Serving export abstraction is leaky | Rename all `snowflake_export_*` methods to `serving_export_*`. Create a `ServingTarget` protocol class. Have `SnowflakeTarget` and `DatabricksTarget` implement it. Route all exports through the protocol. |
| 12 | Manifest fragmentation | Add a `run_manifest.json` at the run root that lists all per-layer manifests with their S3 paths, row counts, and timestamps. Write it as the last step of every command. |

## Testing

After each fix, run:

```bash
uv run pytest tests/unit tests/architecture
```

For MDM-related changes:

```bash
uv run pytest tests/mdm
```

Verify the CLI still works:

```bash
uv run edgar-warehouse --help
python -c "from edgar_warehouse.cli import main; print('OK')"
```

## Working conventions

- Each issue fix should be a separate commit with a message like `fix(data-architecture): issue-1 silver shard reconciliation`
- Do not commit secrets or `.tfvars` with live values
- Preserve loader idempotency (default skips already-captured SEC files)
- Do not broaden IAM policies
- Do not change the `edgartools` ownership parser import path (`from edgar.ownership import Ownership`)
- Gold-affecting changes must verify `SERVING_EXPORT_ROOT` env var is respected
