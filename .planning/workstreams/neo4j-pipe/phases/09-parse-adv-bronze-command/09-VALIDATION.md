---
phase: 09
slug: parse-adv-bronze-command
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-03
---

# Phase 9 - Validation Strategy

Per-phase validation contract for the ADV bronze-to-silver parse command.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 9.0.3 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py -q` |
| **Full suite command** | `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q` |
| **Estimated runtime** | ~8 seconds |

## Sampling Rate

- **After every task commit:** Run `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py -q`
- **After every plan wave:** Run `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~8 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 09-01 | 1 | ADV-04: CLI exposes `parse-adv-bronze --accession-list ...`, `--limit N`, and explicit existing-artifact input. | T-09-02, T-09-04 | Operator inputs are bounded to fixed fields and the command remains outside export-setting command sets. | unit + CLI smoke | `uv run edgar-warehouse parse-adv-bronze --help`; `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py -q` | yes | green |
| 09-01-02 | 09-01 | 1 | ADV-05: Re-running skips already parsed ADV accessions by default and limits count not-yet-parsed candidates. | T-09-03 | Already parsed accessions are skipped before storage reads; merge methods provide the second idempotency layer. | unit | `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py -q` | yes | green |
| 09-01-02 | 09-01 | 1 | ADV-06: `parse_adv` output is merged into all four current ADV silver tables. | T-09-03 | Parsed filing, office, disclosure event, and private fund rows are written through fixed ADV merge methods. | unit | `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py -q` | yes | green |
| 09-01-03 | 09-01 | 1 | ADV-07: Focused tests cover registry reads, explicit existing bronze paths, missing/unreadable artifacts, parser errors, idempotency, and no SEC fetch helpers. | T-09-01, T-09-02, T-09-03 | ADV parse behavior reads existing bronze only, continues through recoverable errors, and hard-fails tests if SEC fetch helpers are invoked. | unit + regression | `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q` | yes | green |
| 09-01-02 | 09-01 | 1 | AWS scope: no gold/dbt/Snowflake export, non-AWS deployment path, Step Functions, or SEC alternate URL load behavior is added. | T-09-04 | Runtime settings and export command classifications do not include `parse-adv-bronze`; alternate SEC URL load testing remains separate backlog scope. | source check | `bash -lc '! rg -n "parse-adv-bronze" edgar_warehouse/infrastructure/warehouse_settings.py'` | yes | green |

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

## Manual-Only Verifications

All phase behaviors have automated verification. Live dev S3 command validation is intentionally Phase 10 scope, not a Phase 9 manual gap.

## Validation Audit

| Audit Date | Requirements | Covered | Partial | Missing |
|------------|--------------|---------|---------|---------|
| 2026-06-03 | 5 | 5 | 0 | 0 |

## Commands Run

| Command | Result |
|---------|--------|
| `uv run edgar-warehouse parse-adv-bronze --help` | passed |
| `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py -q` | passed: 8 tests, 3 upstream `edgartools` deprecation warnings |
| `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q` | passed: 26 tests, 3 upstream `edgartools` deprecation warnings |
| `bash -lc '! rg -n "parse-adv-bronze" edgar_warehouse/infrastructure/warehouse_settings.py'` | passed |
| `rg -n "parse-adv-bronze|_handle_parse_adv_bronze|parse_adv_bronze|_run_parse_adv_bronze|merge_adv_filings|merge_adv_private_funds" edgar_warehouse/cli.py edgar_warehouse/application/commands edgar_warehouse/application/warehouse_orchestrator.py edgar_warehouse/infrastructure/dataset_path_catalog.py` | passed |
| `uv run python -m py_compile edgar_warehouse/cli.py edgar_warehouse/application/commands/parse_adv_bronze.py edgar_warehouse/application/warehouse_orchestrator.py` | passed |

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10 seconds
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-03
