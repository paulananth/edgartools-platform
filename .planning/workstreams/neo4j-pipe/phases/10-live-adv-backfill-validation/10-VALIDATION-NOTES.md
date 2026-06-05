# Phase 10: Live ADV Backfill Validation Notes

## ADV Bronze Acquisition

**Method:** sec-bulk-csv
**Source:** SEC FOIA Form ADV bulk data download
**Source URL:** https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data
**Data file:** adv-filing-data-20111105-20241231-part1.zip / IA_ADV_Base_A_20111105_20241231.csv
**Private fund data:** adv-filing-data-20111105-20241231-part2.zip / IA_Schedule_D_7B1_20111105_20241231.csv
**Adviser:** THE VANGUARD GROUP, INC. / VANGUARD GROUP INC
**CRD:** 105958
**SEC File Number:** 801-11953
**Filing Date:** 2024-12-18 (most recent filing, FilingID=1919760)
**Accession:** ADV-105958-20241218

**Note:** Vanguard's December 2024 ADV Part 1 filing was extracted from the SEC FOIA bulk CSV dataset.
One private fund (CSF PRIVATE FUND) was present in IA_Schedule_D_7B1 for this filing.
The sec-bulk-csv method uses real Form ADV Part 1 data from all registered investment advisers,
filtered for CRD 105958. Private-fund detail (Schedule D 7B1) IS available for this filing.

## S3 Bronze Upload

**S3 URI:** s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/cik=105958/accession=ADV-105958-20241218/primary_doc.xml
**CIK:** 105958
**FORM:** ADV
**Size:** 681 bytes
**Verified:** aws s3 ls confirms one primary_doc.xml with nonzero size

## Storage Adapter Readability

read_bytes returned 681 bytes for the S3 URI above. Exit 0. ✓

## Wave 2 --artifact String

ADV-105958-20241218,ADV,s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/cik=105958/accession=ADV-105958-20241218/primary_doc.xml,105958

## Silver Backfill

**Command:**
```bash
edgar-warehouse parse-adv-bronze \
  --artifact "ADV-105958-20241218,ADV,s3://edgartools-dev-bronze-077127448006/warehouse/bronze/filings/sec/cik=105958/accession=ADV-105958-20241218/primary_doc.xml,105958"
```

**parse_adv_bronze_completed event:**
```json
{"discovered": 1, "errors": 0, "event": "parse_adv_bronze_completed", "explicit_artifacts": 1, "missing_artifacts": 0, "parsed": 1, "rows_written": 3, "selected": 1, "skipped": 0, "unreadable_artifacts": 0}
```

**Deliberate failure test (D-25):**
```bash
edgar-warehouse parse-adv-bronze --artifact "FAKE-ACCESSION-0,ADV,s3://invalid-path/fake.xml"
```
Non-fatal event emitted: `{"event": "parse_adv_bronze_unreadable_artifact", "accession_number": "FAKE-ACCESSION-0", "reason": "unreadable_storage_path"}` — run continued, batch did not abort. ✓

**Silver row counts (local DuckDB: /tmp/edgar-warehouse-silver/silver/sec/silver.duckdb):**

| Table | Count |
|-------|-------|
| sec_adv_filing | 1 |
| sec_adv_office | 1 |
| sec_adv_disclosure_event | 0 |
| sec_adv_private_fund | 1 |

**sec_adv_filing row:** ADV-105958-20241218, THE VANGUARD GROUP, INC., CRD=105958, date=2024-12-18
**sec_adv_private_fund row:** ADV-105958-20241218, CSF PRIVATE FUND, Hedge Fund, Cayman Islands, AUM=$276,012,482

MDM-ADV-01 satisfied: sec_adv_filing > 0 ✓ and sec_adv_private_fund > 0 ✓

## MDM Load

**Commands run (in workspace worktree; WAREHOUSE_STORAGE_ROOT unset):**
```bash
export MDM_DATABASE_URL="postgresql://postgres:test@localhost:5432/mdm"
export MDM_SILVER_DUCKDB="/tmp/edgar-warehouse-silver/silver/sec/silver.duckdb"
unset WAREHOUSE_STORAGE_ROOT
uv run --extra s3 edgar-warehouse mdm run --entity-type adviser
uv run --extra s3 edgar-warehouse mdm run --entity-type fund
```

**Results:**

| Command | Exit Code | Event |
|---------|-----------|-------|
| mdm run --entity-type adviser | 0 | mdm_command_completed |
| mdm run --entity-type fund | 0 | mdm_command_completed (3122 ms) |

**Postgres counts (Colima local MDM):**

| Table | Count |
|-------|-------|
| mdm_adviser | 1 |
| mdm_fund | 1 |

MDM-ADV-01 fully satisfied: sec_adv_filing > 0 ✓, sec_adv_private_fund > 0 ✓, mdm_adviser > 0 ✓, mdm_fund > 0 ✓

**Blockers encountered during Task 3 (recorded per user request):**

| # | Blocker | Root Cause | Fix |
|---|---------|------------|-----|
| 1 | psql: command not found | psql not installed on macOS | docker exec mdm-postgres psql … |
| 2 | MDM_SILVER_DUCKDB ignored | WAREHOUSE_STORAGE_ROOT=s3:// causes S3 shard hydration path | unset WAREHOUSE_STORAGE_ROOT |
| 3 | relation "mdm_source_priority" does not exist | MDM schema not initialized | edgar-warehouse mdm migrate |
| 4 | migrate silently skipped seeding | 005_fundamentals_relationships.sql ALTER TABLE fails on re-run, blocking seed_defaults() | Direct SQL INSERT via docker exec psql ON CONFLICT DO NOTHING |
| 5 | KeyError: No source priority rule for adviser/adv_filing (×2) | mdm_source_priority table empty; seeding never completed | Manually INSERT ('all','adv_filing',2) + 3 other rows |
| 6 | Executor socket timeouts (×2, ~20 min each) | Executor agents read large files before acting | Research pre-solved inline; pre-digested data passed to executor |

**Graph pipeline (backfill-relationships, sync-graph, verify-graph) and Neo4j startup deferred to Phase 5 resume per orchestrator re-scope.**

## Phase 10 COMPLETE

All three requirements are satisfied:

| Gate | Status | Evidence |
|------|--------|----------|
| MDM-ADV-01: sec_adv_filing > 0 | PASS | Silver: 1 row (Vanguard ADV-105958-20241218) |
| MDM-ADV-01: sec_adv_private_fund > 0 | PASS | Silver: 1 row (CSF PRIVATE FUND, Hedge Fund, AUM $276M) |
| MDM-ADV-01: mdm_adviser > 0 | PASS | Postgres: 1 row |
| MDM-ADV-01: mdm_fund > 0 | PASS | Postgres: 1 row |
| MDM-ADV-02: fixture preflight fail→pass | PASS | 5/5 tests green (test_adv_preflight.py, commit 93efbe5) |
| MDM-ADV-03: runbook documents ADV backfill + Phase 5 resume | PASS | docs/aws-mdm-source-to-mdm.md: Step 1b + Phase 5 Resume Path section added |

**Deferred (out of scope for Phase 10):**
- Graph pipeline (backfill-relationships, sync-graph, verify-graph) — deferred to Phase 5 resume
- Neo4j startup — deferred to Phase 5 resume

## Next Steps (Phase 5 Resume)

Phase 10 validated the single-sample slice (1 adviser, 1 fund). Full-scale Phase 5 resume sequence:

1. Obtain ADV bronze for all target investment advisers from IAPD (FINRA) — see `docs/aws-mdm-source-to-mdm.md` Step 1b
2. Run `edgar-warehouse parse-adv-bronze` to populate `sec_adv_filing` and `sec_adv_private_fund`
3. Confirm `sec_adv_filing > 0` (adviser) and `sec_adv_private_fund > 0` (fund)
4. Run `edgar-warehouse mdm run --entity-type adviser` then `--entity-type fund`
5. Run `edgar-warehouse mdm backfill-relationships → sync-graph → verify-graph` (full graph sync)

## Rollback

Silver DuckDB rollback (D-27):
```bash
duckdb /tmp/edgar-warehouse-silver/silver/sec/silver.duckdb \
  "DELETE FROM sec_adv_filing WHERE accession_number = 'ADV-105958-20241218';
   DELETE FROM sec_adv_office WHERE accession_number = 'ADV-105958-20241218';
   DELETE FROM sec_adv_disclosure_event WHERE accession_number = 'ADV-105958-20241218';
   DELETE FROM sec_adv_private_fund WHERE accession_number = 'ADV-105958-20241218';"
```

MDM Postgres rollback (run after Task 3):
```bash
psql "postgresql://postgres:test@localhost:5432/mdm" \
  -c "DELETE FROM mdm_adviser WHERE source_crd = '105958';
      DELETE FROM mdm_fund WHERE name = 'CSF PRIVATE FUND';"
```
