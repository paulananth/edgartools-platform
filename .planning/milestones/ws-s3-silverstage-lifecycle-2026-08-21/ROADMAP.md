# Roadmap: Warehouse S3 duplicate-storage reclaim

workstream: s3-silverstage-lifecycle
status: complete
milestone: v1.0 Warehouse S3 duplicate-storage reclaim
updated: 2026-08-21

---

## Milestones

- ✅ **v1.0 Warehouse S3 duplicate-storage reclaim** — Phases 1-4 shipped 2026-08-21; Phase 5 (CW-01) dropped

## Overview

Seal the prod warehouse lifecycle so `expire-silver-staging-candidates` stays on the live joined prefix `warehouse/silverstage/` (and identity-refresh unique keys expire after 7 days on the same lifecycle resource). VersionId reclaim for leftover warehouse DuckDB/parquet duplicates without touching current canonical silver. Bronze inventory before any bronze delete. CloudWatch stays at seven days.

**Constraints (all phases):**
- Do not reclaim until leak-seal apply cannot revert the staging prefix.
- Do not put VersionId deletes into Terraform. Terraform owns standing lifecycle only.
- Never treat current canonical `warehouse/silver/sec/silver.duckdb` or `shards/shard-{0-3}.duckdb` as objects to delete.

## Phases

<details>
<summary>✅ v1.0 Warehouse S3 duplicate-storage reclaim (Phases 1-4) — SHIPPED 2026-08-21</summary>

- [x] **Phase 1: Leak-seal** - Bind join() keys to Terraform, apply prod lifecycle, add identity-refresh 7-day expiry — 2026-08-21
- [x] **Phase 2: Reclaim primitive** - Dry-run TSV, confirm-flag VersionId delete, bytes proof, empty second run — 2026-08-21
- [x] **Phase 3: Warehouse duplicates** - Reclaim noncurrent shards, historical identity snapshots, historical gold run_id copies — 2026-08-21
- [x] **Phase 4: Bronze inventory** - Report duplicate/noncurrent bronze versions before any bronze delete — 2026-08-21
- [x] **Phase 5: CloudWatch 3-day retention** - Dropped (seven-day Operational Forensics Window stands)

</details>

## Phase Details

### Phase 1: Leak-seal
**Goal**: Staging lifecycle cannot revert to a no-op prefix, and unique identity-refresh keys expire on a standing 7-day rule
**Depends on**: Nothing (first phase)
**Requirements**: REGR-01, LIFE-01, IDEN-02
**Plans**: wayfinder tickets 07-08 (no GSD PLAN.md)
**Details:** See `phases/01-leak-seal/01-SUMMARY.md`

### Phase 2: Reclaim primitive
**Goal**: Operators can permanently delete billed warehouse versions through a reviewed dry-run contract, without Terraform one-shot deletes
**Depends on**: Phase 1
**Requirements**: SAFE-01, SAFE-02
**Plans**: wayfinder ticket 09
**Details:** See `phases/02-reclaim-primitive/02-SUMMARY.md`

### Phase 3: Warehouse duplicates
**Goal**: Duplicate warehouse DuckDB/parquet copies are gone while current silver and the latest complete gold run per table remain
**Depends on**: Phase 1, Phase 2
**Requirements**: SHARD-01, IDEN-01, GOLD-01
**Plans**: wayfinder ticket 10
**Details:** See `phases/03-warehouse-duplicates/03-SUMMARY.md`

### Phase 4: Bronze inventory
**Goal**: Operators know whether bronze billed waste exists before any bronze delete
**Depends on**: Phase 3
**Requirements**: BRON-01
**Plans**: wayfinder ticket 05
**Details:** See `phases/04-bronze-inventory/04-SUMMARY.md`

### Phase 5: CloudWatch 3-day retention (DROPPED)
**Goal**: Platform CloudWatch logs older than 3 days do not accumulate
**Depends on**: Phase 4
**Requirements**: CW-01
**Plans**: none — dropped
**Details:** See `phases/05-cloudwatch-retention/05-SUMMARY.md`

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Leak-seal | 1/1 (wayfinder) | Complete | 2026-08-21 |
| 2. Reclaim primitive | 1/1 (wayfinder) | Complete | 2026-08-21 |
| 3. Warehouse duplicates | 1/1 (wayfinder) | Complete | 2026-08-21 |
| 4. Bronze inventory | 1/1 (wayfinder) | Complete | 2026-08-21 |
| 5. CloudWatch 3-day retention | 0/0 | Dropped | 2026-08-21 |

## Coverage

| Requirement | Phase | Status |
|-------------|-------|--------|
| LIFE-01 | Phase 1 | Complete |
| REGR-01 | Phase 1 | Complete |
| SAFE-01 | Phase 2 | Complete |
| SAFE-02 | Phase 2 | Complete |
| SHARD-01 | Phase 3 | Complete |
| IDEN-01 | Phase 3 | Complete |
| IDEN-02 | Phase 1 | Complete |
| GOLD-01 | Phase 3 | Complete |
| BRON-01 | Phase 4 | Complete |
| CW-01 | Phase 5 | Dropped |

Mapped: 10/10 v1 requirements (9 complete, 1 dropped)
