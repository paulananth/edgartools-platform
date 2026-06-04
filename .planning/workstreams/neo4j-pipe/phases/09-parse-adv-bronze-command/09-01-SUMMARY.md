---
phase: 09-parse-adv-bronze-command
plan: "09-01"
subsystem: warehouse-cli
tags: [adv, bronze, silver, cli, tests]

requires:
  - phase: 08-adv-bronze-discovery-contract
    provides: ADV bronze registry and explicit artifact discovery/read helpers
provides:
  - Bounded `edgar-warehouse parse-adv-bronze` CLI command
  - ADV bronze-to-silver orchestrator path using existing ADV parser and silver merges
  - Focused parser command tests covering registry, explicit artifacts, idempotency, errors, and no SEC fetch
affects: [phase-10-live-adv-backfill-validation, mdm-adviser-source-readiness]

tech-stack:
  added: []
  patterns:
    - CLI command shim delegates to warehouse orchestrator command name
    - ADV operator command uses Phase 8 discovery/read helper with injected storage reader
    - Command-level idempotency skips accessions present in `sec_adv_filing` before storage reads

key-files:
  created:
    - edgar_warehouse/application/commands/parse_adv_bronze.py
    - tests/application/test_parse_adv_bronze.py
  modified:
    - edgar_warehouse/cli.py
    - edgar_warehouse/application/commands/__init__.py
    - edgar_warehouse/application/warehouse_orchestrator.py
    - edgar_warehouse/infrastructure/dataset_path_catalog.py

key-decisions:
  - "Implement ADV backfill as a narrow operator command, not as a new pipeline architecture."
  - "Keep explicit artifact inputs bounded to existing storage paths and route reads through `read_bytes`."
  - "Apply `--limit` after already-parsed skip filtering so limits count processable ADV candidates."
  - "Keep `parse-adv-bronze` out of gold, Snowflake export, and serving export command sets."

patterns-established:
  - "Operator parse commands can use command-specific discovery helpers before invoking parser-family silver merges."
  - "No-SEC-fetch behavior is enforced with hard-failing test patches around SEC fetch helpers."

requirements-completed:
  - ADV-04
  - ADV-05
  - ADV-06
  - ADV-07

duration: 16 min
completed: 2026-06-04
---

# Phase 9 Plan 09-01: Parse ADV Bronze Command Summary

**Bounded ADV bronze-to-silver command with explicit existing-artifact fallback and idempotent silver merges**

## Performance

- **Duration:** 16 min
- **Started:** 2026-06-04T00:09:45Z
- **Completed:** 2026-06-04T00:25:46Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added `edgar-warehouse parse-adv-bronze` with `--limit`, `--accession-list`, and repeatable `--artifact ACCESSION,FORM,STORAGE_PATH[,CIK]`.
- Added an ADV-only orchestrator branch that discovers existing bronze artifacts, skips already parsed accessions, reads through the storage adapter, parses with `parse_adv`, and merges all four ADV silver tables.
- Added focused tests proving registry reads, explicit existing artifact reads, idempotency skip, post-skip limit behavior, missing/unreadable artifacts, parser errors, and no SEC fetch helper calls.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire the CLI and command registry** - `b946512` (`feat(09-01): wire ADV bronze parse command`)
2. **Task 2: Implement the ADV bronze parse orchestrator branch** - `6a47f53` (`feat(09-01): parse ADV bronze artifacts into silver`)
3. **Task 3: Add focused parse-adv-bronze tests** - `a086fa1` (`test(09-01): cover ADV bronze parse command`)

## Files Created/Modified

- `edgar_warehouse/application/commands/parse_adv_bronze.py` - Command registry shim for `parse-adv-bronze`.
- `tests/application/test_parse_adv_bronze.py` - Focused command tests for CLI parsing, registry and explicit artifact reads, idempotency, error handling, and no SEC fetch.
- `edgar_warehouse/cli.py` - Added ADV artifact parser, handler, and `parse-adv-bronze` subparser.
- `edgar_warehouse/application/commands/__init__.py` - Registered the new command module.
- `edgar_warehouse/application/warehouse_orchestrator.py` - Added ADV parse dispatch, runner, metrics, events, and scope metadata.
- `edgar_warehouse/infrastructure/dataset_path_catalog.py` - Added `parse-adv-bronze` to operator-command manifest planning.

## Decisions Made

- `sec_adv_filing` is the skip table because it has one row per ADV accession and parents the ADV detail tables.
- Explicit artifacts are accepted only as operator-provided existing storage paths; the command does not fetch alternate SEC URLs.
- `explicit_artifact_count` is included in scope, but raw artifact paths are not copied into scope metadata.
- `parse-adv-bronze` remains outside `GOLD_AFFECTING_COMMANDS`, `SNOWFLAKE_EXPORT_COMMANDS`, and `SERVING_EXPORT_COMMANDS`.

## Deviations from Plan

None - plan executed exactly as written.

---

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope change.

## Issues Encountered

- `gsd-sdk init.execute-phase 9` does not resolve workstream-local phases in this repository layout, so execution used the workstream plan files directly.
- The worktree had a pre-existing unrelated unstaged edit in `edgar_warehouse/mdm/migrations/runtime.py`; it was left untouched and unstaged.

## Verification

- `uv run python -m py_compile edgar_warehouse/cli.py edgar_warehouse/application/commands/parse_adv_bronze.py edgar_warehouse/application/warehouse_orchestrator.py` - passed.
- `uv run edgar-warehouse parse-adv-bronze --help` - passed and showed `--limit`, `--accession-list`, `--artifact`, and `--run-id`.
- `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py -q` - passed, 8 tests.
- `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py tests/application/test_adv_bronze_discovery.py tests/application/test_parse_ownership_bronze.py -q` - passed, 26 tests.
- `bash -lc '! rg -n "parse-adv-bronze" edgar_warehouse/infrastructure/warehouse_settings.py'` - passed.
- `rg -n "parse-adv-bronze|_run_parse_adv_bronze|merge_adv_filings|merge_adv_private_funds" edgar_warehouse/cli.py edgar_warehouse/application/commands edgar_warehouse/application/warehouse_orchestrator.py edgar_warehouse/infrastructure/dataset_path_catalog.py` - passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 10 can validate the command against dev S3/local silver evidence. The current phase intentionally does not fetch ADV artifacts from SEC or test alternate SEC URL loading; that remains in backlog Phase 999.1.

## Self-Check: PASSED

- All plan tasks executed.
- Task commits exist for CLI/registry wiring, orchestrator implementation, and focused tests.
- Summary created and ready for metadata commit.
- Phase success criteria ADV-04 through ADV-07 are covered by source and tests.

---
*Phase: 09-parse-adv-bronze-command*
*Completed: 2026-06-04*
