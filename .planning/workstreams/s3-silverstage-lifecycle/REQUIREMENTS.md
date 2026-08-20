# Requirements: Warehouse S3 duplicate-storage reclaim

**Defined:** 2026-08-20
**Core Value:** Canonical silver stays intact while duplicate warehouse storage cannot silently accumulate again.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Lifecycle seal

- [ ] **LIFE-01**: Operator can apply prod Terraform so `expire-silver-staging-candidates` stays on `warehouse/silverstage/` and cannot revert to `silverstage/`
- [ ] **REGR-01**: A regression fails if the Terraform lifecycle filter is not a prefix of `StorageLocation.join("silverstage", ...)` live keys

### Reclaim safety

- [ ] **SAFE-01**: Operator can dry-run a VersionId delete to a reviewed TSV, then `--apply` with a distinct confirm flag, batches of 100, and a post-list proof
- [ ] **SAFE-02**: Operator can see count + GiB reclaimed per prefix; a second empty run is success

### Duplicate reclaim

- [ ] **SHARD-01**: Operator can permanently delete noncurrent `shard-*.duckdb` versions without deleting current `shard-0`…`shard-3` or `silver.duckdb`
- [ ] **IDEN-01**: Operator can delete historical `warehouse/identity_refresh/` run snapshots, skipping any in-flight `run_id`
- [ ] **IDEN-02**: Standing Terraform expiry of 7 days on `warehouse/identity_refresh/` so unique run keys do not reaccumulate
- [ ] **GOLD-01**: Operator can delete historical `warehouse/gold/` `run_id=` copies and keep the latest complete run per table by `LastModified` (not UUID sort)

### Bronze check

- [ ] **BRON-01**: Operator can inventory the bronze bucket for duplicate/noncurrent versions and get a report before any bronze delete (immutable SEC objects stay unless the inventory proves billed waste)

### CloudWatch

- [ ] **CW-01**: CloudWatch log groups used by this platform retain 3 days; logs older than 3 days are deleted

## Future Requirements

Deferred to a later milestone.

- Recurring lifecycle on gold (cannot express keep-latest)
- Keep-N gold runs
- Version-aware `ObjectStorage.delete_object`
- CloudWatch cost alarms
- ECR rollback-tag prune
- Empty `edgartools-dev-images` repo delete

## Out of Scope

| Feature | Reason |
|---------|--------|
| Delete current canonical `silver.duckdb` / `shard-{0-3}.duckdb` | Core value: canonical silver stays |
| Blind bronze content delete | Bronze is immutable SEC capture; BRON-01 is inventory-first |
| Shorten 7-day `warehouse/silver/` noncurrent rule | Standing policy stays; SHARD-01 is a one-shot of already-superseded versions |
| Terraform state objects | Needed for apply; kilobytes |
| `aws s3 rm --recursive` as the reclaim path | Leaves billed versions on this versioned bucket |
| New buckets / non-AWS storage | Platform is AWS-only |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| LIFE-01 | — | Pending |
| REGR-01 | — | Pending |
| SAFE-01 | — | Pending |
| SAFE-02 | — | Pending |
| SHARD-01 | — | Pending |
| IDEN-01 | — | Pending |
| IDEN-02 | — | Pending |
| GOLD-01 | — | Pending |
| BRON-01 | — | Pending |
| CW-01 | — | Pending |

**Coverage:**
- v1 requirements: 10 total
- Mapped to phases: 0
- Unmapped: 10

---
*Requirements defined: 2026-08-20*
*Last updated: 2026-08-20 after v1.0 scoping*
