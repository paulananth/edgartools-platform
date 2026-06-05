---
plan: "10-02"
phase: 10-live-adv-backfill-validation
status: complete
completed_at: "2026-06-05"
---

# Plan 10-02 Summary: Silver Backfill + MDM Load

## What Was Done

1. **Preflight tests created** (`tests/mdm/test_adv_preflight.py`, MDM-ADV-02): 5 fixture-based tests prove the `_require_silver_reader` gate transitions FAIL→PASS for adviser and fund entity types. Tests use a tmp_path DuckDB with no network or S3. All 5 pass (commit `93efbe5`).

2. **Silver backfill run**: `edgar-warehouse parse-adv-bronze --artifact "ADV-105958-20241218,ADV,s3://..."` processed the Vanguard ADV XML uploaded in Plan 10-01. Result: `parsed=1, rows_written=3, errors=0`.

3. **Deliberate failure test (D-25)**: Non-existent artifact emitted `parse_adv_bronze_unreadable_artifact` event and continued — batch did not abort.

4. **Silver counts verified**:
   | Table | Count |
   |-------|-------|
   | sec_adv_filing | 1 |
   | sec_adv_office | 1 |
   | sec_adv_disclosure_event | 0 |
   | sec_adv_private_fund | 1 |

5. **MDM adviser load**: `mdm run --entity-type adviser` → exit 0
6. **MDM fund load**: `mdm run --entity-type fund` → exit 0 (3122 ms)

7. **Postgres counts**: `mdm_adviser=1, mdm_fund=1`

## Blockers Encountered (6 total)

| # | Blocker | Fix |
|---|---------|-----|
| 1 | psql not installed on macOS | docker exec mdm-postgres psql |
| 2 | WAREHOUSE_STORAGE_ROOT=s3:// caused S3 shard hydration instead of local DuckDB read | unset WAREHOUSE_STORAGE_ROOT |
| 3 | MDM schema not initialized (mdm_source_priority does not exist) | edgar-warehouse mdm migrate |
| 4 | migrate() blocked by 005_fundamentals_relationships.sql ALTER TABLE on re-run | Direct SQL INSERT bypass |
| 5 | KeyError: No source priority rule for adviser/adv_filing (×2) | INSERT ('all','adv_filing',2) + 3 rows via docker exec psql ON CONFLICT DO NOTHING |
| 6 | Executor socket timeouts (×2, ~20 min each) | Research pre-solved inline by orchestrator |

## Requirements Satisfied

- MDM-ADV-01: sec_adv_filing > 0 ✓, sec_adv_private_fund > 0 ✓, mdm_adviser > 0 ✓, mdm_fund > 0 ✓
- MDM-ADV-02: fixture preflight fail→pass automated test green ✓

## Deferred

Graph pipeline (backfill-relationships, sync-graph, verify-graph) deferred to Phase 5 resume.
