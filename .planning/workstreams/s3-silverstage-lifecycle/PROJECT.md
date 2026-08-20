# Project: Warehouse S3 duplicate-storage reclaim

workstream: s3-silverstage-lifecycle
status: active
updated: 2026-08-20

---

## What This Is

Operator workstream for the prod warehouse S3 bucket
(`edgartools-prod-warehouse-690839588395`). It seals the silverstage
lifecycle prefix leak and reclaims leftover duplicate DuckDB/parquet
copies that are not canonical silver.

## Core Value

Canonical silver stays intact while duplicate warehouse storage cannot
silently accumulate again.

## Current Milestone: v1.0 Warehouse S3 duplicate-storage reclaim

**Goal:** Keep the silverstage lifecycle filter on the live key prefix, and
reclaim remaining duplicate warehouse objects without touching canonical
silver, bronze, or Terraform state.

**Target features:**
- Apply prod Terraform so `expire-silver-staging-candidates` stays on
  `warehouse/silverstage/` and cannot revert to `silverstage/`
- Add a regression check that the lifecycle filter matches live
  `ObjectStorage.join()` keys
- Reclaim ~315 GiB of noncurrent `shard-*.duckdb` versions; keep current
  `shard-0`…`shard-3` and `silver.duckdb`
- Reclaim ~19 GiB identity-refresh snapshots (historical
  `reference_snapshot.duckdb` / `delta.duckdb` run copies)
- Reclaim ~3.4 GiB historical gold `run_id=` parquet copies; keep the
  latest run per table

## Requirements

### Validated

- ✓ Live `warehouse/silverstage/` object delete (2,011 versions, 1.71 TiB) — 2026-08-20
- ✓ Live lifecycle filter corrected to `warehouse/silverstage/` — 2026-08-20
- ✓ Terraform source prefix corrected on `claude/silverstage-lifecycle` (`9d18e5ef`) — 2026-08-20

### Active

- [ ] Prod Terraform apply of the warehouse lifecycle prefix
- [ ] Regression that the lifecycle filter matches live keys
- [ ] Noncurrent shard version reclaim (current shards untouched)
- [ ] Identity-refresh snapshot reclaim
- [ ] Historical gold `run_id=` reclaim (keep latest run per table)

### Out of Scope

- ECR rollback tags and empty `edgartools-dev-images` — billed storage is negligible because layers are shared
- Bronze filings — different layer, not duplicate warehouse objects
- Terraform state objects — kilobytes, needed for apply
- CloudWatch cost alarms — monitoring, not reclaim
- Changing the 7-day canonical-silver noncurrent policy — this milestone executes reclaim of already-superseded shard versions, it does not shorten the standing rule
- Canonical current `warehouse/silver/sec/silver.duckdb` and `shards/shard-{0-3}.duckdb`

## Context

`ObjectStorage.write_staged_bytes` writes a relative path
`silverstage/<uuid>/...`. `ObjectStorage.join()` prefixes
`WAREHOUSE_STORAGE_ROOT`, which already ends in `/warehouse`, so live keys
are `warehouse/silverstage/<uuid>/...`. The Terraform lifecycle filter was
`silverstage/`, which matched nothing. Confirmed 2026-08-20: 1,999 orphaned
DuckDB copies, 1.70 TiB.

`promote_staged` leaves staging objects in place on
`PromotionConflictError`. The 3-day expiry is the backstop; it only works
if the prefix matches live keys.

Remaining duplicates after the staging delete:
- ~315 GiB noncurrent `warehouse/silver/sec/shards/shard-*.duckdb` versions
- ~19 GiB `warehouse/identity_refresh/` run snapshots
- ~3.4 GiB `warehouse/gold/` historical `run_id=` parquet copies

## Constraints

- **Safety:** Never delete current canonical silver keys
- **Safety:** Never delete bronze or tfstate
- **AWS-only:** Account `690839588395`, bucket
  `edgartools-prod-warehouse-690839588395`
- **Terraform:** Passive infrastructure only; do not put image digests or
  runtime secrets into AWS Terraform
- **Apply:** Live lifecycle is already correct; Terraform apply must not
  restore `silverstage/`

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Reclaim remaining duplicates in v1.0, not leak-seal only | User scoped v1.0 to seal + remaining S3 duplicates | — Pending |
| Keep latest gold `run_id` per table | Latest export is the live gold snapshot; older runs are duplicates | — Pending |
| Delete identity-refresh historical run copies | Per-run debug snapshots, not canonical silver | — Pending |
| Delete noncurrent shard versions immediately | They are already superseded; current shards stay | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-20 after v1.0 milestone start*
