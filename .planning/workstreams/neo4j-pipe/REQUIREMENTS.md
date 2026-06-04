# Requirements: ADV Bronze-To-Silver Backfill

workstream: neo4j-pipe
status: active
milestone: v1.4 ADV Bronze-To-Silver Backfill
updated: 2026-06-03

---

## Milestone Requirements

### Bronze Discovery

- [x] **ADV-01**: Operator can select ADV filings that already exist in bronze or the silver artifact registry without calling the SEC API.
- [x] **ADV-02**: Backfill discovery prefers `sec_filing_attachment` + `sec_raw_object` registry rows when present and has an explicit bounded fallback for existing bronze object paths when registry rows are missing.
- [x] **ADV-03**: Missing or unreadable bronze artifacts are reported with accession/path counts and do not abort the whole backfill batch.

### Silver Backfill

- [x] **ADV-04**: `edgar-warehouse parse-adv-bronze` parses selected ADV artifacts with the existing `edgar_warehouse.parsers.adv` parser and writes `sec_adv_filing`, `sec_adv_office`, `sec_adv_disclosure_event`, and `sec_adv_private_fund`.
- [x] **ADV-05**: `parse-adv-bronze` supports `--accession-list` and `--limit`, and repeated runs skip already parsed ADV accessions by default.
- [x] **ADV-06**: The backfill path is idempotent: rerunning against unchanged bronze does not duplicate ADV silver rows or corrupt existing ownership silver rows.
- [x] **ADV-07**: The implementation proves no SEC network fetch occurs during backfill by injecting/stubbing the artifact read path in tests.

### MDM Readiness

- [ ] **MDM-ADV-01**: After ADV backfill, `sec_adv_filing` and `sec_adv_private_fund` readiness diagnostics report nonzero rows for at least one selected live S3 ADV sample when source data contains private funds.
- [ ] **MDM-ADV-02**: `mdm run --entity-type adviser` and `mdm run --entity-type fund` preflights can succeed against a silver source populated by `parse-adv-bronze`.
- [ ] **MDM-ADV-03**: The docs identify the exact resume path for the blocked Phase 5 live checkpoint, including the silver counts needed before running MDM adviser/fund loaders.

### Isolation

- [x] **ISO-01**: Work stays in the `workspace/neo4j-pipe` worktree and does not edit loader-fix artifacts or generated deployment JSON.
- [x] **ISO-02**: Changes remain AWS/local focused and do not introduce non-AWS storage, registry, workflow, or secret-management paths.
- [x] **ISO-03**: Gold refresh, dbt models, Snowflake graph sync, and unrelated Step Functions behavior remain out of scope unless a test exposes a direct regression from ADV backfill.

## Future Requirements

- [ ] Generalize ownership and ADV bronze backfill into a shared parser-family command if a third SEC parser family needs the same operator path.
- [ ] Add large-batch ECS automation for ADV-only backfills after the local/S3 operator command is proven.

## Out Of Scope

- Fetching missing ADV artifacts from SEC.
- Rewriting the ADV parser semantics beyond fixes required to parse already captured artifacts.
- Gold table enrichment or dbt model changes.
- Snowflake graph analytics migration work.
- Non-AWS deployment paths, registries, storage targets, or secret-management paths.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ADV-01 | Phase 8 | Complete |
| ADV-02 | Phase 8 | Complete |
| ADV-03 | Phase 8 | Complete |
| ADV-04 | Phase 9 | Complete |
| ADV-05 | Phase 9 | Complete |
| ADV-06 | Phase 9 | Complete |
| ADV-07 | Phase 9 | Complete |
| MDM-ADV-01 | Phase 10 | Pending |
| MDM-ADV-02 | Phase 10 | Pending |
| MDM-ADV-03 | Phase 10 | Pending |
| ISO-01 | Phase 8 | Complete |
| ISO-02 | Phase 8 | Complete |
| ISO-03 | Phase 8 | Complete |
