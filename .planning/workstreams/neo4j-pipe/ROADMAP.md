# Roadmap: ADV Bronze-To-Silver Backfill

workstream: neo4j-pipe
status: active
milestone: v1.4 ADV Bronze-To-Silver Backfill
updated: 2026-06-02

---

## Milestone Goal

Add a safe operator path that parses already-downloaded ADV bronze artifacts into silver ADV
tables without SEC re-fetch, unblocking the MDM adviser/fund load path.

---

## Context

The previous `neo4j-pipe` live checkpoint proved the dev silver source had populated ownership
rows but zero ADV rows:

- `sec_adv_filing = 0`
- `sec_adv_private_fund = 0`
- ownership Forms 3/4/5 and ownership parsed rows were present

Code already contains an ADV parser and merge methods, but there is no dedicated operator
command equivalent to `parse-ownership-bronze` for ADV bronze artifacts. This milestone fills
that gap without broadening the architecture or fetching missing artifacts from SEC.

---

## Phases

- [ ] **Phase 8: ADV Bronze Discovery Contract** - define and test how existing ADV bronze artifacts are discovered, selected, and read without SEC fetches.
- [ ] **Phase 9: Parse ADV Bronze Command** - implement the bounded idempotent `parse-adv-bronze` operator command and silver merge behavior.
- [ ] **Phase 10: Live ADV Backfill Validation** - validate against dev S3 bronze/silver, update docs, and hand off exact resume evidence for the blocked Phase 5 checkpoint.

---

## Phase Details

### Phase 8: ADV Bronze Discovery Contract

**Goal**: Operators and tests have a precise, bounded contract for selecting already-captured ADV artifacts from registry rows or explicit bronze object paths without any SEC API calls.

**Depends on**: v1.1 Phase 5 live checkpoint findings

**Requirements**: ADV-01, ADV-02, ADV-03, ISO-01, ISO-02, ISO-03

**Success Criteria** (what must be TRUE):
  1. Discovery logic distinguishes registry-backed ADV accessions from explicit existing bronze object path inputs.
  2. Tests prove discovery does not call SEC download functions.
  3. Missing artifact cases are counted and reported without aborting remaining accessions.
  4. Work stays isolated to `neo4j-pipe` source, tests, docs, and planning files.

**Plans**: 1 plan
Plans:
- [ ] 08-01-PLAN.md - Add ADV bronze discovery/read helper and focused contract tests.

### Phase 9: Parse ADV Bronze Command

**Goal**: `edgar-warehouse parse-adv-bronze` can parse selected existing ADV bronze artifacts into current silver ADV tables idempotently.

**Depends on**: Phase 8

**Requirements**: ADV-04, ADV-05, ADV-06, ADV-07

**Success Criteria** (what must be TRUE):
  1. CLI exposes `parse-adv-bronze --accession-list ...` and `parse-adv-bronze --limit N`.
  2. The command uses `edgar_warehouse.parsers.adv` and existing `SilverDatabase.merge_adv_*` methods.
  3. Re-running the command against the same artifacts skips or upserts without duplicate `sec_adv_*` rows.
  4. Focused tests cover registry reads, explicit bronze path reads, missing artifacts, parser errors, and idempotency.

**Plans**: TBD

### Phase 10: Live ADV Backfill Validation

**Goal**: A live dev S3 run proves ADV bronze can populate silver ADV rows and makes MDM adviser/fund loaders ready to resume the blocked source-to-MDM checkpoint.

**Depends on**: Phase 9

**Requirements**: MDM-ADV-01, MDM-ADV-02, MDM-ADV-03

**Success Criteria** (what must be TRUE):
  1. Live validation records selected ADV accession/path evidence from dev S3 bronze.
  2. After backfill, `sec_adv_filing` and, where source data contains private funds, `sec_adv_private_fund` counts are nonzero.
  3. `mdm run --entity-type adviser` and `mdm run --entity-type fund` preflight against the populated silver source no longer fail on empty ADV tables.
  4. `docs/aws-mdm-source-to-mdm.md` documents the ADV backfill step and the Phase 5 resume counts.

**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 8. ADV Bronze Discovery Contract | v1.4 ADV Bronze-To-Silver Backfill | 0/1 | Ready to execute | - |
| 9. Parse ADV Bronze Command | v1.4 ADV Bronze-To-Silver Backfill | 0/TBD | Not started | - |
| 10. Live ADV Backfill Validation | v1.4 ADV Bronze-To-Silver Backfill | 0/TBD | Not started | - |
