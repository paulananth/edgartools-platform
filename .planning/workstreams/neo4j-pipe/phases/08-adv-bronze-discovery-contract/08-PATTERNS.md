# Phase 8 Pattern Map: ADV Bronze Discovery Contract

**Date:** 2026-06-03
**Status:** Complete

## Files To Create

| File | Role | Closest Existing Pattern |
|------|------|--------------------------|
| `edgar_warehouse/application/adv_bronze_discovery.py` | Pure discovery/read helper for ADV bronze artifacts | `_run_parse_ownership_bronze()` and `_read_primary_artifact_bytes()` in `warehouse_orchestrator.py` |
| `tests/application/test_adv_bronze_discovery.py` | Focused unit tests for discovery/read contract | `tests/application/test_parse_ownership_bronze.py` |

## Existing Patterns To Reuse

### Fixed form allowlist

Use the current ADV family from `warehouse_orchestrator.py` and parser dispatch:

```python
ADV_FORMS = {"ADV", "ADV/A", "ADV-E", "ADV-E/A", "ADV-H", "ADV-H/A", "ADV-NR", "ADV-W", "ADV-W/A"}
```

Do not accept arbitrary operator-provided SQL identifiers or form-family table names.

### Registry artifact read

The ownership path reads the primary artifact through:

1. `db.get_filing_attachments(accession_number)`
2. choose `is_primary`
3. `db.get_raw_object(raw_object_id)`
4. `read_bytes(raw_object["storage_path"])`

Phase 8 should keep the same registry semantics but return a structured issue instead of raising
for missing primary/raw-object cases.

### No SEC fetch

The ownership tests patch `warehouse_orchestrator.download_sec_bytes` to raise. Phase 8 tests
should do the same for both:

- `warehouse_orchestrator.download_sec_bytes`
- `edgar_warehouse.infrastructure.filing_artifact_service.refresh_filing_artifacts`

The new helper should not import either symbol.

### Result shape

Prefer simple dataclasses. The exact names are implementation discretion, but the result should
carry these concepts:

- candidate artifact rows: accession, CIK, form, storage path, source kind
- read payload rows: candidate plus bytes
- issue rows: accession/path/source/reason
- counters: selected, missing, read, unreadable, skipped non-ADV

### Tests

Use a fake DB rather than DuckDB. The fake should implement only:

- `fetch(sql, params=None)`
- `get_filing_attachments(accession_number)`
- `get_raw_object(raw_object_id)`

Assertions should verify SQL uses `sec_company_filing` and ADV forms, not dynamic table names.

## Anti-Patterns

- Do not list S3 prefixes to discover ADV artifacts.
- Do not fetch missing filings from SEC.
- Do not parse ADV or mutate silver in Phase 8.
- Do not alter `GOLD_AFFECTING_COMMANDS`, Step Functions, dbt, Snowflake graph sync, or generated deployment JSON.
