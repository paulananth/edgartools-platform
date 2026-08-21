# Project: Warehouse S3 duplicate-storage reclaim

workstream: s3-silverstage-lifecycle
status: complete
updated: 2026-08-21

---

## What This Is

Operator workstream for the prod warehouse S3 bucket
(`edgartools-prod-warehouse-690839588395`). It sealed the silverstage
lifecycle prefix leak and reclaimed leftover duplicate DuckDB/parquet
copies that are not canonical silver.

## Core Value

Canonical silver stays intact while duplicate warehouse storage cannot
silently accumulate again.

## Current State

Shipped **v1.0 Warehouse S3 duplicate-storage reclaim** on 2026-08-21.

- Live silverstage VersionId delete: 2,011 versions / 1.71 TiB (2026-08-20)
- Standing lifecycle on Joined Live Keys: staging `warehouse/silverstage/` 3/3, identity `warehouse/identity_refresh/` 7/7, Canonical Silver `warehouse/silver/` noncurrent-only 7
- Sibling reclaim tool; one-shot apply 1,669 versions / 339.8 GiB (shards, identity, extra gold runs)
- Bronze inventory: no material current-key duplicates
- CloudWatch stays 7 days (CW-01 dropped)

## Next Milestone Goals

Not started in this workstream. If a follow-up is needed:

- Stop the warehouse-bucket gold dual-write and reclaim remaining `warehouse/gold/` with no keep-latest
- Optional abort of 156 empty silverstage MPUs (0 billed bytes)

Use `/gsd:new-milestone --ws <name>` rather than reopening this archived v1.0.

## Requirements

### Validated

- ✓ Live `warehouse/silverstage/` object delete (2,011 versions, 1.71 TiB) — 2026-08-20
- ✓ Live lifecycle filter corrected to `warehouse/silverstage/` — 2026-08-20
- ✓ Terraform source prefix + identity-refresh 7/7 + architecture `join()` tests — v1.0
- ✓ Targeted prod lifecycle apply — v1.0
- ✓ VersionId reclaim primitive (dry-run TSV, confirm flag, batches of 100) — v1.0
- ✓ Noncurrent shard + noncurrent duckdb reclaim; current Canonical Silver stays — v1.0
- ✓ Identity-refresh historical run reclaim with 24h skip — v1.0
- ✓ Historical gold `run_id=` reclaim; newest complete run kept — v1.0
- ✓ Bronze duplicate/noncurrent inventory; no bronze delete — v1.0

### Active

None in this workstream.

### Out of Scope

- ECR rollback tags and empty `edgartools-dev-images`
- Bronze filings delete
- Terraform state objects
- CloudWatch 3-day retention (CW-01 dropped; seven-day floor stands)
- Changing the 7-day canonical-silver noncurrent policy
- Canonical current `warehouse/silver/sec/silver.duckdb` and `shards/shard-{0-3}.duckdb`

## Context

`ObjectStorage.write_staged_bytes` writes a relative path
`silverstage/<uuid>/...`. `ObjectStorage.join()` prefixes
`WAREHOUSE_STORAGE_ROOT`, which already ends in `/warehouse`, so live keys
are `warehouse/silverstage/<uuid>/...`. The Terraform lifecycle filter was
`silverstage/`, which matched nothing.

Execution after discuss-phase used Ask Matt (`/to-spec` → `/to-tickets` →
`/implement`) under `.scratch/warehouse-s3-duplicate-reclaim/`, not GSD
PLAN.md. PR #428 merged leak-seal + reclaim to `main`.

Remaining billed `warehouse/gold/` keep-set (~0.5 GiB) is a dual-write of
the source-dimensional export; Snowflake native-pull reads the export
bucket. That writer is follow-up work.

## Constraints

- **Safety:** Never delete current canonical silver keys
- **Safety:** Never delete bronze or tfstate
- **AWS-only:** Account `690839588395`, bucket
  `edgartools-prod-warehouse-690839588395`
- **Terraform:** Passive infrastructure only; do not put image digests or
  runtime secrets into AWS Terraform
- **Apply:** Lifecycle prefixes must stay Joined Live Keys

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Reclaim remaining duplicates in v1.0, not leak-seal only | User scoped v1.0 to seal + remaining S3 duplicates | ✓ Shipped |
| Keep latest complete gold `run_id` (not UUID sort; not per-table union) | Partial newer run must not displace last complete snapshot | ✓ Shipped; dual-write stop deferred |
| Delete identity-refresh historical run copies | Per-run debug snapshots, not canonical silver | ✓ Shipped |
| Delete noncurrent shard versions immediately | They are already superseded; current shards stay | ✓ Shipped |
| Drop CW-01 three-day CloudWatch | Seven-day Operational Forensics Window already locked | ✓ Dropped |
| VersionId deletes stay in an operator script | Terraform owns standing lifecycle only | ✓ Shipped |
| Convert GSD fog Phases 2–5 to wayfinder then `/to-spec` | User chose Ask Matt over GSD plan-phase | ✓ Shipped |

## Evolution

This document evolves at phase transitions and milestone boundaries.

---
*Last updated: 2026-08-21 after v1.0 milestone close*
