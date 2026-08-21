# Feature Research

**Domain:** Operator warehouse S3 storage hygiene (lifecycle prefix correctness + versioned duplicate reclaim)
**Researched:** 2026-08-20
**Confidence:** HIGH (AWS lifecycle/version-delete contracts and this repo's existing operator scripts); remaining GiB figures are from the workstream inventory, not re-measured in this pass

## Feature Landscape

This milestone does **not** invent a product surface. It adds leak-seal + remaining duplicate reclaim on the existing AWS warehouse bucket `edgartools-prod-warehouse-690839588395`. Canonical current silver (`warehouse/silver/sec/silver.duckdb` and `shards/shard-{0-3}.duckdb`) stays. Already done: live `warehouse/silverstage/` orphan delete and live lifecycle filter correction.

### Table Stakes (Operators Expect These)

Missing any of these means the leak can revert, billed versions survive, or canonical silver is at risk.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Prod Terraform apply of `expire-silver-staging-candidates` on `warehouse/silverstage/` | Live filter is already correct; unapplied Terraform is how it reverts to `silverstage/` (matches nothing) | LOW | Apply `infra/terraform/accounts/prod` (`storage_buckets`). Plan must not restore `prefix = "silverstage/"`. Passive infra only. |
| Lifecycle-prefix regression vs `ObjectStorage.join()` | The original leak was prefix-string mismatch, not a missing rule. A source-only Terraform assert would have missed it if `join()` still prepends `/warehouse` | MEDIUM | Construct live keys from `WAREHOUSE_STORAGE_ROOT` + relative `silverstage/<uuid>/...`. Assert every constructed key starts with the Terraform filter. Negative case: `silverstage/` must not match. Pattern: `tests/architecture/test_ecr_image_retention.py` plus `tests/unit/test_object_storage_conditional_promotion.py` (already proves joined key `warehouse/silverstage/...`). |
| Immediate reclaim of noncurrent `shard-*.duckdb` versions (~315 GiB) | 7-day `expire-noncurrent-silver-canonical-versions` on `warehouse/silver/` is the standing backstop, not this reclaim. Operators expect the already-superseded shard copies gone now | MEDIUM | `list-object-versions` under `warehouse/silver/sec/shards/`. Delete only `IsLatest=false`. Keep current `shard-0`…`shard-3` and current `silver.duckdb`. Do not add an `expiration` block on `warehouse/silver/`. |
| Identity-refresh snapshot reclaim (~19 GiB) | Per-run `reference_snapshot.duckdb` / `delta.duckdb` are debug copies, not canonical silver | MEDIUM | Live keys: `warehouse/identity_refresh/runs/{run_id}/reference/reference_snapshot.duckdb` and `.../batches/{batch_id}/delta.duckdb` (`identity_refresh_publication.py` `_RUN_PREFIX`). Unique keys per run, so these are **current** versions of distinct objects — lifecycle noncurrent expiry on silver will not touch them. |
| Historical gold `run_id=` reclaim, keep latest per table (~3.4 GiB) | Each gold-refresh writes a new hive partition; old parquet is duplicate warehouse storage. Latest export is the live snapshot | MEDIUM | Path: `gold/{table_name}/run_id={run_id}/{table}.parquet` → live `warehouse/gold/{table}/run_id=...`. `run_id` is `uuid.uuid4()` (`_resolve_run_id`), so lexicographic sort is **not** chronological. Keep the current object with max `LastModified` per table. |
| Versioned `DeleteObjects` (`Key` + `VersionId`) | Warehouse bucket versioning is Enabled. A simple DELETE creates a billed delete marker and leaves the payload | MEDIUM | AWS: unversioned DELETE inserts a delete marker; permanent reclaim requires `DELETE Object versionId`. This repo already does this in `cleanup-s3-staging.sh` and `delete-bronze-historic-manifest.sh`. |
| Dry-run → reviewed manifest → explicit `--apply` + confirm flag | Operators will not run a live delete against silver-adjacent prefixes without a reviewed VersionId list | LOW | Copy the staging-cleanup contract: default dry-run, `--apply` requires `--confirm-delete-*` and a reviewed TSV of exact VersionIds, prefix allowlist on every row. |
| Post-delete proof that selected VersionIds are gone and protected keys remain | "Deleted" without `list-object-versions` post-check is how billed versions survive | LOW | Existing pattern: delete-report JSON + post listing; fail if any selected `(key, version_id)` remains; separately assert current canonical silver keys still `IsLatest`. |
| `DeleteObjects` batch cap (≤1000, this repo uses 100) | Combined Versions+DeleteMarkers pages overflow 1000 (`destroy-aws-complete.sh` MalformedXML 5-whys) | LOW | Staging cleanup already batches 100 with `Quiet: false`. Do not raise above 1000. |

### Differentiators (Competitive Advantage)

Not required for the reclaim to work, but they are how this platform already avoids silent storage leaks.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Join()-derived lifecycle test, not Terraform-string-only | Prevents the exact class of bug: relative write path `silverstage/` vs live key `warehouse/silverstage/` | LOW | Architecture test should call `StorageLocation(root).join("silverstage", token, "silver/sec/silver.duckdb")` with a root ending in `/warehouse` and assert startswith Terraform prefix. |
| Fail-closed allowlist before first delete | One wrong prefix on a versioned bucket is a canonical-silver wipe | MEDIUM | Hard-refuse any candidate whose key is `warehouse/silver/sec/silver.duckdb` or `warehouse/silver/sec/shards/shard-[0-3].duckdb` **and** `IsLatest=true`. Gold: refuse if the selected latest run per table is in the delete set. |
| Keep-latest gold by `LastModified`, not `run_id` sort | UUID run_ids make "max run_id" a random table | LOW | Group current versions by table prefix `warehouse/gold/{table}/run_id=`. Winner = max `LastModified` among `IsLatest=true`. Delete other run partitions **and** their noncurrent versions. |
| Terraform plan gate before apply | Live lifecycle is already correct; apply is only valuable if it cannot restore `silverstage/` | LOW | `terraform plan` must show the warehouse lifecycle prefix remaining `warehouse/silverstage/`. Abort apply on any in-place prefix shrink. |
| Bytes-reclaimed evidence bundle | Operators need to know ~315 / ~19 / ~3.4 GiB actually left the bill | LOW | Pre/post `list-object-versions` summaries (count, bytes, GiB) per prefix, uploaded under a warehouse release-evidence prefix like staging cleanup. |
| Idempotent second run | Reclaim will be re-run after the next gold-refresh / shard publish | LOW | Empty candidate set is success, not an error. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Delete current canonical silver (`silver.duckdb` or current `shard-{0-3}`) | "Wipe silver and rebuild" / prefix too broad (`warehouse/silver/`) | Destroys the only live canonical copies. Lifecycle on this prefix is **noncurrent-only** for that reason | Delete only `IsLatest=false` under `warehouse/silver/sec/shards/`. Never send current VersionIds for those five keys |
| Recursive `aws s3 rm` of bronze (or warehouse) | Fastest-looking cleanup | Bronze is a different bucket/layer, additive/immutable. Recursive rm on a versioned bucket also does not permanently delete versions | Out of scope. Bronze stays. Warehouse reclaim is prefix + VersionId only |
| Unversioned deletes / `delete_object(Key)` without `VersionId` | `ObjectStorage.delete_object` and `aws s3 rm` look like they work (GET 404) | On a versioning-enabled bucket S3 inserts a delete marker; previous versions stay billed. `ObjectStorage.delete_object` is this API | `s3api delete-objects` with `VersionId` on every object, same as `cleanup-s3-staging.sh` |
| `aws s3 rm --recursive` without version listing | Familiar CLI | Creates delete markers; payloads remain; easy to cross into `warehouse/silver/` | Manifest of exact VersionIds under an allowlisted prefix |
| Current-version `expiration` on `warehouse/silver/` | "Just expire silver after N days" | Quiet day expires the only canonical copy | Keep existing `noncurrent_version_expiration` 7 days; no `expiration {}` on that rule |
| Shorten the 7-day canonical-silver noncurrent policy to 0 | Avoid writing a one-shot reclaim | Changes standing policy; this milestone executes already-superseded shard versions, it does not retune the rule | One-shot versioned delete of current noncurrent shard versions; leave the 7-day rule |
| Delete latest gold `run_id=` per table | "Gold lives in Snowflake now" | Warehouse gold parquet is the last local snapshot / debug copy; Snowflake native-pull also keys off run manifests. Wiping the latest run per table is a needless recovery hole | Keep max-`LastModified` current object per `warehouse/gold/{table}/` |
| Reclaim snowflake-export bucket / bronze filings / tfstate / ECR tags | "While we are deleting S3…" | Different buckets/layers; bronze immutable; tfstate required for the lifecycle apply itself; ECR layers shared | Out of scope (PROJECT.md) |
| Rely on `ObjectStorage.delete_object` for reclaim | Already exists, tested | No VersionId → delete marker. That helper is for **current** staging-key cleanup after successful promote, not billed-version reclaim | Operator script using `s3api`, not the warehouse runtime delete helper |
| Terraform-managed one-shot delete of existing objects | Make reclaim repeatable via apply | AWS Terraform must not encode workload commands or one-shot data mutation; lifecycle is the only storage policy Terraform owns | Terraform owns the **ongoing** prefix; operator script owns the **existing** duplicate versions |
| Prefix filter `silverstage/` (no `warehouse/`) | Matches the relative write path in `write_staged_bytes` | Prefix match is a key-string prefix, not a directory. Live keys are `warehouse/silverstage/...`. Confirmed 2026-08-20: 1,999 orphans, 1.70 TiB | Filter **and** test against joined keys |

## Feature Dependencies

```
Lifecycle prefix in Terraform source (already corrected)
    └──requires──> Prod Terraform apply (must not revert prefix)
                       └──enhances──> Join()-based regression test

Versioned DeleteObjects primitive (Key+VersionId, batch ≤1000, dry-run manifest)
    └──requires──> Prefix allowlist + fail-closed current-silver guard
    └──requires──> Noncurrent shard reclaim
    └──requires──> Identity-refresh snapshot reclaim
    └──requires──> Historical gold run_id reclaim
                       └──requires──> Per-table keep-latest (LastModified, not UUID sort)

Post-delete version listing
    └──requires──> All three reclaim jobs
    └──enhances──> Bytes-reclaimed evidence

7-day noncurrent silver lifecycle (already live)
    ──conflicts──> Adding expiration on warehouse/silver/ current versions
    ──does not replace──> Immediate noncurrent shard reclaim
```

### Dependency Notes

- **Terraform apply requires the source prefix already `warehouse/silverstage/`:** it is (commit `9d18e5ef`). Apply is the lock so a later plan cannot silently restore `silverstage/`.
- **Regression test should land with or before apply:** it is the only durable guard that `join()` and the lifecycle filter cannot drift again. It does not need live AWS.
- **All three reclaim jobs require the versioned-delete primitive:** identity-refresh and gold historical copies are **current** objects on unique keys; shard waste is **noncurrent** versions of canonical keys. Same delete API, different selection rule (`IsLatest=false` vs "not the kept current key").
- **Gold keep-latest requires grouping before delete:** a prefix delete of `warehouse/gold/` would remove the latest run too.
- **Do not run gold reclaim concurrently with `gold-refresh`:** a new `run_id=` partition appearing mid-inventory can invert "latest." Drain or wait for no in-flight gold-affecting task (staging cleanup already snapshots running ECS tasks as evidence).
- **Do not run shard noncurrent delete while a shard promote is in flight:** a just-superseded version is still the previous current; deleting it is intended, but deleting the new current is not. Guard on `IsLatest` at delete time, not only at inventory time, or re-list immediately before each batch.
- **7-day rule does not replace shard reclaim:** it will eventually expire today's noncurrent shards, but the ~315 GiB is already superseded and in-scope for v1.0. Do not change `noncurrent_days`.

## MVP Definition

### Launch With (v1)

Minimum to seal the leak and reclaim remaining warehouse duplicates.

- [ ] Prod Terraform apply — lifecycle filter stays `warehouse/silverstage/`; plan shows no revert to `silverstage/`
- [ ] Architecture/unit regression — Terraform prefix equals live `StorageLocation.join("silverstage", ...)` keys
- [ ] Versioned reclaim of noncurrent `warehouse/silver/sec/shards/shard-*.duckdb` — current shards + `silver.duckdb` untouched
- [ ] Versioned reclaim of `warehouse/identity_refresh/runs/**` historical snapshots (`reference_snapshot.duckdb`, `delta.duckdb`)
- [ ] Versioned reclaim of historical `warehouse/gold/{table}/run_id=*` parquet — keep latest current object per table by `LastModified`
- [ ] Operator contract — dry-run manifest, confirm flag, VersionId batches, post-check, fail-closed allowlist

### Add After Validation (v1.x)

- [ ] Recurring identity-refresh / gold `run_id=` lifecycle rules (prefix-correct, current-version expiry on those prefixes only) — trigger: if new run copies re-accumulate after v1.0
- [ ] Include noncurrent `silver.duckdb` versions in a future one-shot if they are still material after the 7-day rule — trigger: inventory shows remaining GiB on that key
- [ ] Keep-N gold runs (not just latest 1) — trigger: operators need a warehouse-side rollback copy

### Future Consideration (v2+)

- [ ] Automated cost alarm on warehouse noncurrent bytes — out of scope (monitoring, not reclaim)
- [ ] Changing the 7-day canonical-silver noncurrent window
- [ ] ECR / bronze / tfstate / snowflake-export reclaim
- [ ] Making `ObjectStorage.delete_object` version-aware — would change promote-success cleanup semantics; not needed if reclaim stays in operator scripts

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Terraform apply (prefix cannot revert) | HIGH | LOW | P1 |
| Join() ↔ lifecycle prefix regression | HIGH | LOW | P1 |
| Versioned delete primitive + dry-run/confirm | HIGH | LOW (clone staging cleanup) | P1 |
| Noncurrent shard version reclaim (~315 GiB) | HIGH | MEDIUM | P1 |
| Identity-refresh snapshot reclaim (~19 GiB) | HIGH | MEDIUM | P1 |
| Gold keep-latest `run_id=` reclaim (~3.4 GiB) | HIGH | MEDIUM | P1 |
| Fail-closed current-silver / latest-gold guards | HIGH | LOW | P1 |
| Post-delete version listing + GiB evidence | MEDIUM | LOW | P1 |
| Recurring lifecycle on identity-refresh / gold prefixes | MEDIUM | LOW | P2 |
| Keep-N gold runs | LOW | MEDIUM | P3 |
| Version-aware `ObjectStorage.delete_object` | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

Not a market-competitor domain. Comparable operator patterns:

| Feature | AWS S3 Lifecycle | This repo (`cleanup-s3-staging.sh` / bronze historic delete) | Our plan |
|---------|------------------|---------------------------------------------------------------|----------|
| Prefix filter | String prefix on the **full key**; empty prefix = whole bucket | Staging script hardcodes `warehouse/_staging/` | Terraform + test must use `warehouse/silverstage/`, the joined live prefix |
| Current vs noncurrent | `Expiration` → delete marker on current; `NoncurrentVersionExpiration` permanently drops old versions | Staging cleanup deletes listed VersionIds regardless of `IsLatest` (those keys are abandoned) | Shards: noncurrent only. Identity-refresh/gold historical: current unique keys, so VersionId-delete those keys except kept gold latest |
| Permanent delete | `delete-objects` with `VersionId` | Batches of 100, `Quiet: false`, confirm flag | Same contract; never `ObjectStorage.delete_object` / `aws s3 rm` |
| Safety | Lifecycle cannot "keep latest hive partition" | Manifest review + prefix allowlist + post-check | Gold keep-latest is application logic on `LastModified`; lifecycle cannot express it |
| One-shot vs policy | Policy only (ongoing) | One-shot operator scripts | Terraform = ongoing leak-seal; scripts = existing duplicate reclaim |

## Expected Behavior (operator contracts)

### Lifecycle prefix tests

1. Read `infra/terraform/modules/storage_buckets/main.tf` rule `expire-silver-staging-candidates`.
2. Assert `filter.prefix == "warehouse/silverstage/"`.
3. Build `StorageLocation("s3://edgartools-prod-warehouse-690839588395/warehouse")`.
4. `join("silverstage", "<token>", "silver/sec/silver.duckdb")` must equal `s3://.../warehouse/silverstage/<token>/silver/sec/silver.duckdb`.
5. The object key after the bucket (`warehouse/silverstage/...`) must start with the Terraform prefix.
6. Negative: prefix `silverstage/` is **not** a prefix of that key.
7. Do not assert against `storage_buckets_destroyable` as the prod path; prod `accounts/prod` uses `storage_buckets`.

### Versioned S3 deletes

1. Inventory with `list-object-versions` + prefix, not `list-objects-v2` (v2 hides noncurrent).
2. Each delete object is `{Key, VersionId}`. Missing VersionId is a bug.
3. Batch size 100 (repo convention) and never >1000 (API hard limit; combined Versions+DeleteMarkers can exceed 1000 per page).
4. Simple DELETE / `aws s3 rm` / `ObjectStorage.delete_object` is forbidden for reclaim: they create delete markers and keep paying.
5. Shards: skip `IsLatest=true` for `warehouse/silver/sec/shards/shard-[0-3].duckdb` and skip the `silver.duckdb` current version entirely.
6. After delete, re-list: selected VersionIds absent; protected current versions still `IsLatest` with nonzero size.

### Keep-latest gold snapshots

1. Scope: `warehouse/gold/{table_name}/run_id={run_id}/{table_name}.parquet` (catalog `gold.table.path`). Not `gold/runs/{command}/{run_id}/manifest.json` unless a later inventory shows those manifests are material.
2. `run_id` is a UUID — do not `max(run_id)`.
3. For each table, among `IsLatest=true` objects, keep the max `LastModified`.
4. Delete every other `run_id=` partition for that table, including noncurrent versions of those keys.
5. If a table has only one current run, delete nothing for that table.
6. Pause while `gold-refresh` / other source-export commands are writing.

## Sources

- AWS S3 lifecycle filter is a key-name prefix (official): [Lifecycle configuration elements](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html), [Lifecycle configuration examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-configuration-examples.html) — HIGH
- AWS versioned delete vs delete markers (official): [Deleting object versions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html), [DeleteObjects API (max 1000 keys; VersionId for permanent delete)](https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteObjects.html) — HIGH
- This repo, live contracts: `infra/terraform/modules/storage_buckets/main.tf` (`warehouse/silverstage/`, `warehouse/silver/` noncurrent 7-day); `edgar_warehouse/infrastructure/object_storage.py` (`join`, `write_staged_bytes` relative `silverstage/`, `delete_object` without VersionId); `edgar_warehouse/config/warehouse_paths.properties` (`gold.table.path`); `edgar_warehouse/application/identity_refresh_publication.py` (`identity_refresh/runs`); `_resolve_run_id` UUID in `warehouse_orchestrator.py` — HIGH
- This repo, operator pattern to copy: `infra/scripts/cleanup-s3-staging.sh`, `infra/scripts/delete-bronze-historic-manifest.sh`, `infra/scripts/destroy-aws-complete.sh` (1000-key MalformedXML lesson) — HIGH
- Remaining GiB / already-completed deletes: `.planning/workstreams/s3-silverstage-lifecycle/PROJECT.md` — MEDIUM (inventory dated 2026-08-20, not re-listed here)

---
*Feature research for: warehouse S3 lifecycle prefix correctness and duplicate-object reclaim*
*Researched: 2026-08-20*
