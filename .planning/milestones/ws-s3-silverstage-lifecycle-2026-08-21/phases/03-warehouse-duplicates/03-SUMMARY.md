# Phase 3: Warehouse duplicates — Summary

**Status:** complete
**Shipped:** 2026-08-21

## One-liner

One-shot VersionId reclaim: 1,669 versions / 339.8 GiB after the earlier 1.71 TiB silverstage delete; current Canonical Silver untouched.

## Delivered

- Noncurrent shards + noncurrent `silver.duckdb` gone; current shards and duckdb remain
- Identity Refresh Run snapshots older than 24h gone
- Historical gold `run_id=` copies outside the newest complete run gone
- Second dry-run empty

## Requirements

SHARD-01, IDEN-01, GOLD-01 (keep newest complete `run_id`) — validated.

## Follow-up (not this milestone)

`warehouse/gold/` is a dual-write leftover; Snowflake gold does not read it. Stopping the writer and reclaiming the prefix with no keep-set is a later effort.
