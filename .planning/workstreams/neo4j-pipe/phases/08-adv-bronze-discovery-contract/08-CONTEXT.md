# Phase 8: ADV Bronze Discovery Contract - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning
**Source:** Inline plan-phase context from approved v1.4 milestone scope

<domain>
## Phase Boundary

Phase 8 defines the reusable discovery and read contract for ADV bronze artifacts. It does
not add the `parse-adv-bronze` CLI command and does not parse ADV rows into silver. Phase 9
will wire the command and parser execution.

The output of this phase should be a small production helper plus focused tests that prove
existing ADV artifacts can be selected and read from either:

- the artifact registry: `sec_company_filing` -> `sec_filing_attachment` -> `sec_raw_object`
- explicit operator-provided artifact records containing accession, form, optional CIK, and
  a storage path

No SEC API calls are allowed in this phase.
</domain>

<decisions>
## Implementation Decisions

### D-01: Keep discovery separate from parsing
- Phase 8 should create discovery/read primitives only. The parser command and silver merges are Phase 9.

### D-02: Prefer registry-backed discovery
- When silver registry rows exist, use `sec_company_filing` filtered to ADV forms, then
  `get_filing_attachments(accession_number)`, then `get_raw_object(raw_object_id)`.

### D-03: Support explicit artifact fallback without S3 listing
- When registry rows are missing but the operator already has bronze object paths, support an
  explicit bounded artifact input. Do not list S3 prefixes to discover files.

### D-04: Treat missing artifacts as data issues, not batch failures
- Missing primary attachments, missing raw objects, empty storage paths, and unreadable paths
  must be reported as structured issues while the rest of the batch continues.

### D-05: No SEC fetch path
- The helper must not import or call `download_sec_bytes`, `_download_sec_bytes`, or
  `refresh_filing_artifacts`. Reads must go through `edgar_warehouse.infrastructure.object_storage.read_bytes`
  or an injected test double.

### D-06: Fixed form allowlist only
- ADV form filtering must use a fixed allowlist matching current parser dispatch:
  `ADV`, `ADV/A`, `ADV-E`, `ADV-E/A`, `ADV-H`, `ADV-H/A`, `ADV-NR`, `ADV-W`, `ADV-W/A`.

### D-07: Workstream isolation
- Work remains in `workspace/neo4j-pipe`; do not edit generated deployment JSON, loader-fix
  artifacts, gold/dbt, Snowflake graph sync, or unrelated Step Functions behavior.

### the agent's Discretion
- The helper data structure names and exact return-shape can be chosen by the implementer,
  provided tests assert the public contract and Phase 9 can consume it cleanly.
</decisions>

<canonical_refs>
## Canonical References

Downstream agents MUST read these before planning or implementing.

### Existing parser and command path
- `edgar_warehouse/parsers/adv.py` - local ADV parser to be reused later by Phase 9.
- `edgar_warehouse/parsers/__init__.py` - current `ADV_FORMS` parser dispatch allowlist.
- `edgar_warehouse/application/warehouse_orchestrator.py` - current artifact registry read
  pattern (`_read_primary_artifact_bytes`) and ownership backfill pattern.
- `edgar_warehouse/application/workflows/silver_parse_pipeline.py` - existing parse-pipeline
  wrapper around `_run_parse_pipeline`.
- `edgar_warehouse/silver_store.py` - `merge_adv_filings`, `merge_adv_offices`,
  `merge_adv_disclosure_events`, and `merge_adv_private_funds`.

### Existing tests and storage safety
- `tests/application/test_parse_ownership_bronze.py` - closest test pattern for no SEC
  fetch, registry reads, missing artifact metrics, and bounded parsing.
- `edgar_warehouse/infrastructure/object_storage.py` - storage protocol allowlist and
  `read_bytes(storage_path)`.

### Project and milestone constraints
- `AGENTS.md` - AWS-only scope, `uv` usage, workstream isolation, no unrelated paths.
- `.planning/workstreams/neo4j-pipe/ROADMAP.md` - Phase 8 goal and success criteria.
- `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md` - ADV-01 through ADV-03 and isolation
  requirements.
</canonical_refs>

<specifics>
## Specific Ideas

- Create `edgar_warehouse/application/adv_bronze_discovery.py`.
- Add tests in `tests/application/test_adv_bronze_discovery.py`.
- Expose a pure function such as `discover_adv_bronze_artifacts(db, accession_list=None, explicit_artifacts=None, limit=None)`.
- Expose a read function such as `read_adv_bronze_artifacts(candidates, read_bytes_fn=read_bytes)`.
- Return structured `candidates`, `issues`, and counters rather than printing directly.
- Do not mutate silver in Phase 8.
</specifics>

<deferred>
## Deferred Ideas

- CLI registration for `parse-adv-bronze` is Phase 9.
- ADV parser execution and `SilverDatabase.merge_adv_*` usage are Phase 9.
- Live S3 validation and docs with resume counts are Phase 10.
- Large-batch ECS automation is future scope.
</deferred>

---

*Phase: 08-adv-bronze-discovery-contract*
*Context gathered: 2026-06-03 via inline plan-phase*
