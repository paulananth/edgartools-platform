# 10 — Reclaim leftover warehouse duplicates

**What to build:** Operator dry-run then apply of the sibling reclaim tool, in order: noncurrent shards plus the one noncurrent Canonical Silver duckdb version; then Identity Refresh Run snapshots older than 24 hours; then gold `run_id=` copies outside the keep-set (including their noncurrent versions). Bytes reclaimed are reported. Current Canonical Silver remains. Staging versions stay empty.

**Blocked by:** 08 — Targeted prod lifecycle apply; 09 — Sibling VersionId Reclaim tool

**Status:** resolved

- [x] Dry-run TSVs reviewed before each prefix apply
- [x] Noncurrent shard versions and the one noncurrent Canonical Silver duckdb version are gone; current shards and current duckdb remain
- [x] Identity Refresh Run snapshots older than 24 hours are gone; younger run dirs skipped
- [x] Gold keep-set (union of per-table newest LastModified `run_id=`) remains; other `run_id=` copies and their noncurrent versions are gone
- [x] Post-list proof and count + GiB per prefix; empty second run succeeds
- [x] Current Canonical Silver keys were never in an apply manifest

Evidence: [10-reclaim-leftover-warehouse-duplicates.md](../research/10-reclaim-leftover-warehouse-duplicates.md)
