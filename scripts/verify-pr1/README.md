# PR-1 Verification Scripts

Manual verification harness for the Branch B fundamentals PR-1 (Snowflake source DDL + composite-key load procedure).

## What gets verified

| Stage | Script | Creds needed | What it checks |
|---|---|---|---|
| **1** | `01_check_local_schema.sh` | No | 6 `CREATE TABLE` blocks in `01_source_stage.sql`; `LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN` proc in `06_*.sql`; 3 dim entries in `03_*.sql`; 6 entries in `SNOWFLAKE_EXPORT_TABLES`; 6 dbt sources with correct naming; 6 dbt gold models reference the right sources; PR-1 unit tests pass |
| **2** | `02_smoke_builders.sh` | No | In-memory DuckDB → 6 PyArrow builders → row count + schema equality + `nullable=False` on PK columns + non-zero `fact_key` on dimensional rows |
| **3** | `03_check_snowflake_ddl.sh` | Yes | Applies all 3 SQL files to dev Snowflake; verifies 6 tables exist; verifies `NOT NULL` constraints on PK columns; verifies both load procs exist |
| **4** | `04_smoke_merge_proc.sh` | Yes | Composite-key MERGE is idempotent (INSERT same row twice → COUNT=1); update on conflict actually updates; NULL CIK/CONCEPT INSERTs are rejected (NOT NULL enforced); `LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN` parses and executes (returns "No run manifest" — expected, no real manifest at this stage) |
| **5** | _(deferred)_ | Yes | Full Parquet roundtrip via `gold-refresh` → S3 → COPY INTO → MERGE — depends on PR-2 |

## How to run

### Just the local checks (no Snowflake creds)

```bash
cd /Users/aneenaananth/projects/edgartools-platform
bash scripts/verify-pr1/run_all.sh --offline
```

### Full verification (requires Snowflake creds)

**One-time install** (the repo uses the modern `snow` CLI, not legacy `snowsql` — see [`docs/snowflake-cli-migration.md`](../../docs/snowflake-cli-migration.md) for the migration rationale and best practices):

```bash
pip install snowflake-cli-labs       # or: uv pip install snowflake-cli-labs
snow connection add                   # interactive — writes ~/.snowflake/connections.toml
snow connection list                  # confirm the connection name to set below
```

Set the required env vars:

```bash
# Required for stages 3 + 4
export SNOW_CONNECTION=edgartools-dev                     # name from `snow connection list`
export SNOWFLAKE_DATABASE=EDGARTOOLS_DEV
export SNOWFLAKE_DEPLOYER_ROLE=EDGARTOOLS_DEV_DEPLOYER
export SNOWFLAKE_STORAGE_ROLE_ARN=arn:aws:iam::077127448006:role/edgartools-dev-snowflake-s3
export SNOWFLAKE_EXPORT_ROOT_URL=s3://edgartools-dev-snowflake-export-077127448006/warehouse/artifacts/snowflake_exports/
export SNOWFLAKE_MANIFEST_SNS_TOPIC_ARN=arn:aws:sns:us-east-1:077127448006:edgartools-dev-snowflake-manifest-events

bash scripts/verify-pr1/run_all.sh
```

### Run a single stage

```bash
bash scripts/verify-pr1/01_check_local_schema.sh
bash scripts/verify-pr1/02_smoke_builders.sh
bash scripts/verify-pr1/03_check_snowflake_ddl.sh
bash scripts/verify-pr1/04_smoke_merge_proc.sh
```

## How to read the output

Each check prints:
- `✓ <description>` — pass (green)
- `✗ <description>` — fail (red)
- `! <description>` — warning (yellow)

Each stage ends with `[STAGE N OK]` or `[STAGE N FAILED]` and a count.

`run_all.sh` stops on the first stage failure to keep the output focused on the actual problem. Re-run the failing stage alone for full output.

## What "PR-1 is complete" means

PR-1 is **complete** when:

1. **Stages 1 + 2 pass** without Snowflake creds (proves the local artifacts are internally consistent — schemas match, builders produce correct shapes, dbt models reference real sources). This is the **review-time gate**.

2. **Stages 3 + 4 pass** against dev Snowflake (proves the DDL actually deploys, NOT NULL constraints land in Snowflake metadata, composite-key MERGE behaves correctly). This is the **deploy-time gate**.

3. **Optional pre-PR-2 sanity**: manually insert a row into `SEC_FINANCIAL_FACT` via `snow sql --connection $SNOW_CONNECTION --query "..."` and observe it in `EDGARTOOLS_DEV.EDGARTOOLS_SOURCE.SEC_FINANCIAL_FACT`. Stage 4 already does this.

Stage 5 (full Parquet roundtrip) is **NOT** required for PR-1 to be considered complete — it's the gate for **PR-2**, which is the warehouse export wiring.

## Idempotency

All scripts are safe to re-run:
- Stages 1, 2: pure inspection / in-memory; no side effects
- Stage 3: every `CREATE` uses `IF NOT EXISTS` or `OR REPLACE`; safe to re-deploy
- Stage 4: uses synthetic CIK `999999991` and cleans up via `trap cleanup EXIT`; no real data touched

## When a stage fails

Each script logs the specific check that failed. Common fixes:

- **Stage 1 `sources.yml MISSING <table>`** → check that `sources.yml` was committed; my edits used the dimensional names without `SEC_` prefix
- **Stage 1 `NOT NULL`** → check `01_source_stage.sql` — PK columns need `NOT NULL` after the type
- **Stage 2 `schema mismatch`** → silver column order differs from PyArrow schema order; use explicit SELECT list in the builder
- **Stage 3 `<table> NOT FOUND`** → snow connection or role issue; verify `SNOWFLAKE_DEPLOYER_ROLE` has CREATE TABLE in the source schema, and that `snow connection test --connection $SNOW_CONNECTION` succeeds
- **Stage 4 `NULL <col> INSERT was ACCEPTED`** → DDL did not apply NOT NULL constraint; re-run stage 3 and capture the deploy output by running `snow sql --connection $SNOW_CONNECTION --filename <the-tmp-file-path-from-the-failed-stage>` to see errors
- **`required command not found: snow`** → install via `pip install snowflake-cli-labs`
- **`required env var not set: SNOW_CONNECTION`** → set `export SNOW_CONNECTION=<your-connection-name>` (list with `snow connection list`)

## Adding a new stage 5 (PR-2 dependency)

After PR-2 lands, add `05_parquet_roundtrip.sh`:

```bash
# 1. Insert a row into silver/fundamentals/shard-0.duckdb
# 2. Run: edgar-warehouse gold-refresh
# 3. Confirm Parquet file lands at s3://.../warehouse/artifacts/snowflake_exports/sec_financial_fact/...
# 4. CALL LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN(<workflow>, <run_id>)
# 5. SELECT COUNT(*) FROM SEC_FINANCIAL_FACT WHERE CIK=<test_cik> → expect >0
```

Then add it to `STAGES[]` in `run_all.sh`.
