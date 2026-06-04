---
phase: 09-parse-adv-bronze-command
verified: 2026-06-04T00:25:46Z
status: passed
score: 4/4 must-haves verified
---

# Phase 9: Parse ADV Bronze Command Verification Report

**Phase Goal:** `edgar-warehouse parse-adv-bronze` can parse selected existing ADV bronze artifacts into current silver ADV tables idempotently.  
**Verified:** 2026-06-04T00:25:46Z  
**Status:** passed

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | CLI exposes `parse-adv-bronze --accession-list ...` and `parse-adv-bronze --limit N`. | VERIFIED | `edgar_warehouse/cli.py` defines `_handle_parse_adv_bronze` and the `parse-adv-bronze` subparser with `--limit`, `--accession-list`, `--artifact`, and `--run-id`; `uv run edgar-warehouse parse-adv-bronze --help` passed. |
| 2 | The command uses `edgar_warehouse.parsers.adv` and existing `SilverDatabase.merge_adv_*` methods. | VERIFIED | `_run_parse_adv_bronze` imports `parse_adv`, calls Phase 8 discovery/read helpers, and calls `merge_adv_filings`, `merge_adv_offices`, `merge_adv_disclosure_events`, and `merge_adv_private_funds`. |
| 3 | Re-running the command against the same artifacts skips or upserts without duplicate `sec_adv_*` rows. | VERIFIED | The runner fetches `SELECT DISTINCT accession_number FROM sec_adv_filing`, skips already parsed accessions before storage read, and silver merge methods use existing upserts. Tests prove already parsed accessions are skipped before `read_bytes`. |
| 4 | Focused tests cover registry reads, explicit bronze path reads, missing artifacts, parser errors, and idempotency. | VERIFIED | `tests/application/test_parse_adv_bronze.py` covers CLI parsing, registry and explicit reads, already parsed skip, limit-after-skip, missing/unreadable artifacts, parser errors, and hard-failing SEC fetch guards. Combined regression test command passed with 26 tests. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `edgar_warehouse/cli.py` | ADV operator CLI | EXISTS + SUBSTANTIVE | Defines explicit artifact parser, command handler, and subparser. |
| `edgar_warehouse/application/commands/parse_adv_bronze.py` | Command shim | EXISTS + SUBSTANTIVE | Delegates to `run_command("parse-adv-bronze", args)`. |
| `edgar_warehouse/application/commands/__init__.py` | Command registry | EXISTS + WIRED | Imports `parse_adv_bronze` and registers `"parse-adv-bronze"`. |
| `edgar_warehouse/application/warehouse_orchestrator.py` | Orchestrator runner | EXISTS + SUBSTANTIVE + WIRED | Dispatches command, resolves scope, reads existing bronze, parses, merges ADV silver rows, emits metrics/events. |
| `edgar_warehouse/infrastructure/dataset_path_catalog.py` | Manifest path support | EXISTS + WIRED | Adds `parse-adv-bronze` to the operator-command manifest branch. |
| `tests/application/test_parse_adv_bronze.py` | Behavior regression tests | EXISTS + SUBSTANTIVE | 8 tests passed; combined regression suite passed. |

**Artifacts:** 6/6 verified

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| CLI | Runtime command registry | `run_command("parse-adv-bronze", args)` and command shim | WIRED | CLI handler and command module both delegate to the orchestrator command name. |
| Orchestrator dispatch | ADV parse runner | `_capture_bronze_raw` branch | WIRED | `command_name == "parse-adv-bronze"` calls `_run_parse_adv_bronze`. |
| ADV runner | Phase 8 discovery/read helper | `discover_adv_bronze_artifacts`, `read_adv_bronze_artifacts(..., read_bytes_fn=read_bytes)` | WIRED | Uses existing bronze artifact contract and storage adapter injection. |
| ADV runner | Silver ADV tables | `merge_adv_*` calls | WIRED | All four current ADV silver merge methods are called. |
| Tests | No SEC fetch behavior | Patches `download_sec_bytes` and `refresh_filing_artifacts` to raise | WIRED | Tests fail if SEC fetch helpers are called during ADV parse behavior. |

**Wiring:** 5/5 connections verified

## Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| ADV-04: `parse-adv-bronze` parses selected ADV artifacts and writes all four ADV silver tables. | SATISFIED | - |
| ADV-05: `parse-adv-bronze` supports `--accession-list`, `--limit`, and skips already parsed ADV accessions by default. | SATISFIED | - |
| ADV-06: The backfill path is idempotent and does not duplicate ADV rows or corrupt ownership rows. | SATISFIED | - |
| ADV-07: Tests prove no SEC network fetch occurs during backfill. | SATISFIED | - |

**Coverage:** 4/4 requirements satisfied

## Anti-Patterns Found

None.

**Anti-patterns:** 0 found (0 blockers, 0 warnings)

## Human Verification Required

None - all Phase 9 scope is covered by source inspection and automated tests. Live S3 validation is Phase 10.

## Gaps Summary

**No gaps found.** Phase goal achieved. Ready to proceed to Phase 10 live validation.

## Verification Metadata

**Verification approach:** Goal-backward from Phase 9 roadmap success criteria and plan must-haves.  
**Must-haves source:** Phase 9 `09-01-PLAN.md` and ROADMAP success criteria.  
**Automated checks:** 6 passed, 0 failed.  
**Human checks required:** 0.  
**Total verification time:** 4 min.

---
*Verified: 2026-06-04T00:25:46Z*
*Verifier: Codex inline verifier*
