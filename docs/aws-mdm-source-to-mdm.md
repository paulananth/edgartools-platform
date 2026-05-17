# MDM Source-to-Entity Load Path (Phase 5)

This document covers the operator path for loading MDM entity rows from silver
DuckDB data without SEC re-fetching or Neo4j synchronisation. It is the
reference for Phase 5 of the neo4j-pipe workstream.

Phase boundaries:
- **Phase 5 (this document):** Silver source readiness and MDM entity loading
- **Phase 6:** Relationship derivation coverage
- **Phase 7:** Neo4j graph synchronisation

---

## Prerequisites

### Silver data must already exist

The MDM load path consumes already-captured bronze and silver data. It never
re-fetches SEC artifacts. If bronze primary XML is absent for a filing, the
`parse-ownership-bronze` command reports the gap as a `missing_artifact` metric
and continues (D-09, D-10). No silent SEC re-fetch occurs.

Required source tables and nonzero-row checks before MDM entity loading:

| Table | Required by |
|-------|-------------|
| `sec_company` | company entity loader |
| `sec_adv_filing` | adviser entity loader |
| `sec_adv_private_fund` | fund entity loader |
| `sec_company_filing` | person and security loaders |
| `sec_ownership_reporting_owner` | person entity loader (Form 3/4/5 parse) |
| `sec_ownership_non_derivative_txn` | security entity loader |

If ownership tables are empty, run `parse-ownership-bronze` first (see below).

### Environment variables

```bash
# Required: local path or s3:// URI to the silver DuckDB file
export MDM_SILVER_DUCKDB=/path/to/silver.duckdb

# Required for MDM writes: MDM Postgres (or SQLite for local testing)
export MDM_DATABASE_URL="postgresql://mdm:password@localhost:5432/mdm"

# Optional: local cache path when MDM_SILVER_DUCKDB is an s3:// URI
export MDM_LOCAL_SILVER_DUCKDB=/tmp/mdm-silver.duckdb

# Optional: AWS region for S3 reads
export AWS_DEFAULT_REGION=us-east-1
```

---

## Local Silver Path

Use a local `silver.duckdb` file when running on a developer machine or in a
container with a pre-downloaded silver copy.

```bash
export MDM_SILVER_DUCKDB=/data/silver/silver.duckdb
export MDM_DATABASE_URL="postgresql://mdm:password@localhost:5432/mdm"
```

### 1. Populate ownership tables (if empty)

If `sec_ownership_reporting_owner` has 0 rows, parse the existing bronze XMLs:

```bash
# Parse all Form 3/4/5 bronze XMLs already captured in sec_raw_object
edgar-warehouse parse-ownership-bronze

# Bounded run: process only the most recent 500 accessions
edgar-warehouse parse-ownership-bronze --limit 500

# Targeted run: re-process specific accessions (comma-separated)
edgar-warehouse parse-ownership-bronze \
  --accession-list 0001234567-24-000001,0001234567-24-000002
```

The command reads primary artifacts via `sec_filing_attachment` and
`sec_raw_object` only. If a primary XML is not registered, the accession is
counted in `missing_artifacts` and skipped without any SEC API call.

### 2. Run MDM entity loaders

```bash
# Load all five entity domains (company, adviser, fund, person, security)
edgar-warehouse mdm run --entity-type all

# Load a single domain
edgar-warehouse mdm run --entity-type company
edgar-warehouse mdm run --entity-type adviser
edgar-warehouse mdm run --entity-type fund
edgar-warehouse mdm run --entity-type person
edgar-warehouse mdm run --entity-type security

# Cap rows per domain (useful for smoke tests)
edgar-warehouse mdm run --entity-type all --limit 100
```

The `mdm run` preflight checks `MDM_SILVER_DUCKDB` and required tables before
opening the MDM database session. If a required table is missing or empty, the
command exits nonzero and prints an actionable message naming `MDM_SILVER_DUCKDB`.

### 3. Derive relationships (Phase 6 scope)

Relationship derivation is covered in Phase 6. The commands below are
documented here for operator awareness; they require populated entity tables
from step 2 above.

```bash
# Derive relationship instances from resolved entities and silver facts
edgar-warehouse mdm derive-relationships --target-per-type 100

# Derive specific relationship type
edgar-warehouse mdm derive-relationships \
  --target-per-type 100 \
  --relationship-type IS_INSIDER
```

### 4. Load relationships without Neo4j sync (Phase 6 scope, Phase 7 opt-in)

```bash
# Derive relationships and skip Neo4j sync (Phase 5/6 validation only)
edgar-warehouse mdm load-relationships \
  --target-per-type 100 \
  --skip-graph-sync

# Full path including Neo4j sync (Phase 7 — requires NEO4J_* credentials)
edgar-warehouse mdm load-relationships \
  --target-per-type 100
```

---

## S3-Backed Silver Path

Use the S3-backed path when running inside an ECS task or when the silver
DuckDB is stored in the platform S3 bucket.

```bash
# S3-backed silver: the file is downloaded to MDM_LOCAL_SILVER_DUCKDB before use
export MDM_SILVER_DUCKDB=s3://my-bucket/warehouse/silver/silver.duckdb
export MDM_LOCAL_SILVER_DUCKDB=/tmp/mdm-silver.duckdb
export MDM_DATABASE_URL="postgresql://mdm:password@mdm.internal:5432/mdm"
export AWS_DEFAULT_REGION=us-east-1
```

The `_silver_reader()` call in `edgar_warehouse/mdm/cli.py` detects the
`s3://` prefix and calls `object_storage.read_bytes()` to download the file
before opening a DuckDB connection. The download uses the AWS SDK credential
chain (IAM role, environment variables, or `~/.aws/credentials`).

After download, the same preflight table checks apply as for local paths.

### Downloading silver manually for ad-hoc inspection

```bash
aws s3 cp s3://my-bucket/warehouse/silver/silver.duckdb /tmp/silver.duckdb
export MDM_SILVER_DUCKDB=/tmp/silver.duckdb
```

---

## Source Readiness Diagnostics

Before running entity loaders, verify that source tables are populated:

```bash
# Quick row counts for all required Phase 5 source tables
uv run python3 - <<'EOF'
import duckdb, os
db = duckdb.connect(os.environ["MDM_SILVER_DUCKDB"], read_only=True)
tables = [
    "sec_company",
    "sec_company_filing",
    "sec_adv_filing",
    "sec_adv_private_fund",
    "sec_ownership_reporting_owner",
    "sec_ownership_non_derivative_txn",
]
for t in tables:
    try:
        n = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n}")
    except Exception as e:
        print(f"  {t}: MISSING ({e})")
EOF
```

Expected nonzero tables before a valid entity load:
- `sec_company` — at least 1 row per company in the universe
- `sec_company_filing` — Form 3/4/5 filings for person/security derivation
- `sec_adv_filing` — ADV submissions for adviser and fund domains
- `sec_ownership_reporting_owner` — parsed from `parse-ownership-bronze`

If `sec_ownership_reporting_owner` is zero, person and security entity loaders
will produce 0 rows. This is not an error — run `parse-ownership-bronze` first
(see "Populate ownership tables" above).

### Check sec_company_sync_state (current tracking column)

The company loader reads `sec_company_sync_state.tracking_status` to include
tracking metadata. This table is present in silver after a `bootstrap-batch`
or `bootstrap-next` run. If absent, the loader still succeeds and loads all
companies from `sec_company` without tracking metadata.

```bash
# Verify current silver tracking table is populated
uv run python3 - <<'EOF'
import duckdb, os
db = duckdb.connect(os.environ["MDM_SILVER_DUCKDB"], read_only=True)
n = db.execute("SELECT COUNT(*) FROM sec_company_sync_state").fetchone()[0]
active = db.execute("SELECT COUNT(*) FROM sec_company_sync_state WHERE tracking_status='active'").fetchone()[0]
print(f"sec_company_sync_state: {n} rows ({active} active)")
EOF
```

---

## Phase Boundaries

| Phase | Scope | Commands |
|-------|-------|----------|
| Phase 5 | Silver source readiness + entity loading | `parse-ownership-bronze`, `mdm run` |
| Phase 6 | Relationship derivation coverage | `mdm derive-relationships`, `mdm load-relationships --skip-graph-sync` |
| Phase 7 | Neo4j graph synchronisation | `mdm load-relationships`, `mdm sync-graph` |

### What Phase 5 does NOT do

- SEC re-fetch: absent bronze XMLs are reported, not re-fetched (D-09, D-10)
- Relationship derivation coverage: Phase 6 owns validation that IS_INSIDER,
  HOLDS, ISSUED_BY, IS_ENTITY_OF, MANAGES_FUND, and IS_PERSON_OF relationships
  are derived with expected coverage across all entity pairs
- Neo4j sync: Phase 7 owns NEO4J_URI credentials and `mdm sync-graph`
  execution; `--skip-graph-sync` is the Phase 5 boundary flag

---

## Isolation Constraints

The following files and directories are managed by the parallel loader-fix
workstream (Codex) and must not be edited from this workstream:

- `infra/aws-dev-application.json` — generated deployment JSON
- `.planning/workstreams/fix-pipelines/` — loader-fix planning artifacts
- `edgar_warehouse/application/warehouse_orchestrator.py` — loader-fix scope
  (except D-07/D-08 changes committed in Phase 5 plan 02)

---

## Idempotency

MDM entity loading is idempotent: running `mdm run` twice against the same
silver fixture leaves entity domain counts (`mdm_company`, `mdm_adviser`,
`mdm_person`, `mdm_security`, `mdm_fund`) unchanged. This is proven by
`TestEntityLoadIdempotentForDomainCounts` in
`tests/mdm/test_source_to_mdm_load_path.py`.

The identity keys per domain:
- company: CIK (`sec_company.cik`)
- adviser: CIK or CRD number (`sec_adv_filing.cik`, `sec_adv_filing.crd_number`)
- person: owner CIK or canonical name (`sec_ownership_reporting_owner.owner_cik`)
- security: source ref `accession_number:owner_index:txn_index` or title + issuer
- fund: adviser entity ID + normalised fund name
