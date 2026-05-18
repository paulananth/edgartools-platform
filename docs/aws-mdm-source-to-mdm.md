# AWS MDM: Source to MDM Load Path (Phase 5)

This document covers running the MDM entity loaders against a local or S3-backed silver DuckDB
produced from already-captured SEC EDGAR bronze artifacts. It does not describe bronze artifact
capture, Neo4j graph sync, or relationship derivation — those belong to later phases.

**Scope:** This guide is AWS/local only. Do not introduce Azure, Databricks, non-AWS storage
backends, new secret-management paths, or Terraform rollout steps for Phase 5 operations.

---

## Prerequisites

The silver DuckDB must already exist and contain the required source rows.
See the [Silver Readiness Diagnostics](#silver-readiness-diagnostics) section before running
MDM entity loads.

Runtime variables must be exported in your shell or injected as ECS task environment variables:

```bash
# Required for all MDM commands
export MDM_DATABASE_URL="postgresql+psycopg2://user:password@host:5432/mdm"

# Required for MDM entity loads from silver (see path options below)
export MDM_SILVER_DUCKDB="/path/to/silver.duckdb"    # local path
# or
export MDM_SILVER_DUCKDB="s3://edgartools-dev-warehouse/warehouse/silver.duckdb"  # S3-backed

# Optional: local cache path for S3-backed silver (avoids re-download on each run)
export MDM_LOCAL_SILVER_DUCKDB="/tmp/silver_local_cache.duckdb"
```

---

## Silver Source Options

### Local Path

Set `MDM_SILVER_DUCKDB` to an absolute path on the local filesystem:

```bash
export MDM_SILVER_DUCKDB="/data/silver/silver.duckdb"
```

The MDM CLI opens the DuckDB file read-only and loads entity rows without copying it.

### S3-Backed Path

Set `MDM_SILVER_DUCKDB` to an S3 URI. The CLI downloads the file through the existing
`object_storage.read_bytes()` adapter (backed by `fsspec`/`s3fs`):

```bash
export MDM_SILVER_DUCKDB="s3://edgartools-dev-warehouse/warehouse/silver.duckdb"
```

The AWS credential chain (`~/.aws/credentials`, EC2 instance profile, ECS task role) must grant
`s3:GetObject` on the warehouse bucket path.

Optionally cache the downloaded file locally to avoid re-downloading on repeated runs:

```bash
export MDM_LOCAL_SILVER_DUCKDB="/tmp/silver_local_cache.duckdb"
```

If `MDM_LOCAL_SILVER_DUCKDB` is set and the file already exists at that path, the CLI skips the
S3 download and reads from the cached local file instead.

**Note:** Unsupported URI protocols (e.g., `ftp://`, `http://`) are rejected by the
object_storage allowlist before any download is attempted.

---

## Step 1: Parse Ownership Bronze

Before running MDM entity loads, parse existing bronze Form 3/4/5 primary XML artifacts into
silver ownership tables. This step reads already-captured bronze artifacts and writes to
`sec_ownership_reporting_owner` and transaction tables in the silver DuckDB.

```bash
# Parse all unprocessed ownership XML from the bronze artifact registry
edgar-warehouse parse-ownership-bronze

# Bounded run: limit to N accessions (useful for validation)
edgar-warehouse parse-ownership-bronze --limit 100

# Bounded run: specific accession numbers only
edgar-warehouse parse-ownership-bronze --accession-list 0001234567-24-000001,0009876543-24-000002
```

**Important:** `parse-ownership-bronze` reads primary XML from the artifact registry
(`sec_filing_attachment` joined to `sec_raw_object`) and does NOT make SEC API calls. If the
primary XML artifact is absent from `sec_raw_object` for a given accession, the command reports
the gap and skips that filing — it does not re-fetch from SEC. Absent bronze primary XML means
the bronze capture phase was incomplete; re-running bronze capture is outside Phase 5 scope
unless explicitly requested.

The command is idempotent: accessions already present in `sec_ownership_reporting_owner` are
skipped on repeat runs.

---

## Step 2: Run MDM Entity Loaders

Load all five entity domains (company, adviser, person, security, fund) from silver into MDM:

```bash
edgar-warehouse mdm run --entity-type all
```

Or load a single entity type:

```bash
edgar-warehouse mdm run --entity-type company
edgar-warehouse mdm run --entity-type adviser
edgar-warehouse mdm run --entity-type person
edgar-warehouse mdm run --entity-type security
edgar-warehouse mdm run --entity-type fund
```

Add `--limit N` to process at most N entities per type:

```bash
edgar-warehouse mdm run --entity-type all --limit 100
```

The loaders are idempotent: running `mdm run` twice against the same silver data leaves
`mdm_company`, `mdm_adviser`, `mdm_person`, `mdm_security`, and `mdm_fund` counts stable.

**Note:** `MDM_SILVER_DUCKDB` must be set and readable before this command opens the MDM
database session. If the variable is absent or the DuckDB cannot be opened, the command exits
with a nonzero code and names `MDM_SILVER_DUCKDB` in the error message without opening an MDM
session or mutating MDM state.

---

## Step 3: Derive Relationships (Phase 6 — for reference)

Relationship derivation is Phase 6 scope. When you are ready to move to relationship coverage:

```bash
edgar-warehouse mdm derive-relationships --target-per-type 100
```

---

## Step 4: Load Relationships (Skip Graph Sync for Source Readiness)

To validate source readiness without pushing to Neo4j, use `--skip-graph-sync`:

```bash
edgar-warehouse mdm load-relationships --skip-graph-sync
```

This runs entity resolution and writes relationship instances to MDM SQL but skips the Neo4j
graph sync step. Useful for verifying source coverage before Neo4j credentials are available
(Neo4j sync is Phase 7 scope).

---

## Silver Readiness Diagnostics

Run these checks before entity loads to confirm the silver DuckDB has the required source rows.

### Required Tables and Minimum Counts

| Table | Required For | Minimum Rows |
|-------|-------------|-------------|
| `sec_company` | Company, all entity types | 1 |
| `sec_company_filing` | Person, security, all | Forms 3/4/5 present |
| `sec_filing_attachment` | `parse-ownership-bronze` artifact read | 1 primary row per Form 3/4/5 |
| `sec_raw_object` | `parse-ownership-bronze` artifact content | 1 row per Form 3/4/5 attachment |
| `sec_ownership_reporting_owner` | Person, security, IS_INSIDER | 1 |
| `sec_adv_filing` | Adviser, fund | 1 |
| `sec_adv_private_fund` | Fund | 1 |

### DuckDB Diagnostic Queries

Connect to the silver DuckDB and run:

```sql
-- Company source counts
SELECT COUNT(*) AS company_count FROM sec_company;

-- Ownership filing counts (Forms 3/4/5)
SELECT form, COUNT(*) AS filing_count
FROM sec_company_filing
WHERE form IN ('3','3/A','4','4/A','5','5/A')
GROUP BY form
ORDER BY form;

-- Artifact registry availability
SELECT COUNT(*) AS attachment_count
FROM sec_filing_attachment
WHERE is_primary = TRUE;

SELECT COUNT(*) AS raw_object_count
FROM sec_raw_object;

-- Parsed ownership rows
SELECT COUNT(*) AS owner_count FROM sec_ownership_reporting_owner;

-- ADV source counts
SELECT COUNT(*) AS adv_filing_count FROM sec_adv_filing;
SELECT COUNT(*) AS private_fund_count FROM sec_adv_private_fund;
```

### Interpreting Results

| Finding | Cause | Action |
|---------|-------|--------|
| Nonzero `sec_company_filing` Forms 3/4/5 + zero `sec_raw_object` | Bronze artifacts were not captured | Bronze capture is outside Phase 5 scope; contact operator who ran bronze pipeline |
| Nonzero `sec_raw_object` + zero `sec_ownership_reporting_owner` | `parse-ownership-bronze` not yet run or failed | Run `edgar-warehouse parse-ownership-bronze --limit 100` and review output |
| Zero `sec_adv_filing` | ADV data was not loaded | ADV forms must be in silver before adviser/fund entity loads |

---

## Scope Boundaries

| Capability | Phase |
|-----------|-------|
| Bronze artifact capture (SEC fetch) | Pre-Phase 5 / outside this path |
| Silver ownership backfill from bronze | Phase 5 (`parse-ownership-bronze`) |
| MDM entity loads (all 5 domains) | Phase 5 (`mdm run`) |
| Relationship derivation coverage | Phase 6 (`mdm derive-relationships`) |
| Neo4j graph sync | Phase 7 (`mdm sync-graph`, `mdm verify-graph`) |

**Protected artifacts:** Generated deployment JSON (e.g., `infra/aws-dev-application.json`) and
loader-fix workstream artifacts must not be edited during Phase 5 MDM operations. These are
governed by ISO-01 and ISO-02 workstream isolation rules.

---

## AWS ECS Execution

For production runs via Step Functions:

```bash
# Start the MDM entity load Step Function
STATE_MACHINE_ARN="$(
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["state_machines"]["mdm_run"])' \
    infra/aws-dev-application.json
)"

aws stepfunctions start-execution \
  --region us-east-1 \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --input '{"entity_type":"all"}'
```

Monitor execution:

```bash
aws stepfunctions describe-execution \
  --execution-arn <execution-arn> \
  --query 'status'
```

---

## Common Errors

| Error | Meaning | Fix |
|-------|---------|-----|
| `MDM_SILVER_DUCKDB is required` | Variable not set | `export MDM_SILVER_DUCKDB=...` |
| `Unsupported protocol` in silver path | Protocol not in allowlist | Use `/local/path`, `s3://`, or a supported scheme |
| `Table not found: sec_ownership_reporting_owner` | Preflight failed; table missing | Run `parse-ownership-bronze` first |
| `No source priority rule for ...` | MDM schema not seeded | Run `edgar-warehouse mdm migrate` |
| `CatalogException: Table with name sec_tracked_universe` | Stale pipeline code | Upgrade to current `edgar_warehouse.mdm.pipeline` |
