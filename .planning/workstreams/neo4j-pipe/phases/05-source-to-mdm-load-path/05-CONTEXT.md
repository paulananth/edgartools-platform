# Phase 5: Source To MDM Load Path - Context

**Gathered:** 2026-05-16 (assumptions mode)
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 5 proves that MDM can consume existing silver data produced from already-captured bronze without re-fetching SEC artifacts and without touching the parallel loader-fix workstream. The immediate blocker is that available silver DuckDB candidates contain company and filing metadata, but the ownership parser output tables required for people and company-person relationships are empty.
</domain>

<decisions>
## Implementation Decisions

### Bronze-To-Silver Ownership Backfill
- **D-01:** Use the existing edgartools-backed ownership parser path to populate missing Forms 3/4/5 silver tables from bronze primary XML artifacts.
- **D-02:** The repair target is silver ownership data first: `sec_ownership_reporting_owner`, `sec_ownership_non_derivative_txn`, and `sec_ownership_derivative_txn`.
- **D-03:** Do not derive MDM relationships directly from bronze XML. MDM and Neo4j must remain downstream of silver ownership rows.

### Independent Workstream Isolation
- **D-04:** Keep all Phase 5 implementation in the `workspace/neo4j-pipe` worktree and the `neo4j-pipe` planning workstream.
- **D-05:** Do not edit loader-fix artifacts, generated deployment JSON, gold/dbt assets, Step Functions observability work, or unrelated loader code unless required to prove the bronze-to-MDM input contract.

### Existing Command Repair
- **D-06:** Repair and use the existing `parse-ownership-bronze` command rather than adding a second ownership backfill command.
- **D-07:** Fix the current silver schema mismatch in `parse-ownership-bronze`: `sec_company_filing` uses `form` and `report_date`, not `form_type` and `period_of_report`.
- **D-08:** Prefer artifact-registry based reads (`sec_filing_attachment` plus `sec_raw_object`) where possible, because that matches the existing `_run_parse_pipeline` path and works for local fixtures. Path-based bronze lookup remains valid only when registry rows are unavailable and the document path can be derived.

### Bronze Artifact Prerequisite
- **D-09:** Treat already-captured bronze primary XML as the prerequisite for this independent repair. If the XML artifacts are absent, Phase 5 should report the gap clearly and not silently re-fetch SEC data.
- **D-10:** Any SEC fetch or artifact capture repair is outside this Phase 5 default path unless explicitly requested, because the phase goal says existing bronze/silver data and no loader-workstream overlap.

### MDM Source Validation
- **D-11:** Add or tighten MDM preflight validation so `mdm run`, `mdm derive-relationships`, and `mdm load-relationships` fail clearly when required silver source configuration or required ownership tables are missing/empty.
- **D-12:** For company-person Neo4j validation, nonzero `sec_company`, `sec_company_filing`, and `sec_ownership_reporting_owner` rows are required before MDM person and `IS_INSIDER` relationship derivation can be considered testable.

### The Agent's Discretion
- Add bounded execution controls only if needed for safe verification, such as `--limit`, `--cik-list`, `--accession-list`, or dry-run/report-only behavior for `parse-ownership-bronze`.
- Keep tests focused on schema compatibility, idempotent re-runs, missing source behavior, and a minimal silver fixture with at least one company, reporting owner, and issuer relationship.

### Folded Todos
None.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/workstreams/neo4j-pipe/ROADMAP.md`
- `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md`
- `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md`
- `edgar_warehouse/cli.py`
- `edgar_warehouse/application/warehouse_orchestrator.py`
- `edgar_warehouse/parsers/ownership.py`
- `edgar_warehouse/silver_store.py`
- `edgar_warehouse/bronze_filing_artifacts.py`
- `edgar_warehouse/infrastructure/dataset_path_catalog.py`
- `edgar_warehouse/config/warehouse_paths.properties`
- `edgar_warehouse/mdm/cli.py`
- `edgar_warehouse/mdm/pipeline.py`
- `tests/mdm/test_pipeline_relationships.py`
- `scripts/ops/check-neo4j-e2e.py`
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `edgar_warehouse/parsers/ownership.py` already wraps `edgar.ownership.Ownership.from_xml(content)` and returns silver table-shaped rows for reporting owners and ownership transactions.
- `edgar_warehouse/cli.py` already exposes `parse-ownership-bronze` with the intended behavior: parse existing bronze Form 3/4/5 XMLs, use edgartools, make no SEC API calls, and skip accessions already present in `sec_ownership_reporting_owner`.
- `edgar_warehouse/application/warehouse_orchestrator.py` dispatches `parse-ownership-bronze` and also contains `_run_parse_pipeline`, which reads primary artifacts via `sec_filing_attachment` and `sec_raw_object`.
- `edgar_warehouse/silver_store.py` already has merge methods and schemas for ownership reporting owners, non-derivative transactions, and derivative transactions.
- `edgar_warehouse/mdm/pipeline.py` already consumes `sec_ownership_reporting_owner` and joins it to `sec_company_filing` to resolve persons and derive `IS_INSIDER`.

### Established Patterns
- Warehouse commands hydrate remote silver into a local DuckDB, mutate it locally, and publish it back to `WAREHOUSE_STORAGE_ROOT` when the storage root is remote.
- Bronze filing artifacts are registered through `sec_raw_object` and `sec_filing_attachment`; this registry is the most reliable way to read the exact primary artifact when present.
- MDM commands use `MDM_SILVER_DUCKDB` for local or URI-backed silver reads and already return nonzero when the variable is unset.
- SEC filing artifacts are additive and immutable after capture; repair paths should be explicit and idempotent.

### Integration Points
- `parse-ownership-bronze` should select Forms 3/4/5 from `sec_company_filing.form`, parse bronze XML, merge ownership rows, and publish the updated silver DuckDB.
- MDM entity loading depends on `sec_ownership_reporting_owner` for people, and relationship derivation depends on `sec_ownership_reporting_owner` joined to `sec_company_filing`.
- The available local silver candidates currently have zero `sec_raw_object`, zero `sec_filing_attachment`, zero `sec_ownership_reporting_owner`, and zero `sec_ownership_non_derivative_txn` rows, so they are not enough by themselves to prove company-person graph coverage.
</code_context>

<specifics>
## Specific Ideas

- User explicitly confirmed the ownership relationship gap should be addressed independently from bronze to silver for missing data.
- Use edgartools Python for missing ownership relationships through the repo's existing parser adapter, not a new custom XML parser.
- Keep Phase 5 focused on making the source tables valid for MDM; relationship coverage belongs to Phase 6 and Neo4j sync verification belongs to Phase 7.
</specifics>

<deferred>
## Deferred Ideas

- SEC artifact re-fetch or missing-bronze capture repair is deferred unless the user explicitly expands Phase 5 beyond existing bronze/silver data.
- Full AWS 100-company runtime proof remains a future requirement after credentials and Neo4j environment are available.

### Reviewed Todos
None.
</deferred>
