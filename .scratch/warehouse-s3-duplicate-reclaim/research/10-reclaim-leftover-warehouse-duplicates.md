# Reclaim leftover warehouse duplicates (ticket 10)

Date: 2026-08-21  
Profile: `aws-admin-prod`  
Bucket: `edgartools-prod-warehouse-690839588395`

Dry-run reviewed first (`20260821T101810Z`): 1669 versions, **339.795 GiB**.
Current Canonical Silver count in that manifest: **0**.

Sequential apply of split manifests:

| Prefix | Versions deleted | GiB | Evidence run |
| --- | ---: | ---: | --- |
| shards + noncurrent `silver.duckdb` | 831 | 316.927 | `20260821T101856Z` |
| identity_refresh (all older than 24h) | 614 | 19.093 | `20260821T102022Z` |
| gold outside keep-set | 224 | 3.775 | `20260821T102133Z` |
| **Total** | **1669** | **339.795** | |

Keep-set gold `run_id`: `ticket42-task35-fulluniverse-retry7-1786673391` (newest LastModified on every parquet table).

Post-conditions:
- Current `silver.duckdb` 1.48 GiB and four current shards remain; noncurrent count 0.
- `warehouse/identity_refresh/` recursive listing: 0 objects.
- `warehouse/silverstage/` versions: 0.
- Second dry-run: **0 object versions (0.0 GiB)**.

S3 evidence prefixes:
`s3://edgartools-prod-warehouse-690839588395/warehouse/release-evidence/warehouse-duplicate-reclaim/`
