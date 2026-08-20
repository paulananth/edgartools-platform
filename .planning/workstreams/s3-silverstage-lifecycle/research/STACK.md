# Stack Research

**Domain:** AWS S3 lifecycle prefix seal + versioned duplicate reclaim
**Researched:** 2026-08-20
**Confidence:** HIGH

## Recommended Stack

No new platforms, storage backends, or runtime libraries. Seal the leak with the existing prod Terraform module; reclaim duplicates with the same AWS CLI + `uv` Python pattern already used by `infra/scripts/cleanup-s3-staging.sh` and `infra/scripts/delete-bronze-historic-manifest.sh`.

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Terraform | `>= 1.14.7` (prod root pin) | Apply `expire-silver-staging-candidates` so it cannot revert to `silverstage/` | Passive AWS infra already lives in `infra/terraform/accounts/prod`; this is the only durable way to keep the live lifecycle filter on `warehouse/silverstage/` |
| hashicorp/aws | `= 6.39.0` | `aws_s3_bucket_lifecycle_configuration.warehouse` | Exact pin in `infra/terraform/accounts/prod/versions.tf`. Provider docs require `rule.filter.prefix` (not the deprecated `rule.prefix`) and allow one lifecycle resource per bucket |
| Amazon S3 versioning + Lifecycle | current AWS API | 3-day current+noncurrent expiry on staging; 7-day noncurrent-only on canonical silver | Prefix filters are **key-prefix matches**, not path-suffix matches. `filter { prefix = "silverstage/" }` never sees `warehouse/silverstage/...`. Do not add `expiration` on `warehouse/silver/` |
| AWS CLI v2 `s3api` | CLI 2.x (`delete-objects` docs currently 2.36.28) | List versions and permanently delete by `VersionId` | Versioned deletes reclaim billed bytes. Key-only deletes create delete markers and **leave** noncurrent data billed. Same APIs the 2026-08-20 silverstage delete already used |
| Python stdlib via `uv run --no-project python` | CPython `>=3.11` (project requires-python) | Manifest selection, keep-sets, 100-object delete batches | Existing reclaim scripts already do this. No extra PyPI package is needed for JSON/TSV/batching |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `edgar_warehouse.infrastructure.object_storage.StorageLocation` | in-repo | `join()` + `write_staged_bytes` key contract | Regression: prove Terraform prefix equals the S3 key after `WAREHOUSE_STORAGE_ROOT` (`.../warehouse`) is prefixed |
| pytest | `>=9.0.3` (dev extra; lockfile present) | Architecture regression next to `tests/architecture/test_ecr_image_retention.py` | Static test: parse `storage_buckets/main.tf` + call `StorageLocation.join()`. No live AWS |
| boto3 | `1.42.91` (uv.lock, `--extra s3`) | Already used by `StorageLocation._s3()` | Unit tests that stub `boto3.client`. **Do not** add a boto3 operator reclaim tool; AWS CLI is the operator surface |
| `warehouse_paths.properties` | packaged config | Gold path template `gold/{table_name}/run_id={run_id}/{document_name}` | Gold keep-latest grouping. Identity-refresh snapshots are **not** in this file; they are `identity_refresh/runs/{run_id}/...` in `identity_refresh_publication.py` |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `terraform plan` / `apply` in `infra/terraform/accounts/prod` | Seal lifecycle in state | Profile: `aws-admin-prod` (provisioning Terraform, not `sec_platform_deployer`). Narrow target: `module.storage.aws_s3_bucket_lifecycle_configuration.warehouse`. Reject any plan that sets prefix back to `silverstage/` |
| `aws s3api get-bucket-lifecycle-configuration` | Post-apply live check | Bucket `edgartools-prod-warehouse-690839588395`. Rule `expire-silver-staging-candidates` must show `Prefix=warehouse/silverstage/` |
| `aws s3api list-object-versions --prefix ...` | Inventory before delete | Paginate. Default page is 1,000 **keys**, and a page can include up to 1,000 Versions **plus** 1,000 DeleteMarkers. Do not dump one unpaginated JSON like `cleanup-s3-staging.sh` currently does |
| `aws s3api delete-objects --delete file://batch.json` | Permanent version delete | Hard cap **1,000** objects/request (AWS API). This repo already batches **100** in staging/bronze cleanup scripts — keep 100. Every object **must** include `VersionId` |
| `uv run pytest tests/architecture` | Regression | Fast, no AWS. Pair with `uv run pytest tests/unit/test_object_storage_conditional_promotion.py` if join/staging tests change |
| Existing script pattern in `infra/scripts/cleanup-s3-staging.sh` | Dry-run → reviewed TSV → `--apply` + confirm flag | Copy the safety contract, **do not** reuse that script (it is hardcoded to `warehouse/_staging/`) |

## Installation

No new packages. Operator workstation already has Terraform, AWS CLI v2, and `uv`.

```bash
# Tests only (regression)
uv sync --extra s3
uv run pytest tests/architecture tests/unit/test_object_storage_conditional_promotion.py

# Prod Terraform seal (admin profile, prod root only)
export AWS_PROFILE=aws-admin-prod
export AWS_DEFAULT_REGION=us-east-1
cd infra/terraform/accounts/prod
terraform init -backend-config=backend.hcl
terraform plan -target=module.storage.aws_s3_bucket_lifecycle_configuration.warehouse
# apply only if Prefix stays warehouse/silverstage/ and the 7-day silver noncurrent rule is unchanged

# Live lifecycle readback
aws s3api get-bucket-lifecycle-configuration \
  --bucket edgartools-prod-warehouse-690839588395 \
  --query "Rules[?ID=='expire-silver-staging-candidates']"
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Terraform apply of existing `storage_buckets` lifecycle | Out-of-band `put-bucket-lifecycle-configuration` | Never for the seal. Live prefix is already correct; CLI-only edits are what drifted Terraform last time |
| AWS CLI `delete-objects` with `VersionId` | Lifecycle-only wait on the 7-day `expire-noncurrent-silver-canonical-versions` rule | Acceptable later for *future* shard versions. This milestone must reclaim ~315 GiB **now** without shortening the 7-day standing rule |
| Keep-latest gold by current-version `LastModified` per table prefix | Expire all of `warehouse/gold/` via lifecycle | Lifecycle cannot express “keep newest `run_id=` per table”. Default `run_id` is `uuid.uuid4()` (`_resolve_run_id`), so lexicographic run_id order is wrong |
| New `infra/scripts/` reclaim script modeled on staging cleanup | S3 Batch Operations + Inventory | Batch Jobs need extra IAM roles, a manifest bucket, and days of inventory lag. Volume here is hundreds of GiB across known prefixes, not billions of keys |
| `uv run --no-project python` for keep-set logic | New boto3 CLI package in `edgar_warehouse` | Reclaim is a one-shot operator action, not warehouse runtime. Keep it out of ECS images |
| Architecture pytest on Terraform source + `StorageLocation.join()` | Live moto/S3 integration test | Join/prefix mismatch is a static contract. Live AWS is the apply/readback gate, not CI |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Non-AWS storage, registries, or workflow engines | Agents.md: keep the AWS path only | Existing S3 + Terraform + AWS CLI |
| `aws s3 rm --recursive` / key-only `delete-object` | On a versioned bucket this writes **delete markers**; noncurrent bytes stay billed. Confirmed by AWS DeleteObjects docs and this repo’s teardown 5-whys | `delete-objects` with explicit `VersionId` |
| `aws s3api delete-objects` batches > 1000 | API hard limit; combined Versions+DeleteMarkers on one list page can exceed 1000 (`destroy-aws-complete.sh` 5-whys) | Batch 100 like existing cleanup scripts; cap any emergency path at 1000 |
| Lifecycle `expiration` on `warehouse/silver/` | Would delete **current** `silver.duckdb` and `shard-{0-3}.duckdb` on a quiet day | Keep `noncurrent_version_expiration { noncurrent_days = 7 }` only; operator-delete noncurrent shard versions |
| Changing the 7-day canonical-silver noncurrent policy | Explicitly out of scope | Immediate VersionId reclaim of already-superseded shard versions |
| Prefix `silverstage/` (bucket-root) | Matches nothing; that leak produced 1.70 TiB | `warehouse/silverstage/` |
| Terraform in `storage_buckets_destroyable` or Snowflake/access roots | Prod warehouse uses `module.storage` → `storage_buckets`. Destroyable module has **no** warehouse lifecycle. Dev AWS/Snowflake is decommissioned | `infra/terraform/accounts/prod` only |
| Image digests, ECS task defs, secrets in Terraform | Passive-infra rule | Operator deploy scripts stay out of this work |
| S3 Glacier / Intelligent-Tiering transitions | Not reclaim; 128 KB transition default; retrieval cost; DuckDB files need immediate delete | Version delete |
| rclone, aws-nuke, s3-pit-restore, new MDM/Snowflake tools | Extra blast radius; wrong layer | AWS CLI + Terraform |
| `cleanup-s3-staging.sh` as-is | Hardcoded `warehouse/_staging/`; one-shot unpaginated `list-object-versions` | New script with paginated listing and per-class keep-sets |

## Stack Patterns by Variant

**If sealing the lifecycle (must happen first):**
- Use Terraform `hashicorp/aws` 6.39.0 `filter { prefix = "warehouse/silverstage/" }` on rule `expire-silver-staging-candidates`.
- Because live S3 was already patched; only Terraform state can stop the next apply from restoring `silverstage/`.
- After apply, `get-bucket-lifecycle-configuration` is the source of truth, not `terraform plan` alone (lifecycle can take time to propagate).

**If adding the join/prefix regression:**
- Use pytest that (1) extracts the Terraform prefix string, (2) builds `StorageLocation("s3://edgartools-prod-warehouse-690839588395/warehouse").join("silverstage", "<uuid>", "silver/sec/silver.duckdb")`, (3) asserts the object key after the bucket is `warehouse/silverstage/...` and **starts with** that prefix.
- Because `write_staged_bytes` writes relative `silverstage/<uuid>/...` and `join()` prefixes `WAREHOUSE_STORAGE_ROOT` which already ends in `/warehouse`. Tests that only check the relative path will re-introduce the leak.

**If reclaiming noncurrent shards (~315 GiB):**
- List `warehouse/silver/sec/shards/` versions; delete only `IsLatest=false` for `shard-0.duckdb`…`shard-3.duckdb`.
- Never select `warehouse/silver/sec/silver.duckdb` current or noncurrent in this pass unless a reviewed manifest says so (canonical current keys are out of scope; silver.duckdb noncurrent is already covered by the 7-day rule).
- Because current shard objects are canonical silver.

**If reclaiming identity-refresh snapshots (~19 GiB):**
- Prefix `warehouse/identity_refresh/runs/` from `_RUN_PREFIX = "identity_refresh/runs"` plus `join()`.
- Target `reference/reference_snapshot.duckdb` and `batches/*/delta.duckdb` (and their noncurrent versions). These are per-run debug snapshots, not canonical silver.
- Keep-set: do not touch `warehouse/silver/sec/...`. Optionally keep the newest run’s current objects if an identity-refresh Map is live; default decision is delete historical run copies.

**If reclaiming historical gold `run_id=` copies (~3.4 GiB):**
- Prefix `warehouse/gold/`. Group current versions by table directory, parse `run_id=` from the key, keep **all current versions** of the newest run per table (newest = max `LastModified` among that table’s current objects).
- Delete every version of older `run_id=` prefixes for that table, including noncurrent versions of the kept run if any exist.
- Because `run_id` defaults to a UUID, “latest” is time, not sort order.

**If a listing is truncated:**
- Follow `IsTruncated` / `NextKeyMarker` / `NextVersionIdMarker` (CLI pagination). Do not use `--no-paginate`.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| Terraform `>= 1.14.7` | hashicorp/aws `6.39.0` | Prod root exact provider pin. S3 backend uses `use_lockfile = true` (no DynamoDB) |
| hashicorp/aws 6.39.0 `filter.prefix` | S3 Lifecycle Prefix element | Same semantics: objects whose **key starts with** the prefix. Must include the `warehouse/` storage-root segment |
| AWS CLI v2 `delete-objects` | S3 DeleteObjects (max 1000 keys) | Include `VersionId` or the call is a current-version delete marker |
| `StorageLocation.join` | `WAREHOUSE_STORAGE_ROOT=s3://…/warehouse` | `root.rstrip("/") + "/" + relative`. Relative `silverstage/...` → key `warehouse/silverstage/...` |
| pytest `>=9.0.3` | Python `>=3.11` | Architecture tests are stdlib + in-repo modules |
| boto3 `1.42.91` | botocore from the same lock | Runtime only; not required for the reclaim script |
| Existing 3-day staging rule + 7-day silver noncurrent rule | One `aws_s3_bucket_lifecycle_configuration` per bucket | Do not add a second lifecycle resource on the warehouse bucket (provider perpetual-diff warning) |

## Integration Points

| Capability | Integration | Do not change |
|------------|-------------|---------------|
| Lifecycle seal | `infra/terraform/modules/storage_buckets/main.tf` resource `aws_s3_bucket_lifecycle_configuration.warehouse`; consumed only by `infra/terraform/accounts/prod` | `storage_buckets_destroyable`, snowflake-export 30-day rule, bronze bucket |
| Key contract | `StorageLocation.write_staged_bytes` → `silverstage/{uuid}/{canonical}`; `promote_staged` leaves staging objects on `PromotionConflictError` | Promotion conflict semantics; 3-day expiry is the backstop |
| Canonical keep-set | `warehouse/silver/sec/silver.duckdb`, `warehouse/silver/sec/shards/shard-{0,1,2,3}.duckdb` | Bronze filings, tfstate, ECR |
| Identity-refresh paths | `edgar_warehouse/application/identity_refresh_publication.py` `_RUN_PREFIX` | Lease objects under `reference/identity_refresh_lease/` unless a reviewed manifest includes them |
| Gold paths | `gold.table.path = gold/{table_name}/run_id={run_id}/{document_name}` | Snowflake export bucket (`edgartools-prod-snowflake-export-*`) — different bucket, 30-day lifecycle already |

## Sources

- hashicorp/aws v6.39.0 `aws_s3_bucket_lifecycle_configuration` docs — filter prefix vs deprecated `rule.prefix`; one lifecycle resource per bucket; `noncurrent_version_expiration` — HIGH
- [S3 Lifecycle configuration examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-configuration-examples.html) — prefix `tax/` matches `tax/doc1.txt`; versioned buckets need `NoncurrentVersionExpiration` to remove old versions without deleting current — HIGH
- [DeleteObjects API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteObjects.html) and [AWS CLI `delete-objects`](https://docs.aws.amazon.com/cli/latest/reference/s3api/delete-objects.html) (CLI 2.36.28) — max 1000 keys; VersionId permanently deletes; omitting VersionId inserts a delete marker — HIGH
- [ListObjectVersions API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectVersions.html) — `prefix`, `IsLatest`, `IsTruncated`, `NextKeyMarker`/`NextVersionIdMarker`; default 1000 keys — HIGH
- In-repo: `infra/terraform/modules/storage_buckets/main.tf`, `infra/terraform/accounts/prod/versions.tf`, `edgar_warehouse/infrastructure/object_storage.py`, `infra/scripts/cleanup-s3-staging.sh`, `infra/scripts/destroy-aws-complete.sh` (1000-key combined-page cap) — HIGH
- Gold `run_id` is UUID unless passed in (`warehouse_orchestrator._resolve_run_id`) — HIGH for code, MEDIUM for live gold key inventory until the reclaim dry-run lists prefixes

---
*Stack research for: warehouse S3 lifecycle prefix correctness and duplicate-object reclaim*
*Researched: 2026-08-20*
