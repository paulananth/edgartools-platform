# Roadmap: Warehouse S3 duplicate-storage reclaim

workstream: s3-silverstage-lifecycle
status: planning
milestone: v1.0 Warehouse S3 duplicate-storage reclaim
updated: 2026-08-20

---

## Overview

Seal the prod warehouse lifecycle so `expire-silver-staging-candidates` stays on the live joined prefix `warehouse/silverstage/` (and identity-refresh unique keys expire after 7 days on the same lifecycle resource). Then add a VersionId reclaim primitive, delete leftover warehouse DuckDB/parquet duplicates without touching current canonical silver, inventory bronze before any bronze delete, and set CloudWatch log retention to 3 days.

**Constraints (all phases):**
- Do not reclaim until leak-seal apply cannot revert the staging prefix.
- Do not put VersionId deletes into Terraform. Terraform owns standing lifecycle only.
- Never treat current canonical `warehouse/silver/sec/silver.duckdb` or `shards/shard-{0-3}.duckdb` as objects to delete.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Leak-seal** - Bind join() keys to Terraform, apply prod lifecycle, add identity-refresh 7-day expiry
- [ ] **Phase 2: Reclaim primitive** - Dry-run TSV, confirm-flag VersionId delete, bytes proof, empty second run
- [ ] **Phase 3: Warehouse duplicates** - Reclaim noncurrent shards, historical identity snapshots, historical gold run_id copies
- [ ] **Phase 4: Bronze inventory** - Report duplicate/noncurrent bronze versions before any bronze delete
- [ ] **Phase 5: CloudWatch 3-day retention** - Platform log groups retain 3 days; older logs are deleted

## Phase Details

### Phase 1: Leak-seal
**Goal**: Staging lifecycle cannot revert to a no-op prefix, and unique identity-refresh keys expire on a standing 7-day rule
**Depends on**: Nothing (first phase)
**Requirements**: REGR-01, LIFE-01, IDEN-02
**Success Criteria** (what must be TRUE):
  1. Operator can run the lifecycle-prefix regression and it fails if the Terraform filter is not a prefix of `StorageLocation.join("silverstage", ...)` live keys
  2. Operator can apply prod Terraform and live `expire-silver-staging-candidates` stays on `warehouse/silverstage/` (does not revert to `silverstage/`)
  3. Operator can see standing 7-day expiry on `warehouse/identity_refresh/` in the same applied warehouse lifecycle document
  4. Operator can confirm the 7-day noncurrent `warehouse/silver/` rule is still present with no current-object expiration
**Plans**: TBD

### Phase 2: Reclaim primitive
**Goal**: Operators can permanently delete billed warehouse versions through a reviewed dry-run contract, without Terraform one-shot deletes
**Depends on**: Phase 1
**Requirements**: SAFE-01, SAFE-02
**Success Criteria** (what must be TRUE):
  1. Operator can dry-run a VersionId delete and get a reviewed TSV of key, version_id, last_modified, size_bytes, and is_latest
  2. Operator can `--apply` only with a distinct confirm flag, in batches of 100, and get a post-list proof that selected VersionIds are gone
  3. Operator can see count + GiB reclaimed per prefix
  4. Operator can re-run apply against an empty candidate set and that empty run is success
**Plans**: TBD

### Phase 3: Warehouse duplicates
**Goal**: Duplicate warehouse DuckDB/parquet copies are gone while current silver and the latest complete gold run per table remain
**Depends on**: Phase 1, Phase 2
**Requirements**: SHARD-01, IDEN-01, GOLD-01
**Success Criteria** (what must be TRUE):
  1. Operator can permanently delete noncurrent `shard-*.duckdb` versions while current `shard-0`…`shard-3` and `silver.duckdb` remain
  2. Operator can delete historical `warehouse/identity_refresh/` run snapshots while any in-flight `run_id` is skipped
  3. Operator can delete historical `warehouse/gold/` `run_id=` copies and still have the latest complete run per table by `LastModified` (not UUID sort)
  4. Operator can confirm live lifecycle still shows `warehouse/silverstage/` before the first reclaim `--apply`
**Plans**: TBD

### Phase 4: Bronze inventory
**Goal**: Operators know whether bronze billed waste exists before any bronze delete
**Depends on**: Phase 3
**Requirements**: BRON-01
**Success Criteria** (what must be TRUE):
  1. Operator can inventory the bronze bucket for duplicate/noncurrent versions
  2. Operator receives a report before any bronze delete
  3. Immutable SEC objects stay unless that inventory proves billed waste
**Plans**: TBD

### Phase 5: CloudWatch 3-day retention
**Goal**: Platform CloudWatch logs older than 3 days do not accumulate
**Depends on**: Phase 4
**Requirements**: CW-01
**Success Criteria** (what must be TRUE):
  1. Operator can inspect CloudWatch log groups used by this platform and see 3-day retention
  2. Logs older than 3 days are deleted
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Leak-seal | 0/? | Not started | - |
| 2. Reclaim primitive | 0/? | Not started | - |
| 3. Warehouse duplicates | 0/? | Not started | - |
| 4. Bronze inventory | 0/? | Not started | - |
| 5. CloudWatch 3-day retention | 0/? | Not started | - |

## Coverage

| Requirement | Phase | Status |
|-------------|-------|--------|
| LIFE-01 | Phase 1 | Pending |
| REGR-01 | Phase 1 | Pending |
| SAFE-01 | Phase 2 | Pending |
| SAFE-02 | Phase 2 | Pending |
| SHARD-01 | Phase 3 | Pending |
| IDEN-01 | Phase 3 | Pending |
| IDEN-02 | Phase 1 | Pending |
| GOLD-01 | Phase 3 | Pending |
| BRON-01 | Phase 4 | Pending |
| CW-01 | Phase 5 | Pending |

Mapped: 10/10 v1 requirements
