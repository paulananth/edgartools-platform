---
phase: 05-source-to-mdm-load-path
plan: "02"
subsystem: warehouse-orchestrator
tags: [fix, duckdb, silver, ownership, artifact-registry, sec-edgar, parse-ownership-bronze]

requires:
  - phase: 05-source-to-mdm-load-path
    plan: "01"
    provides: RED test contract for parse-ownership-bronze (D-01..D-10)

provides:
  - Repaired parse-ownership-bronze command using current silver schema (form, report_date)
  - Artifact-registry read path via sec_filing_attachment + sec_raw_object + read_bytes
  - Distinct missing_artifacts metric and parse_ownership_bronze_missing_artifact event
  - --limit and --accession-list CLI arguments for bounded operator repair
  - Green regression coverage: 13/13 tests pass in test_parse_ownership_bronze.py

affects:
  - 05-03 (MDM silver preflight — ownership tables now writable via repair command)

tech-stack:
  added: []
  patterns:
    - "Artifact-registry-first read: sec_filing_attachment -> sec_raw_object -> read_bytes(storage_path)"
    - "Distinct missing-artifact metric separate from parse-error metric"
    - "Optional limit/accession_list threaded through _capture_bronze_raw dispatch"

key-files:
  created: []
  modified:
    - edgar_warehouse/application/warehouse_orchestrator.py
    - edgar_warehouse/cli.py

key-decisions:
  - "Removed function-local fsspec import from _run_parse_ownership_bronze; module-level read_bytes already imported at line 70 so test patches on warehouse_orchestrator.read_bytes work correctly"
  - "WarehouseRuntimeError from _read_primary_artifact_bytes caught as missing-artifact, not generic error — gives distinct missing_artifacts count in metrics"
  - "--limit applied after accession_list filter so limit counts processable accessions only"
  - "_capture_bronze_raw dispatch threads limit/accession_list through arguments dict; scope resolver updated to expose them"

metrics:
  duration: 20min
  completed: "2026-05-17"
  tasks: 2
  files_modified: 2
---

# Phase 5 Plan 02: Repair parse-ownership-bronze — GREEN Tests Summary

**Repaired _run_parse_ownership_bronze to use current silver schema columns and artifact-registry reads; 13 RED tests now GREEN with no SEC API calls and named missing-artifact metrics**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-05-17T09:55:00Z
- **Completed:** 2026-05-17T10:13:53Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Fixed `_run_parse_ownership_bronze` in `warehouse_orchestrator.py`:
  - Changed SQL from `sec_company_filing.form_type` + `ORDER BY period_of_report` to `sec_company_filing.form` + `ORDER BY report_date` (D-07)
  - Replaced `fsspec.filesystem("s3").ls(prefix)` with `_read_primary_artifact_bytes(db, accession)` which routes through `sec_filing_attachment` + `sec_raw_object` + `read_bytes(storage_path)` (D-08)
  - Added `missing_artifact_count` metric and `parse_ownership_bronze_missing_artifact` structured event for absent primary registry rows (D-09)
  - Removed function-local `import fsspec` and function-local `from ... import read_bytes` — module-level `read_bytes` at line 70 is used, allowing `patch.object(warehouse_orchestrator, "read_bytes", ...)` to work in tests (D-10)
  - Added optional `limit` and `accession_list` parameters (T-05-11)
  - Updated `_capture_bronze_raw` dispatch and `_resolve_scope` to thread CLI args through
- Updated `edgar_warehouse/cli.py` to add `--limit` and `--accession-list` to the existing `parse-ownership-bronze` command (D-06, T-05-11)
- All 13 tests in `tests/application/test_parse_ownership_bronze.py` now pass (GREEN gate)

## Task Commits

1. **Tasks 1+2: Repair parse-ownership-bronze and harden diagnostics** — `688af5d` (fix)

## Files Created/Modified

- `/Users/aneenaananth/projects/edgartools-platform/edgar_warehouse/application/warehouse_orchestrator.py` — Fixed `_run_parse_ownership_bronze`: current schema columns, artifact-registry read, missing-artifact metric, removed fsspec S3 listing; added limit/accession_list params; updated dispatch and scope resolver
- `/Users/aneenaananth/projects/edgartools-platform/edgar_warehouse/cli.py` — Added `--limit` and `--accession-list` to `parse-ownership-bronze` command registration

## Decisions Made

- Removed function-local `import fsspec` entirely from `_run_parse_ownership_bronze`; `_read_primary_artifact_bytes` (already at line 2079) encapsulates the registry read and uses the module-level `read_bytes`.
- `WarehouseRuntimeError` from missing primary attachment is caught and routed to `missing_artifacts` counter (not `errors`) to satisfy D-09's "distinct observable metric" requirement. Tests accept either `errors > 0` OR `missing_artifacts > 0`; the implementation uses the distinct counter.
- `--limit` is applied after the `--accession-list` filter to ensure bounded runs count processable filings, not raw DB rows.
- Function signature uses `limit: int | None = None` and `accession_list: list[str] | None = None` so tests calling `_run_parse_ownership_bronze(context=..., db=..., sync_run_id=..., metrics={})` continue to work without modification.

## Deviations from Plan

None — plan executed as written. Both tasks (schema fix + diagnostics hardening) were addressed in a single commit since the static isolation checks (Task 2) confirmed no out-of-scope file drift and required no additional implementation changes.

## Known Stubs

None. All repairs are complete and functional. The command can be run against any silver DuckDB with sec_filing_attachment/sec_raw_object rows populated by the bronze capture pipeline.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries were introduced. Mitigations T-05-07 through T-05-12 are satisfied:

| Threat | Status |
|--------|--------|
| T-05-07 Fixed Forms 3/4/5 constants + parameterized filtering | MITIGATED — SQL uses fixed IN-list, no operator-controlled interpolation |
| T-05-08 read_bytes protocol allowlist | MITIGATED — reads go through _read_primary_artifact_bytes -> read_bytes |
| T-05-09 Named missing-artifact events with accession + run_id | MITIGATED — parse_ownership_bronze_missing_artifact event emitted |
| T-05-10 Sole parser path via parse_ownership/Ownership.from_xml | MITIGATED — no new parser path added |
| T-05-11 --limit and --accession-list for bounded repair | MITIGATED — both args added to CLI |
| T-05-12 No SEC re-fetch in default path | MITIGATED — fsspec S3 listing removed, no SEC client calls remain |

## Self-Check

- [x] `edgar_warehouse/application/warehouse_orchestrator.py` exists — FOUND
- [x] `edgar_warehouse/cli.py` exists — FOUND
- [x] Commit `688af5d` exists in git log — FOUND
- [x] All 13 tests pass: `uv run --extra s3 --with pytest python -m pytest tests/application/test_parse_ownership_bronze.py -q` → 13 passed
- [x] Static check: no `form_type`, `period_of_report`, `fsspec.filesystem("s3")`, `download_sec_bytes`, `download_sec_submission` inside `_run_parse_ownership_bronze`
- [x] CLI check: `edgar-warehouse parse-ownership-bronze --help` shows `--limit` and `--accession-list`
- [x] No out-of-scope file changes: only `warehouse_orchestrator.py` and `cli.py` staged; `infra/aws-dev-application.json` (Codex workstream) and `.planning/workstreams/fix-pipelines/` untouched

## Self-Check: PASSED

---
*Phase: 05-source-to-mdm-load-path*
*Completed: 2026-05-17*
