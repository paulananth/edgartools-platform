---
phase: 08
slug: adv-bronze-discovery-contract
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-03
---

# Phase 8 - Validation Strategy

Per-phase validation contract for the ADV bronze discovery/read helper.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 9.0.3 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py -q` |
| **Full suite command** | `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q` |
| **Estimated runtime** | ~14 seconds |

## Sampling Rate

- **After every task commit:** Run `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py -q`
- **After every plan wave:** Run `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~14 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 08-01 | 1 | ADV-01: Discovery selects only existing ADV filings/artifacts without calling SEC APIs. | T-08-03 | Helper has no SEC download or artifact-refresh dependency and tests fail if those helpers are invoked. | unit + source check | `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py -q`; `bash -lc '! rg -n -e "download_sec_bytes" -e "refresh_filing_artifacts" -e "fsspec\\.filesystem" edgar_warehouse/application/adv_bronze_discovery.py'` | yes | green |
| 08-01-01 | 08-01 | 1 | ADV-02: Registry rows are preferred and explicit existing artifact records are a bounded fallback. | T-08-01, T-08-02 | Discovery uses fixed ADV forms, fixed registry accessors, and storage paths are read only through the storage adapter contract. | unit + source check | `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py -q`; `rg -n -e "def discover_adv_bronze_artifacts" -e "def read_adv_bronze_artifacts" -e "ADV_FORMS" edgar_warehouse/application/adv_bronze_discovery.py` | yes | green |
| 08-01-01 | 08-01 | 1 | ADV-03: Missing or unreadable artifacts are structured issues and do not abort the batch. | T-08-01 | Missing primary attachment, missing raw object, empty storage path, and unreadable path cases continue processing. | unit | `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py -q` | yes | green |
| 08-01-02 | 08-01 | 1 | ISO-01: Work stays isolated to the `neo4j-pipe` source, tests, docs, and planning files. | - | Validation covers only Phase 8 helper/test surfaces and does not require loader-fix or generated deployment JSON edits. | regression + review | `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q` | yes | green |
| 08-01-02 | 08-01 | 1 | ISO-02: AWS/local focus remains intact, with no non-AWS storage, registry, workflow, or secret path. | T-08-01 | Reads use the existing object storage adapter or injected test double; no new storage protocol handling is introduced. | unit + source check | `bash -lc '! rg -n -e "download_sec_bytes" -e "refresh_filing_artifacts" -e "fsspec\\.filesystem" edgar_warehouse/application/adv_bronze_discovery.py'` | yes | green |
| 08-01-02 | 08-01 | 1 | ISO-03: Gold/dbt, Snowflake graph sync, and unrelated Step Functions behavior remain untouched. | - | Phase 8 scope is limited to ADV bronze discovery and ownership regression tests. | regression + review | `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q` | yes | green |

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

## Manual-Only Verifications

All phase behaviors have automated verification. Live dev S3 ADV backfill validation is intentionally Phase 10 scope, not a Phase 8 manual gap.

## Validation Audit

| Audit Date | Requirements | Covered | Partial | Missing |
|------------|--------------|---------|---------|---------|
| 2026-06-03 | 6 | 6 | 0 | 0 |

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

## Commands Run

| Command | Result |
|---------|--------|
| `uv run python -m py_compile edgar_warehouse/application/adv_bronze_discovery.py` | passed |
| `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py -q` | passed: 5 tests |
| `uv run --extra s3 --with pytest pytest tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q` | passed: 18 tests, 3 upstream `edgartools` deprecation warnings |
| `rg -n -e "def discover_adv_bronze_artifacts" -e "def read_adv_bronze_artifacts" -e "ADV_FORMS" edgar_warehouse/application/adv_bronze_discovery.py` | passed |
| `bash -lc '! rg -n -e "download_sec_bytes" -e "refresh_filing_artifacts" -e "fsspec\\.filesystem" edgar_warehouse/application/adv_bronze_discovery.py'` | passed |

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15 seconds
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-03
