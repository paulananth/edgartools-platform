# Phase 8 Validation Strategy: ADV Bronze Discovery Contract

**Date:** 2026-06-03
**Status:** Ready

## Validation Architecture

Phase 8 is validated with local unit tests and source assertions. No live AWS call is required
for this phase.

## Required Checks

| ID | Requirement | Verification |
|----|-------------|--------------|
| V-08-01 | Registry-backed ADV discovery selects current ADV forms only | `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py -q` |
| V-08-02 | Explicit artifact fallback accepts bounded records without S3 listing | `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py -q` |
| V-08-03 | Missing primary/raw/unreadable artifacts produce issues and continue | `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py -q` |
| V-08-04 | Helper does not call SEC fetch or artifact refresh helpers | `rg -n "download_sec_bytes|refresh_filing_artifacts" edgar_warehouse/application/adv_bronze_discovery.py` returns no matches |
| V-08-05 | Ownership backfill behavior is not regressed | `uv run --extra s3 --with pytest pytest tests/application/test_parse_ownership_bronze.py -q` |

## Acceptance Gate

Phase 8 is ready to execute when `08-01-PLAN.md` covers all Phase 8 requirements:

- ADV-01
- ADV-02
- ADV-03
- ISO-01
- ISO-02
- ISO-03
