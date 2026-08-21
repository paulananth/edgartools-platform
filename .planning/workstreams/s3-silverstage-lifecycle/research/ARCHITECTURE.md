# Architecture Research

**Domain:** Warehouse S3 lifecycle prefix correctness and duplicate-object reclaim (existing EdgarTools AWS platform)
**Researched:** 2026-08-20
**Confidence:** HIGH for component boundaries and path-join contract (repo + AWS lifecycle docs). MEDIUM for remaining billed sizes (~315 / ~19 / ~3.4 GiB) — those figures come from this workstream's live inventory, not re-measured in this research pass.

## Standard Architecture

This milestone does **not** add a bucket, a second `WAREHOUSE_STORAGE_ROOT`, a new storage adapter, or a runtime cleanup ECS task. It plugs leak-seal and reclaim into the existing warehouse object layout.

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Passive AWS Terraform                            │
│              infra/terraform/accounts/prod → storage_buckets             │
│  aws_s3_bucket.warehouse  (edgartools-prod-warehouse-690839588395)      │
│  versioning = Enabled                                                    │
│  lifecycle (WHOLE config replaced on apply):                             │
│    expire-silver-staging-candidates     prefix warehouse/silverstage/    │
│    expire-noncurrent-silver-canonical   prefix warehouse/silver/         │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Runtime writes (unchanged contract)                   │
│  WAREHOUSE_STORAGE_ROOT = s3://…-warehouse-…/warehouse                   │
│  StorageLocation.join(relative) → s3://bucket/warehouse/<relative>       │
│  Object key (lifecycle filter target) = warehouse/<relative>             │
│                                                                          │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────────┐  │
│  │ write_staged_    │ │ promote to       │ │ gold_table_path /        │  │
│  │ bytes            │ │ silver/sec/…     │ │ identity_refresh/runs/   │  │
│  │ silverstage/uuid │ │ (canonical)      │ │ (per-run copies)         │  │
│  └────────┬─────────┘ └────────┬─────────┘ └────────────┬─────────────┘  │
└───────────┴────────────────────┴────────────────────────┴────────────────┘
            │                    │                        │
            ▼                    ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              Live keys in ONE warehouse bucket, ONE root                 │
│                                                                          │
│  warehouse/silverstage/<uuid>/…     ephemeral; 3-day current+noncurrent  │
│  warehouse/silver/sec/silver.duckdb canonical current (never expire)     │
│  warehouse/silver/sec/shards/shard-{0-3}.duckdb  current keep;           │
│                                     noncurrent 7-day standing + one-off  │
│  warehouse/identity_refresh/runs/<run_id>/…  debug snapshots             │
│  warehouse/gold/<table>/run_id=<id>/…        historical parquet copies   │
│                                                                          │
│  NEVER in this milestone: bronze bucket, tfstate, snowflake-export bucket│
└─────────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         v1.0 control plane                               │
│  Terraform apply     = standing prefix-correct lifecycle (leak-seal)     │
│  Architecture test   = filter prefix is a prefix of join() live keys     │
│  Operator delete     = VersionId DeleteObjects for leftover duplicates   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `StorageLocation.join()` | Prefix `WAREHOUSE_STORAGE_ROOT` (`…/warehouse`) onto a relative path. This is the live key contract. | Existing `edgar_warehouse/infrastructure/object_storage.py`. Do not change for this milestone. |
| `write_staged_bytes` | Write `silverstage/<uuid>/<canonical_relative>` (relative). Live key becomes `warehouse/silverstage/<uuid>/…`. Leaves object on `PromotionConflictError`. | Existing adapter. Success-path callers already `delete_object` the staged key. |
| `aws_s3_bucket_lifecycle_configuration.warehouse` | Standing backstop for prefixes that otherwise live forever. **One resource = entire lifecycle document.** Apply replaces every rule. | Existing `infra/terraform/modules/storage_buckets/main.tf`, applied via `infra/terraform/accounts/prod`. |
| Architecture regression | Fail CI if Terraform filter `silverstage/` (no `warehouse/`) or if join() keys would not match the filter. | **New** `tests/architecture/` test. Pattern already used by `test_ecr_image_retention.py`. |
| Operator reclaim script | Version-aware, default-dry-run `DeleteObjects` with `VersionId`. Never `aws s3 rm --recursive`. Never delete-marker-only deletes (those hide current keys but keep billed versions). | **New** script modeled on `infra/scripts/cleanup-s3-staging.sh` + ADR 0004. Not Terraform. Not ECS. |
| Canonical silver | Current `warehouse/silver/sec/silver.duckdb` and `shards/shard-{0-3}.duckdb`. Untouchable by reclaim. | Existing publish path (`stage_and_promote` / `merge_candidate_into_canonical`). |

## Recommended Project Structure

No new package, bucket module, or warehouse root. Touch only the prod storage lifecycle, a lock test, and an operator reclaim script.

```
infra/terraform/modules/storage_buckets/
  main.tf                          # MODIFY only if adding identity_refresh expire
                                   # already has warehouse/silverstage/ + warehouse/silver/
infra/terraform/accounts/prod/     # APPLY this root (module.storage)
  main.tf                          # UNCHANGED wiring: module "storage" { source = storage_buckets }

tests/architecture/
  test_warehouse_lifecycle_prefix.py   # NEW — join() key vs Terraform filter

infra/scripts/
  cleanup-s3-staging.sh            # EXISTING pattern (warehouse/_staging/ only) — do not reuse as-is
  reclaim-warehouse-duplicates.sh  # NEW — shards noncurrent + identity_refresh + gold keep-latest

edgar_warehouse/infrastructure/
  object_storage.py                # DO NOT CHANGE join()/write_staged_bytes for this milestone
  dataset_path_catalog.py          # DO NOT CHANGE gold.table.path / silver.shard.path
```

### Structure Rationale

- **`storage_buckets` (prod only):** Passive lifecycle lives here. `accounts/prod` already instantiates it. Dev uses `storage_buckets_destroyable`, which has **no warehouse lifecycle** — AWS-side dev is decommissioned; do not invent a second prod-like bucket to host rules.
- **`tests/architecture/`:** Repo convention for “this Terraform string must never regress.” A unit test of `join()` alone would not catch a Terraform prefix revert; a Terraform-only string test would not catch a future `join()` change. The regression must bind both.
- **`infra/scripts/`:** ADR 0004 already established one-time version-aware cleanup as an operator script with dry-run, confirm flag, VersionId batches, and evidence under `warehouse/release-evidence/`. Reclaim is the same class of work. Do not fold deletes into Terraform `null_resource` provisioners or a new Step Function.

## Architectural Patterns

### Pattern 1: Relative write path + rooted join = live S3 key

**What:** Callers pass a relative path (`silverstage/<uuid>/…`, `silver/sec/shards/shard-0.duckdb`, `gold/company/run_id=…`). `StorageLocation.join()` concatenates the storage root, which already ends in `/warehouse`. Lifecycle `filter.prefix` matches the **object key**, not the relative path.

**When to use:** Every standing S3 lifecycle rule and every reclaim prefix.

**Trade-offs:** One extra path segment (`warehouse/`) is easy to drop in Terraform. A filter of `silverstage/` is valid HCL and applies to nothing.

**Example:**

```python
from edgar_warehouse.infrastructure.object_storage import StorageLocation

root = StorageLocation("s3://edgartools-prod-warehouse-690839588395/warehouse")
staged = root.join("silverstage", "deadbeef", "silver/sec/silver.duckdb")
# s3://edgartools-prod-warehouse-690839588395/warehouse/silverstage/deadbeef/silver/sec/silver.duckdb
# key = warehouse/silverstage/deadbeef/silver/sec/silver.duckdb
```

Terraform must filter `warehouse/silverstage/`. AWS lifecycle prefix matching is a key-name prefix (`tax/` matches `tax/doc1.txt`) — not a suffix, not a relative-path match.

### Pattern 2: Standing lifecycle vs one-off VersionId delete

**What:** Lifecycle is the backstop for **continuous writers** whose keys will keep appearing. Operator `DeleteObjects` with `VersionId` is for **already-billed leftovers** that lifecycle has not aged out, or that lifecycle cannot express (keep-latest-per-table).

**When to use:**

| Object class | Why it exists | Standing owner | Immediate reclaim |
|--------------|---------------|----------------|-------------------|
| `warehouse/silverstage/<uuid>/…` | Unique keys; conflict path never deletes; success path does | Terraform current+noncurrent 3-day expire. Prefix **must** be `warehouse/silverstage/`. | Already done 2026-08-20 (2,011 versions / 1.71 TiB). Do not repeat unless apply reverts the prefix. |
| `warehouse/silver/sec/silver.duckdb` + `shards/shard-{0-3}.duckdb` | Same key overwritten on every promote → old bytes become **noncurrent versions** | Terraform `noncurrent_days = 7` on `warehouse/silver/`. **Do not add current `expiration`.** **Do not shorten 7 days in v1.0.** | Operator: delete **noncurrent** shard versions now (~315 GiB). Keep `IsLatest` current objects. |
| `warehouse/identity_refresh/runs/<run_id>/…` | New key per run (`reference_snapshot.duckdb`, `delta.duckdb`). Objects stay **current** forever | Optional but recommended Terraform current+noncurrent expire on `warehouse/identity_refresh/` (7 days). Without it, reclaim will rot. | Operator: delete historical run copies (~19 GiB). Skip in-flight `run_id`s. |
| `warehouse/gold/<table>/run_id=<id>/…` | New key per gold-refresh. Objects stay **current**. S3 cannot “keep latest run_id” | **Not Terraform.** A time-based expire would delete the live snapshot if gold-refresh pauses. | Operator: keep latest `run_id=` per table by `LastModified`; VersionId-delete the rest (~3.4 GiB). |

**Trade-offs:** Lifecycle is eventually consistent (daily evaluator) and prefix-dumb. Operator delete is immediate and can encode keep-latest / skip-current / skip-in-flight. Operator delete does not prevent the next gold-refresh from writing another `run_id=` copy.

### Pattern 3: Versioned-bucket reclaim (ADR 0004)

**What:** Bucket versioning is Enabled. A delete without `VersionId` writes a delete marker; previous versions remain billed. Freeing storage requires `s3api delete-objects` with `{Key, VersionId}` in batches of ≤1000 (this repo has already burned on combined Versions+DeleteMarkers > 1000 — cap each request at 1000 keys).

**When to use:** Every reclaim in this milestone.

**Trade-offs:** Dry-run + reviewed manifest + `--confirm-…` is slower than `aws s3 rm`. It is the only safe pattern next to canonical silver.

**Example:**

```bash
# dry-run: list-object-versions --prefix warehouse/silver/sec/shards/
# select Versions where IsLatest != true
# apply: delete-objects Objects=[{Key, VersionId}]  (batches of 100)
```

Never `aws s3 rm s3://bucket/warehouse/silver/ --recursive`.

### Pattern 4: Whole-lifecycle-document apply

**What:** `aws_s3_bucket_lifecycle_configuration.warehouse` is a single Terraform resource. Plan/apply sends the **full** rule set. Live prod already has `warehouse/silverstage/` (corrected 2026-08-20). An apply from a branch that still says `prefix = "silverstage/"` restores the leak. An apply that omits `expire-noncurrent-silver-canonical-versions` drops the 7-day silver backstop.

**When to use:** The leak-seal apply. Review `terraform plan` for this resource only: both rule IDs present, staging prefix `warehouse/silverstage/`, silver rule has **no** current `expiration` block.

**Trade-offs:** Cannot “patch one prefix” out of band and expect Terraform to leave the rest alone.

## Data Flow

### Request Flow

```
Warehouse command (ECS)
    ↓
relative path (silverstage/…, silver/sec/…, gold/…, identity_refresh/…)
    ↓
StorageLocation.join(WAREHOUSE_STORAGE_ROOT, relative)
    ↓
PutObject Key=warehouse/<relative>   (versioned)
    ↓
Standing lifecycle (Terraform prefixes) ──or── leftover billed versions
    ↓
v1.0: Terraform apply (future objects) + operator VersionId delete (existing duplicates)
```

### State Management

Not a UI state store. The durable state is S3 object versions:

```
PutObject on existing key
    ↓
previous current → noncurrent (still billed)
new current → IsLatest=true

PutObject on unique key (silverstage uuid, gold run_id, identity run_id)
    ↓
new current object (never becomes noncurrent unless overwritten or expired)
```

That split is why silver shards need **noncurrent** expiration, while silverstage / identity / gold need **current** expiration or an operator keep-latest pass.

### Key Data Flows

1. **Silverstage leak-seal:** `write_staged_bytes` → unique `warehouse/silverstage/<uuid>/…` → on conflict, object remains → lifecycle 3-day expire **iff** filter is `warehouse/silverstage/` → regression test locks that iff.
2. **Canonical silver publish:** merge → `stage_and_promote` onto `silver/sec/silver.duckdb` or `silver/sec/shards/shard-N.duckdb` → prior version becomes noncurrent → 7-day rule eventually deletes it → v1.0 operator deletes noncurrent **now** without touching `IsLatest`.
3. **Identity refresh snapshots:** reducer writes `identity_refresh/runs/<run_id>/reference/reference_snapshot.duckdb` and per-batch `delta.duckdb` via the same `storage_root`. Canonical company identity still lands on silver via `stage_and_promote`. The run prefix is debug, not canonical. Reclaim the run prefix; do not reclaim the silver keys it promoted into.
4. **Warehouse gold copies:** `gold_table_output` → relative `gold/{table}/run_id={run_id}/{table}.parquet` → `storage_root.join` → `warehouse/gold/…`. Snowflake serving export is a **different bucket** (`edgartools-prod-snowflake-export-…`, 30-day expire). Do not reclaim or retarget that bucket. Keep the latest warehouse `run_id=` per table so a local/warehouse reader still has one snapshot.

## Scaling Considerations

This is storage-cost scaling, not user-count scaling.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Current prod (one warehouse bucket, versioning on) | Prefix-correct lifecycle + one-off VersionId reclaim. No new buckets. |
| Recurring gold-refresh / identity-refresh | Unique `run_id=` keys reaccumulate as **current** objects. Identity: add Terraform expire. Gold: accept slow growth or a later writer change to `gold/<table>/latest.parquet` (out of v1.0). |
| Shard publish at Map concurrency | More noncurrent versions on the same four shard keys. 7-day rule is the standing cap; immediate reclaim is a one-time catch-up. Do not raise Map concurrency to “clean storage.” |

### Scaling Priorities

1. **First bottleneck:** Wrong lifecycle prefix → unbounded current objects (already hit: 1.70 TiB silverstage). Fix: join()-keyed regression + apply that cannot restore `silverstage/`.
2. **Second bottleneck:** Versioned overwrites without noncurrent expire (shards / `silver.duckdb`). Already has 7-day rule; v1.0 only accelerates deletion of already-superseded versions.
3. **Third bottleneck:** Unique-key historical copies (identity, gold) that never become noncurrent. Lifecycle prefix expire or keep-latest operator logic — not a new root.

## Anti-Patterns

### Anti-Pattern 1: Lifecycle filter uses the relative path

**What people do:** Set `prefix = "silverstage/"` because `write_staged_bytes` returns that relative path. Comment in `identity_refresh_publication.py` still says “lifecycle rule on silverstage/.”

**Why it's wrong:** Live keys are `warehouse/silverstage/…`. AWS matches key prefix. The rule silently matches zero objects.

**Do this instead:** Derive the filter from `StorageLocation.join()` and assert it in CI. Filter = `warehouse/silverstage/`.

### Anti-Pattern 2: New bucket or second warehouse root

**What people do:** Create `edgartools-prod-warehouse-staging` or set `WAREHOUSE_STORAGE_ROOT` to the bucket root so relative `silverstage/` matches a naive filter.

**Why it's wrong:** Splits canonical silver, IAM, and Snowflake-adjacent paths. Out of scope and forbidden by this milestone's quality gate.

**Do this instead:** Keep `s3://edgartools-prod-warehouse-690839588395/warehouse` and put `warehouse/` in the lifecycle prefix.

### Anti-Pattern 3: Terraform `aws s3 rm` / provisioner reclaim

**What people do:** Put deletes in Terraform apply so “infra owns cleanup.”

**Why it's wrong:** Passive AWS Terraform must not encode workload commands or one-off data destruction. Apply is the wrong control plane for “keep latest gold run_id” and for “do not delete current shards.” A destroy/recreate of the lifecycle resource must not imply object deletion.

**Do this instead:** Terraform owns standing rules only. Operator script owns VersionId deletes.

### Anti-Pattern 4: Delete without VersionId, or recursive prefix delete on `warehouse/silver/`

**What people do:** `aws s3 rm` the shard prefix, or `delete_object` without VersionId.

**Why it's wrong:** Delete markers hide current keys while leaving noncurrent versions billed. Recursive prefix delete can remove **current** `shard-0`…`shard-3` and `silver.duckdb`.

**Do this instead:** List versions, select `IsLatest != true` (shards) or non-latest `run_id=` (gold), delete exact VersionIds. Post-check that current canonical keys still `HeadObject`.

### Anti-Pattern 5: Current-object expiration on `warehouse/silver/`

**What people do:** Add `expiration { days = N }` to `expire-noncurrent-silver-canonical-versions` to “clean faster.”

**Why it's wrong:** On a quiet day that expires the only live canonical copy.

**Do this instead:** Noncurrent-only standing rule (keep 7 days). Immediate noncurrent reclaim is the operator script.

### Anti-Pattern 6: Time-based expire on `warehouse/gold/` to replace keep-latest

**What people do:** 30-day expire on the gold prefix because snowflake-export already has one.

**Why it's wrong:** Warehouse gold keys are unique per `run_id`. Expire deletes the latest snapshot if `gold-refresh` does not run inside the window. Snowflake-export is a different bucket with a different consumer (native pull).

**Do this instead:** Operator keep-latest per table. Leave warehouse gold lifecycle unset in v1.0.

### Anti-Pattern 7: Apply lifecycle from a stale branch after a live prefix fix

**What people do:** Live `put-bucket-lifecycle-configuration` already says `warehouse/silverstage/`; an older Terraform still says `silverstage/`; apply “to sync state.”

**Why it's wrong:** The resource replaces the whole document and reopens the leak.

**Do this instead:** CI regression must fail on `prefix = "silverstage/"`. Plan must show staging prefix `warehouse/silverstage/` **before** apply.

## Integration Points

### New vs modified vs do-not-touch

| Item | Change type | Notes |
|------|-------------|-------|
| `storage_buckets` warehouse lifecycle prefixes | Modified (source already corrected on `claude/silverstage-lifecycle`); **apply is still outstanding** | Must not restore `silverstage/`. Optional additive rule: expire `warehouse/identity_refresh/`. |
| `accounts/prod` Terraform root | Unchanged wiring; **operator apply** | Passive storage module only. |
| `tests/architecture/test_warehouse_lifecycle_prefix.py` | **New** | Bind join() live key to Terraform filter. |
| `infra/scripts/reclaim-warehouse-duplicates.sh` | **New** | Three selectors, one bucket, VersionId deletes. |
| `object_storage.py` / path catalog / orchestrator | Do not touch | Relative paths and join() are the contract the test locks. |
| Bronze bucket, tfstate, snowflake-export bucket, ECR | Do not touch | Explicit out of scope. |
| 7-day silver noncurrent days | Do not change | Reclaim already-superseded versions; do not shorten the standing rule. |

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| S3 warehouse bucket `edgartools-prod-warehouse-690839588395` | Lifecycle API via Terraform; `list-object-versions` + `delete-objects` via operator CLI | Account `690839588395` only. Versioning on. Prefix filters are key prefixes. |
| S3 bronze / snowflake-export / tfstate | None | Wrong buckets. |
| ECS / Step Functions | Evidence only (record running tasks, do not block solely because something is running — same as ADR 0004) | Skip identity `run_id`s that are in-flight. Do not add a reclaim state machine. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Runtime adapter ↔ Terraform lifecycle | Shared string contract: live key prefix `warehouse/silverstage/` | Enforced by architecture test, not by importing HCL into Python at runtime. |
| Canonical silver ↔ reclaim script | Reclaim may list `warehouse/silver/sec/shards/` but may only delete noncurrent versions | Current keys are a hard deny-list: `silver.duckdb`, `shard-0`…`shard-3` `IsLatest`. |
| Identity refresh run prefix ↔ silver promote | Run snapshots are not canonical. Promote target is silver. | Deleting `warehouse/identity_refresh/` does not delete promoted silver. |
| Warehouse gold ↔ Snowflake export | Separate roots (`WAREHOUSE_STORAGE_ROOT` vs `SERVING_EXPORT_ROOT`) | Keep-latest applies only under `warehouse/gold/`. |
| `delete_object` (runtime) ↔ lifecycle | Runtime deletes current key only (no VersionId) on **successful** promote | Conflict leftovers and old versions are lifecycle/operator concerns. Do not “fix” `delete_object` to purge all versions in this milestone. |

### Ownership matrix (Terraform vs operator vs test)

| Work item | Owner | Why |
|-----------|-------|-----|
| Keep `expire-silver-staging-candidates` on `warehouse/silverstage/` | Terraform apply | Standing backstop for unique staging keys. |
| Keep `expire-noncurrent-silver-canonical-versions` on `warehouse/silver/` at 7 days, no current expiration | Terraform apply (no days change) | Standing cap on overwrite versions. |
| Optional: expire `warehouse/identity_refresh/` at 7 days current+noncurrent | Terraform (recommended additive rule) | Unique per-run keys will otherwise reaccumulate after reclaim. |
| Join() key matches lifecycle filter | Regression test | Prevents the original silent mismatch and an apply revert. |
| ~315 GiB noncurrent `shard-*.duckdb` | Operator VersionId delete | 7-day rule will get there eventually; v1.0 wants the bytes gone now. Current shards stay. |
| ~19 GiB identity-refresh snapshots | Operator VersionId delete | Historical current objects; lifecycle cannot distinguish in-flight vs done unless aged. |
| ~3.4 GiB historical gold `run_id=` | Operator keep-latest VersionId delete | S3 lifecycle cannot “keep latest run per table.” |
| Bronze, tfstate, current canonical silver, latest gold run per table | Deny-list | Safety. |

## Suggested Build Order

Dependencies run left-to-right. Do not reclaim until the leak cannot be reopened by the next apply.

```
1. Regression test
   tests/architecture/test_warehouse_lifecycle_prefix.py
   - Parse storage_buckets warehouse lifecycle HCL
   - Assert rule expire-silver-staging-candidates filter.prefix == "warehouse/silverstage/"
   - Assert rule expire-noncurrent-silver-canonical-versions filter.prefix == "warehouse/silver/"
   - Assert that rule has noncurrent_version_expiration and NO expiration block
   - Construct StorageLocation(WAREHOUSE-shaped root).join("silverstage", token, "silver/sec/silver.duckdb")
   - Assert object key startswith warehouse/silverstage/
   - Assert Terraform prefix is a prefix of that key
   - Assert prefix "silverstage/" is NOT used as the staging filter
   Why first: makes a bad apply unmergeable.

2. Terraform plan + apply (prod storage root only)
   infra/terraform/accounts/prod
   - Plan the lifecycle resource: both rules, correct prefixes
   - Apply so state matches live (live already corrected; apply must not revert)
   - Optional same apply: add warehouse/identity_refresh/ expire (if accepted)
   Why second: seal the leak before deleting leftovers, so writers cannot refill silverstage unmatched.

3. Operator dry-run inventories (no deletes)
   Three selectors against the same bucket:
   a) warehouse/silver/sec/shards/  — Versions where IsLatest is false
      deny: IsLatest shard-0..3, silver.duckdb any version until classified
   b) warehouse/identity_refresh/   — all versions except in-flight run_id
   c) warehouse/gold/               — group by table; keep latest run_id= by LastModified
   Write evidence under warehouse/release-evidence/duplicate-reclaim/ (or local + copy).
   Why third: reviewed manifests, like ADR 0004.

4. Reclaim shards (safest)
   VersionId delete noncurrent shard versions only.
   Post-check HeadObject on current shard-0..3 and silver.duckdb.
   Why fourth: same keys, IsLatest is an explicit keep bit; smallest chance of wrong-prefix delete.

5. Reclaim identity-refresh
   VersionId delete historical run copies.
   Post-check no leftover large duckdb under the prefix except skipped in-flight runs.
   Why fifth: whole prefix is non-canonical, but in-flight reducers still read it.

6. Reclaim gold historical run_id=
   Keep latest run per table; VersionId-delete the rest.
   Post-check each table still has exactly one current parquet (or one latest run prefix).
   Why last: keep-latest logic is the easy place to delete the live snapshot if grouping is wrong.

7. Post-milestone verification
   - get-bucket-lifecycle-configuration prefixes still warehouse/silverstage/ and warehouse/silver/
   - architecture tests green
   - canonical silver current keys exist
   - bronze and tfstate prefixes untouched
```

### Phase mapping for the roadmap

1. **Seal** — test + Terraform apply (items 1–2). Addresses leak. Avoids reclaiming into a still-wrong filter.
2. **Reclaim shards** — item 4. Addresses 315 GiB. Avoids current-silver expiration.
3. **Reclaim identity + gold** — items 5–6. Addresses remaining current-object duplicates. Avoids Terraform keep-latest fiction.

## Sources

- Repo: `edgar_warehouse/infrastructure/object_storage.py` (`join`, `write_staged_bytes`, `promote_staged`, `delete_object`)
- Repo: `infra/terraform/modules/storage_buckets/main.tf` (`aws_s3_bucket_lifecycle_configuration.warehouse`)
- Repo: `infra/terraform/accounts/prod/main.tf` (`module "storage"`)
- Repo: `edgar_warehouse/config/warehouse_paths.properties` (`silver.shard.path`, `gold.table.path`)
- Repo: `edgar_warehouse/application/identity_refresh_publication.py` (`identity_refresh/runs` snapshots + stage/promote to silver)
- Repo: `edgar_warehouse/serving/source_dimensional_export.py` (`gold_table_output` → warehouse gold parquet)
- Repo: `infra/scripts/cleanup-s3-staging.sh` and `docs/adr/0004-one-time-version-aware-staging-cleanup.md` (VersionId, dry-run, evidence)
- Repo: `tests/architecture/test_ecr_image_retention.py` (Terraform-string architecture lock)
- Workstream: `.planning/workstreams/s3-silverstage-lifecycle/PROJECT.md`
- AWS: [S3 Lifecycle configuration examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-configuration-examples.html) — filter `Prefix` is a **key name prefix**; versioned buckets need `Expiration` for current objects and `NoncurrentVersionExpiration` for superseded versions; delete without VersionId creates a delete marker rather than freeing storage

---
*Architecture research for: warehouse S3 lifecycle prefix correctness and duplicate-object reclaim*
*Researched: 2026-08-20*
