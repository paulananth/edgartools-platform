---
phase: 09-parse-adv-bronze-command
type: patterns
date: 2026-06-03
workstream: neo4j-pipe
---

# Phase 9 Pattern Map

Use the existing ownership bronze parse command shape, but do not copy its current `--limit`
ordering bug. For ADV, `--limit` must count candidates that are not already present in
`sec_adv_filing`.

## Command Wiring

- `edgar_warehouse/cli.py`
  - Add `_handle_parse_adv_bronze(args)` beside `_handle_parse_ownership_bronze`.
  - Add a `parse-adv-bronze` subparser beside `parse-ownership-bronze`.
  - Reuse `--limit`, `--accession-list`, and `_add_run_id_arg`.
  - Add repeatable `--artifact ACCESSION,FORM,STORAGE_PATH[,CIK]` with `action="append"`,
    `dest="artifacts"`, and `argparse.ArgumentTypeError` for malformed values.
- `edgar_warehouse/application/commands/parse_adv_bronze.py`
  - Mirror `parse_ownership_bronze.py`: delegate to `run_command("parse-adv-bronze", args)`.
- `edgar_warehouse/application/commands/__init__.py`
  - Import `parse_adv_bronze`.
  - Register `"parse-adv-bronze": parse_adv_bronze.execute`.

## Orchestrator

- `edgar_warehouse/application/warehouse_orchestrator.py`
  - Keep `parse-adv-bronze` out of `GOLD_AFFECTING_COMMANDS` and
    `SNOWFLAKE_EXPORT_COMMANDS`.
  - Add a dispatch branch near `parse-ownership-bronze`.
  - Add `_run_parse_adv_bronze(...)` near `_run_parse_ownership_bronze(...)`.
  - Add `_resolve_scope(...)` support with `limit`, `accession_list`, and
    `explicit_artifact_count`; do not emit full operator paths into scope unless necessary.

The command body should:

1. Fetch already parsed accessions from `sec_adv_filing`.
2. Call `discover_adv_bronze_artifacts(db, accession_list=..., explicit_artifacts=..., limit=None)`.
3. Filter out already parsed accessions before reading.
4. Apply `limit` after that skip filter.
5. Call `read_adv_bronze_artifacts(selected, read_bytes_fn=read_bytes)`.
6. Call `parse_adv(accession, payload, form, cik)`.
7. Merge rows with:
   - `db.merge_adv_filings(parsed.get("sec_adv_filing", []), sync_run_id)`
   - `db.merge_adv_offices(parsed.get("sec_adv_office", []), sync_run_id)`
   - `db.merge_adv_disclosure_events(parsed.get("sec_adv_disclosure_event", []), sync_run_id)`
   - `db.merge_adv_private_funds(parsed.get("sec_adv_private_fund", []), sync_run_id)`
8. Continue on unreadable artifact issues and parser exceptions.
9. Emit structured start, skip, unreadable/missing, parser error, and completion events.
10. Return `([], metrics)` like `parse-ownership-bronze`.

## Storage And Path Catalog

- Use Phase 8 `edgar_warehouse/application/adv_bronze_discovery.py`.
- Do not add S3 prefix listing, SEC fetches, or custom file readers.
- Pass the existing orchestrator-level `read_bytes` into `read_adv_bronze_artifacts` so tests can
  patch the read boundary deterministically.
- In `edgar_warehouse/infrastructure/dataset_path_catalog.py`, add `parse-adv-bronze` to the same
  operator-command manifest branch as `parse-ownership-bronze`.

## Settings Boundary

- Do not add `parse-adv-bronze` to `edgar_warehouse/infrastructure/warehouse_settings.py`
  `SERVING_EXPORT_COMMANDS`.
- Do not require `SERVING_EXPORT_ROOT`, `SNOWFLAKE_EXPORT_ROOT`, or `MDM_DATABASE_URL`.
- Do not trigger gold, dbt, Snowflake, MDM, ECS, Step Functions, or deploy artifacts.

## Test Patterns

- Use fake DBs patterned after `tests/application/test_adv_bronze_discovery.py` and
  `tests/application/test_parse_ownership_bronze.py`.
- Patch SEC fetch helpers to hard-fail:
  - `edgar_warehouse.application.warehouse_orchestrator.download_sec_bytes`
  - `edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts`
- Patch or inject storage reads through `read_adv_bronze_artifacts(..., read_bytes_fn=...)` by
  keeping the orchestrator call explicit.
- Cover:
  - CLI parser registration and `--artifact` parsing.
  - Registry candidates parsed and merged to all four ADV silver methods.
  - Explicit artifact candidates parsed and merged.
  - Already parsed accessions skipped before storage read.
  - `--limit` applied after skip filtering.
  - Missing/unreadable artifacts counted and non-fatal.
  - Parser exceptions counted and non-fatal.
  - No SEC fetch helpers called.

