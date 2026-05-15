# Roadmap: EdgarTools Platform

status: active
updated: 2026-05-15

---

## Milestones

- 🚧 **MDM & graph completeness** — Phases 1-4 (active)
- 📋 **Gold layer enrichment** — Phases 5-7 (planned)

---

## 🚧 MDM & graph completeness (Active)

**Milestone Goal:** All phased pipeline stages (bronze → MDM → gold) run reliably at scale.
The MDM graph correctly classifies entity relationships. `mdm-verify-graph` reports zero
relationship defects for a full 100-company dataset.

### Phases

- [ ] **Phase 1: MDM Entity Resolution** - Universe seeding and entity deduplication at scale
- [ ] **Phase 2: Neo4j Sync Correctness** - Idempotent graph sync with end-to-end verification
- [ ] **Phase 3: Relationship Coverage** - IS_INSIDER and MANAGES_FUND edges fully backfilled
- [ ] **Phase 4: Pipeline Hardening** - Phased pipeline reliability, artifact-policy enforcement, invariant tests

---

## Phase Details

### Phase 1: MDM Entity Resolution
**Goal**: The MDM entity store is seeded and populated with a deduplicated, stable entity set
for the full tracked company universe.
**Depends on**: Nothing (first phase of milestone)
**Requirements**: REQ-MDM-01, REQ-MDM-02
**Success Criteria** (what must be TRUE):
  1. `edgar-warehouse mdm seed-universe` completes without error and the MDM PostgreSQL store
     contains the full tracked CIK universe with correct tracking statuses
  2. `edgar-warehouse mdm run` completes against the full silver dataset and produces a
     deterministic entity count — re-running does not increase the count
  3. No duplicate CIK-level entity records exist in the MDM store after two consecutive runs
  4. Active CIK list from MDM correctly gates which companies `bootstrap-batch` processes
**Plans**: TBD

### Phase 2: Neo4j Sync Correctness
**Goal**: The Neo4j graph is synchronized from MDM state, is idempotent, and passes a
structured verification check with no orphaned nodes or ghost edges.
**Depends on**: Phase 1
**Requirements**: REQ-MDM-03, REQ-MDM-04
**Success Criteria** (what must be TRUE):
  1. `edgar-warehouse mdm sync-graph` completes without error and produces a node count and
     edge count consistent with the MDM entity set
  2. Running `mdm-sync-graph` twice in succession produces identical node and edge counts
     (no accumulating duplicates)
  3. `edgar-warehouse mdm verify-graph` runs to completion and outputs a structured report
     covering node counts, edge counts, and relationship integrity
  4. `mdm-verify-graph` reports zero orphaned nodes after a full sync
**Plans**: TBD

### Phase 3: Relationship Coverage
**Goal**: Every IS_INSIDER relationship (Forms 3/4/5 reporter to issuer) and every
MANAGES_FUND relationship (adviser to private fund) is present in Neo4j, verified by
`mdm-verify-graph`.
**Depends on**: Phase 2
**Requirements**: REQ-MDM-05, REQ-MDM-06, REQ-MDM-07
**Success Criteria** (what must be TRUE):
  1. `edgar-warehouse mdm backfill-relationships` runs without error after `mdm-run`
  2. `mdm-verify-graph` confirms IS_INSIDER edge count matches the count of distinct
     reporter-issuer pairs in the silver ownership dataset — zero uncovered pairs
  3. `mdm-verify-graph` confirms MANAGES_FUND edge count matches the count of distinct
     adviser-fund pairs in silver — zero uncovered pairs
  4. Re-running `mdm-backfill-relationships` against unchanged silver data produces no
     increase in IS_INSIDER or MANAGES_FUND edge counts (idempotent)
**Plans**: TBD

### Phase 4: Pipeline Hardening
**Goal**: The full phased pipeline (`bootstrap_phased`) completes reliably for a 100-company
dataset; the `--artifact-policy skip` invariant is enforced; `GOLD_AFFECTING_COMMANDS`
invariants are machine-verifiable.
**Depends on**: Phase 1 (MDM baseline required to run full pipeline)
**Requirements**: REQ-PIPE-01, REQ-PIPE-02, REQ-PIPE-03
**Success Criteria** (what must be TRUE):
  1. `bootstrap_phased` Step Function reaches SUCCEEDED state for a 100-company input with no
     manual intervention; completes within 20 minutes
  2. Running `bootstrap_phased` against an already-loaded dataset makes zero SEC API calls for
     previously-captured ownership XMLs (confirming `--artifact-policy skip` is active)
  3. A script or automated check asserts that `bootstrap-batch` is NOT in
     `GOLD_AFFECTING_COMMANDS` and `gold-refresh` IS — and exits non-zero if either invariant
     is violated
  4. Any stage failure in `bootstrap_phased` surfaces as an explicit Step Functions error —
     not a silent skip or partial success
**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. MDM Entity Resolution | MDM & graph completeness | 0/TBD | Not started | - |
| 2. Neo4j Sync Correctness | MDM & graph completeness | 0/TBD | Not started | - |
| 3. Relationship Coverage | MDM & graph completeness | 0/TBD | Not started | - |
| 4. Pipeline Hardening | MDM & graph completeness | 0/TBD | Not started | - |

---

## 📋 Gold Layer Enrichment (Planned)

**Milestone Goal:** Expand gold layer accuracy and coverage — resolve geography dimension for
ADVISER_OFFICES, complete documentation debt, and harden Snowflake task observability.

Candidate phases (not yet committed):
- Phase 5: Geography dimension (resolve ADVISER_OFFICES.geography_key surrogate; enable map plots)
- Phase 6: Gold table accuracy (ticker coverage, COMPANY field completeness, FILING_DETAIL edge cases)
- Phase 7: Documentation and ADR formalization (promote DEC-001 through DEC-005 to formal ADRs;
  fix CLAUDE.md gold table count; update README.md to use uv)

These phases are backlog items until MDM & graph completeness milestone ships.
