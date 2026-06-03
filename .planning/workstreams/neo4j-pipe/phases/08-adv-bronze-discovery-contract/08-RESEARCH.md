# Phase 8 Research: ADV Bronze Discovery Contract

**Date:** 2026-06-03
**Status:** Complete

## Goal

Research what is needed to plan Phase 8 well: a safe discovery and read contract for
already-captured ADV bronze artifacts, without adding the parser CLI yet.

## Findings

### Current ADV parser support exists

`edgar_warehouse/parsers/adv.py` provides `parse_adv(accession_number, content, form_type, cik=None)`.
It returns four silver table payload groups:

- `sec_adv_filing`
- `sec_adv_office`
- `sec_adv_disclosure_event`
- `sec_adv_private_fund`

`edgar_warehouse/parsers/__init__.py` and `warehouse_orchestrator.py` both define the ADV form
family as:

`ADV`, `ADV/A`, `ADV-E`, `ADV-E/A`, `ADV-H`, `ADV-H/A`, `ADV-NR`, `ADV-W`, `ADV-W/A`

### The existing generic parser path is not an operator backfill command

`warehouse_orchestrator._run_parse_pipeline()` can parse ADV forms when a filing accession is
already present in `sec_company_filing` and has primary artifact registry rows. It then calls
the existing ADV merge methods on `SilverDatabase`.

The gap is operator reachability: there is no dedicated `parse-adv-bronze` equivalent to
`parse-ownership-bronze`, and no fallback for "bronze object exists but registry rows are
missing."

### Ownership backfill gives the closest implementation pattern

`_run_parse_ownership_bronze()` already models the safety constraints this milestone needs:

- query a fixed form allowlist from `sec_company_filing`
- skip already parsed rows
- read primary artifacts through `sec_filing_attachment` and `sec_raw_object`
- use `read_bytes(storage_path)`
- count missing artifacts separately from parser errors
- do not call SEC download helpers

Phase 8 should extract the discovery/read portion of this pattern for ADV. It should not copy
the ownership parser's merge behavior yet.

### Explicit bronze path fallback needs structured input

Inferring accession, CIK, and form from arbitrary S3 paths is underdefined and fragile. The
fallback should accept explicit artifact records with these fields:

- `accession_number`
- `storage_path`
- `form`
- optional `cik`

That keeps the fallback bounded and testable, avoids S3 listing, and gives Phase 9 a clean CLI
design target.

### Storage safety comes from the existing storage adapter

`edgar_warehouse.infrastructure.object_storage.read_bytes()` already enforces the storage
protocol allowlist before using fsspec. The discovery helper should call this function, or an
injected test double, rather than using fsspec directly.

## Validation Architecture

Phase 8 validation should be local and deterministic:

- a fake SilverDatabase for registry-backed discovery
- explicit fallback artifact records for registry-missing cases
- injected `read_bytes_fn` for artifact reads
- tests that patch SEC fetch helpers to raise if called
- source assertions that the new helper does not import `download_sec_bytes` or
  `refresh_filing_artifacts`

## Planning Recommendation

Use one executable plan:

1. Add `edgar_warehouse/application/adv_bronze_discovery.py` with dataclasses/result objects,
   fixed ADV allowlist, registry discovery, explicit artifact fallback, and read helper.
2. Add `tests/application/test_adv_bronze_discovery.py` covering registry discovery, explicit
   fallback, missing artifact issues, unreadable path issues, filtering/limit behavior, and no
   SEC fetch.

## Research Complete
