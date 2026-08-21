# Requirements: Warehouse S3 duplicate-storage reclaim

**Defined:** 2026-08-20
**Closed:** 2026-08-21
**Core Value:** Canonical silver stays intact while duplicate warehouse storage cannot silently accumulate again.

## v1 Requirements

### Lifecycle seal

- [x] **LIFE-01**: Operator can apply prod Terraform so `expire-silver-staging-candidates` stays on `warehouse/silverstage/` and cannot revert to `silverstage/` — **validated** (targeted prod apply 2026-08-21)
- [x] **REGR-01**: A regression fails if the Terraform lifecycle filter is not a prefix of `StorageLocation.join("silverstage", ...)` live keys — **validated** (`tests/architecture/test_warehouse_lifecycle_prefix.py`)

### Reclaim safety

- [x] **SAFE-01**: Operator can dry-run a VersionId delete to a reviewed TSV, then `--apply` with a distinct confirm flag, batches of 100, and a post-list proof — **validated**
- [x] **SAFE-02**: Operator can see count + GiB reclaimed per prefix; a second empty run is success — **validated** (second dry-run 0 versions)

### Duplicate reclaim

- [x] **SHARD-01**: Operator can permanently delete noncurrent `shard-*.duckdb` versions without deleting current `shard-0`…`shard-3` or `silver.duckdb` — **validated** (831 versions / 316.9 GiB)
- [x] **IDEN-01**: Operator can delete historical `warehouse/identity_refresh/` run snapshots, skipping any in-flight `run_id` — **validated** (614 versions / 19.1 GiB; 24h skip)
- [x] **IDEN-02**: Standing Terraform expiry of 7 days on `warehouse/identity_refresh/` so unique run keys do not reaccumulate — **validated** (same lifecycle document as staging)
- [x] **GOLD-01**: Operator can delete historical `warehouse/gold/` `run_id=` copies and keep the latest complete run per table by `LastModified` (not UUID sort) — **validated** (keep newest complete `run_id`; 224 versions / 3.8 GiB outside keep-set). Dual-write of new gold parquet to the warehouse bucket is follow-up, not this requirement.

### Bronze check

- [x] **BRON-01**: Operator can inventory the bronze bucket for duplicate/noncurrent versions and get a report before any bronze delete (immutable SEC objects stay unless the inventory proves billed waste) — **validated** (inventory only; ~0.36 GiB noncurrent, not deleted)

### CloudWatch

- [ ] **CW-01**: CloudWatch log groups used by this platform retain 3 days; logs older than 3 days are deleted — **dropped**. Seven-day Operational Forensics Window stands.

## Future Requirements

Deferred to a later milestone.

- Stop warehouse-bucket gold dual-write (`write_source_export_table_manifest_entry` on `WAREHOUSE_STORAGE_ROOT`) and reclaim remaining `warehouse/gold/` with no keep-latest
- Recurring lifecycle on gold (cannot express keep-latest)
- Keep-N gold runs
- Version-aware `ObjectStorage.delete_object`
- CloudWatch cost alarms
- ECR rollback-tag prune
- Empty `edgartools-dev-images` repo delete
- Abort 156 empty silverstage multipart uploads (0 billed bytes)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Delete current canonical `silver.duckdb` / `shard-{0-3}.duckdb` | Core value: canonical silver stays |
| Blind bronze content delete | Bronze is immutable SEC capture; BRON-01 is inventory-first |
| Shorten 7-day `warehouse/silver/` noncurrent rule | Standing policy stays; SHARD-01 is a one-shot of already-superseded versions |
| Terraform state objects | Needed for apply; kilobytes |
| `aws s3 rm --recursive` as the reclaim path | Leaves billed versions on this versioned bucket |
| New buckets / non-AWS storage | Platform is AWS-only |
| VersionId deletes in Terraform | Terraform owns standing lifecycle; operator script owns existing versions |
| CloudWatch 3-day retention (CW-01) | Dropped; seven-day floor from ops-cost-control stands |

## Traceability

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

**Coverage:**
- v1 requirements: 10 total
- Complete: 9
- Dropped: 1 (CW-01)

---
*Requirements defined: 2026-08-20*
*Last updated: 2026-08-21 at v1.0 close*
