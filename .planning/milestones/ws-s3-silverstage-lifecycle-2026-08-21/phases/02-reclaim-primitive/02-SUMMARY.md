# Phase 2: Reclaim primitive — Summary

**Status:** complete
**Shipped:** 2026-08-21

## One-liner

Sibling VersionId Reclaim tool (not ADR 0004 staging cleanup): dry-run TSV, distinct confirm flag, batches of 100, Canonical Silver deny-list.

## Delivered

- `edgar_warehouse/infrastructure/warehouse_duplicate_reclaim.py`
- `infra/scripts/reclaim-warehouse-duplicates.sh`
- Fixture tests; empty second run is success
- Evidence under warehouse release-evidence prefix

## Requirements

SAFE-01, SAFE-02 — validated.
