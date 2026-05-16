# Phase 05: Source To MDM Load Path - Pattern Map

**Mapped:** 2026-05-16
**Files analyzed:** 5
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `edgar_warehouse/application/warehouse_orchestrator.py` | controller/orchestrator | batch, file I/O, transform | `edgar_warehouse/application/warehouse_orchestrator.py` | exact |
| `edgar_warehouse/mdm/cli.py` | CLI boundary | request/response, batch | `edgar_warehouse/mdm/cli.py` | exact |
| `edgar_warehouse/mdm/pipeline.py` | service/orchestrator | batch, CRUD, transform | `edgar_warehouse/mdm/pipeline.py` | exact |
| `tests/application/test_parse_ownership_bronze.py` | application test | batch, file I/O, transform | `tests/unit/test_loader_idempotency.py`, `tests/unit/test_submission_phase_order.py` | role match |
| `tests/mdm/test_source_to_mdm_load_path.py` | MDM integration test | batch, CRUD, transform | `tests/mdm/test_pipeline_relationships.py` | exact |

## Pattern Assignments

### `edgar_warehouse/application/warehouse_orchestrator.py`

Use the existing command dispatch and per-filing parser loop patterns:

- Keep `parse-ownership-bronze` routed through `_capture_bronze_raw()` command dispatch.
- Emit structured events with `_emit_pipeline_event(...)`.
- Mutate the `metrics` dict before returning.
- Preserve idempotent skip counts with `already_parsed`.
- Use `WarehouseRuntimeError` for operator-facing hard failures.
- Reuse `_read_primary_artifact_bytes(db, accession_number)` for artifact-registry reads when possible.
- Use current silver DDL names from `silver_store.py`: `sec_company_filing.form` and `sec_company_filing.report_date`.

Closest current references:

- `_run_parse_ownership_bronze(...)`
- `_run_parse_pipeline(...)`
- `_read_primary_artifact_bytes(...)`
- `_emit_pipeline_event(...)`

### `edgar_warehouse/mdm/cli.py`

Follow the existing MDM CLI boundary:

- Add shared helpers near `_silver_reader()` rather than duplicating source checks in every handler.
- Keep parser exposure through `register_mdm_subparser`.
- Keep command execution wrapped with `_logged_handler(...)`.
- Keep secret-safe argument logging through `_safe_arguments(...)`.
- Print operator failures to `stderr` and return nonzero.
- For `run`, `derive-relationships`, and `load-relationships`, validate silver source before `_session()`.
- Close sessions in `finally` when a handler opens one.

Closest current references:

- `_silver_reader()`
- `_handle_run(...)`
- `_handle_derive_relationships(...)`
- `_handle_load_relationships(...)`
- `_handle_seed_from_silver(...)`

### `edgar_warehouse/mdm/pipeline.py`

Keep source-to-MDM behavior inside the existing pipeline/resolver contract:

- Use `SilverReader.fetch(sql, params)` as the only pipeline input interface.
- Keep domain loading in resolver methods: `run_companies`, `run_advisers`, `run_persons`, `run_securities`, and `run_funds`.
- Use `ResolverContext` and existing resolver classes for entity matching/source refs.
- Commit after each loader method as current methods do.
- If company loading needs tracking metadata, use current silver `sec_company_sync_state` semantics or nullable tracking, not stale `sec_tracked_universe`.
- Do not introduce Neo4j requirements into Phase 5 tests.

Closest current references:

- `MDMPipeline.run_all(...)`
- `MDMPipeline.run_persons(...)`
- `MDMPipeline.run_securities(...)`
- `edgar_warehouse/mdm/resolvers/base.py`
- `edgar_warehouse/mdm/resolvers/person.py`

### `tests/application/test_parse_ownership_bronze.py`

Use application-level tests with fake/stub DB and storage:

- Use temporary local `StorageLocation`/`WarehouseCommandContext` patterns from bronze-file tests.
- Patch storage reads instead of hitting S3.
- Use a fake DB implementing exactly the methods the orchestrator command calls.
- Assert current-schema SQL uses `form` and does not use stale `form_type`/`period_of_report`.
- Assert already-parsed accessions are skipped.
- Assert missing primary artifact increments error/missing counts without SEC fetch.
- Assert parser output is merged into all three ownership silver tables.

Closest current references:

- `tests/unit/test_bronze_files.py`
- `tests/unit/test_submission_phase_order.py`
- `tests/unit/test_loader_idempotency.py`
- `tests/application/test_warehouse_orchestrator_mdm.py`

### `tests/mdm/test_source_to_mdm_load_path.py`

Use existing MDM fixture patterns:

- Use in-memory SQLite with `Base.metadata.create_all(...)` and registry seeding.
- Use `StubSilver.fetch(...)` keyed by SQL substrings for pipeline tests where possible.
- Use a real temporary DuckDB file for CLI source-preflight tests.
- Assert idempotency on domain tables only: `mdm_company`, `mdm_adviser`, `mdm_person`, `mdm_security`, `mdm_fund`.
- Do not assert staging/change-log tables stay unchanged across repeated runs.
- Test missing `MDM_SILVER_DUCKDB` before `_session()` by monkeypatching `_session` to raise if called.

Closest current references:

- `tests/mdm/conftest.py`
- `tests/mdm/test_pipeline_relationships.py`
- `tests/mdm/test_universe.py`
- `tests/mdm/test_runtime_ops.py`

## Shared Patterns

### Structured Events

Use `_emit_pipeline_event(...)` in warehouse orchestrator paths and `emit_mdm_event(...)` in MDM CLI paths. Both produce JSON to `stderr` with sorted keys and timestamps.

### Source Validation

Use a fixed allowlist of required silver table names for preflight. Do not interpolate operator-controlled identifiers into validation SQL.

### Artifact Reads

Prefer `sec_filing_attachment` -> `sec_raw_object` -> `read_bytes(storage_path)` because it supports both local fixtures and remote S3 URIs through existing storage adapters.

### Security

Every implementation plan should include threats for:

- Unsupported URI/protocol reads via `MDM_SILVER_DUCKDB`.
- SQL injection via dynamic table validation.
- Partial MDM mutation after invalid silver source.
- SEC re-fetch accidentally entering Phase 5.
- Secret leakage in CLI logs.

## No Analog Found

None. Every expected implementation surface has an existing role/data-flow analog in the repository.
