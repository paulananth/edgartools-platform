# Project Research Summary

**Project:** Warehouse S3 duplicate-storage reclaim (`s3-silverstage-lifecycle`)
**Domain:** Operator storage hygiene on an existing versioned AWS warehouse bucket (not a greenfield product)
**Researched:** 2026-08-20
**Confidence:** HIGH

## Executive Summary

This is a one-shot operator milestone on the live prod warehouse bucket `edgartools-prod-warehouse-690839588395` (account `690839588395`). Canonical current silver stays; the work is (1) lock the silverstage lifecycle filter onto the **joined live key** `warehouse/silverstage/` so the next Terraform apply cannot restore the silent no-op prefix `silverstage/`, and (2) permanently delete already-billed duplicate DuckDB/parquet versions that lifecycle has not aged out. Live prefix and the 1.71 TiB silverstage orphan delete are already done; Terraform apply of that prefix is not. Remaining inventory (workstream figures, not re-listed in this pass): ~315 GiB noncurrent shards, ~19 GiB identity-refresh run snapshots, ~3.4 GiB historical gold `run_id=` copies.

Experts do this with two control planes, not one: Terraform owns **standing** prefix-correct lifecycle (one `aws_s3_bucket_lifecycle_configuration` per bucket — apply replaces the whole document); an operator script owns **existing** VersionId deletes. Copy the safety contract from `cleanup-s3-staging.sh` (dry-run TSV → reviewed manifest → `--apply` + distinct confirm flag → post `list-object-versions`). Do **not** reuse that script: it deletes `IsLatest=true` under `warehouse/_staging/`. Do not add platforms, buckets, ECS reclaim tasks, boto3 CLIs, Glacier, or `aws s3 rm`.

The main risks are a reverted lifecycle prefix (reopens the 1.7 TiB leak), delete-marker-only “cleanup” that leaves billed bytes, and wiping current `silver.duckdb` / `shard-{0-3}.duckdb`. Mitigate in that order: branch-hygiene so MDM WIP is not in the PR, CI that binds `StorageLocation.join()` to the Terraform filter, plan-gated apply, then reclaim shards (noncurrent only) before identity-refresh and gold keep-latest. Never add `expiration` on `warehouse/silver/`; never shorten the 7-day noncurrent rule in v1.0.

## Key Findings

### Recommended Stack

No new packages or runtimes. Seal with the existing prod Terraform module; reclaim with AWS CLI v2 `s3api` plus `uv run --no-project python` for keep-set / TSV / 100-object batches — the same pattern as `infra/scripts/cleanup-s3-staging.sh` and `delete-bronze-historic-manifest.sh`. See [STACK.md](STACK.md).

**Core technologies:**
- Terraform `>= 1.14.7` (prod root pin): apply `module.storage.aws_s3_bucket_lifecycle_configuration.warehouse` so the live prefix cannot revert — only durable seal
- hashicorp/aws `= 6.39.0`: `rule.filter.prefix` (not deprecated `rule.prefix`); **one** lifecycle resource per bucket
- S3 versioning + Lifecycle: 3-day current+noncurrent on `warehouse/silverstage/`; 7-day **noncurrent-only** on `warehouse/silver/` — prefix is a key-name prefix, not a path suffix
- AWS CLI v2 `s3api` (`list-object-versions`, `delete-objects` with `VersionId`): only path that frees billed bytes; omit VersionId → delete marker
- CPython `>=3.11` via `uv`: manifest selection, gold keep-latest, batch JSON — no extra PyPI; do **not** add a boto3 operator tool

**Critical version / API constraints:** `delete-objects` hard-cap 1,000 keys; this repo batches 100. One `list-object-versions` page can return 1,000 Versions **plus** 1,000 DeleteMarkers. Paginate on `KeyMarker` / `VersionIdMarker`. Profile for apply: `aws-admin-prod`, not `sec_platform_deployer`. Root: `infra/terraform/accounts/prod` only — never `storage_buckets_destroyable`.

### Expected Features

Operator contracts, not end-user product. See [FEATURES.md](FEATURES.md).

**Must have (table stakes):**
- Prod Terraform apply of `expire-silver-staging-candidates` on `warehouse/silverstage/` — live is already correct; unapplied source is how it reverts
- Architecture regression: Terraform filter is a prefix of `StorageLocation.join("silverstage", …)` live keys; negative case `silverstage/` must not match
- Immediate VersionId reclaim of noncurrent `warehouse/silver/sec/shards/shard-*.duckdb` (~315 GiB) — keep current shards + `silver.duckdb`
- Identity-refresh historical snapshot reclaim (~19 GiB) — unique current keys under `warehouse/identity_refresh/runs/{run_id}/`; 7-day silver noncurrent rule will never touch them
- Historical gold `run_id=` reclaim (~3.4 GiB) — keep latest **current** object per table by `LastModified` (UUID run_id is not chronological)
- Versioned `DeleteObjects` (`Key` + `VersionId`), dry-run → reviewed TSV → `--apply` + distinct confirm flags, post-list proof, fail-closed current-silver / latest-gold allowlist, batches of 100

**Should have (differentiators):**
- Join()-derived test, not Terraform-string-only
- Terraform plan gate: abort if prefix changes away from `warehouse/silverstage/` or if `expire-noncurrent-silver-canonical-versions` is destroyed
- Bytes-reclaimed evidence (count + GiB per prefix); idempotent empty second run = success
- Optional additive Terraform expire on `warehouse/identity_refresh/` (7-day current+noncurrent) so unique run keys do not reaccumulate — P2 if not in the same apply

**Defer (v2+):**
- Recurring lifecycle on gold (cannot express keep-latest; a pause would expire the live snapshot)
- Keep-N gold runs; noncurrent `silver.duckdb` one-shot unless inventory still shows material GiB
- Version-aware `ObjectStorage.delete_object`; CloudWatch cost alarms; 7-day policy change; bronze / tfstate / snowflake-export / ECR reclaim

### Architecture Approach

Do not add a bucket, a second `WAREHOUSE_STORAGE_ROOT`, a runtime cleanup ECS task, or Terraform provisioner deletes. Plug leak-seal and reclaim into the existing layout: `WAREHOUSE_STORAGE_ROOT` already ends in `/warehouse`; `join()` makes live keys `warehouse/<relative>`. Lifecycle filters and reclaim prefixes must use that joined key. See [ARCHITECTURE.md](ARCHITECTURE.md).

**Major components:**
1. `StorageLocation.join()` / `write_staged_bytes` — unchanged live-key contract; relative `silverstage/<uuid>/…` → `warehouse/silverstage/…`
2. `aws_s3_bucket_lifecycle_configuration.warehouse` — standing backstop; whole document replaced on apply
3. `tests/architecture/test_warehouse_lifecycle_prefix.py` — new; bind HCL prefix to joined keys (pattern: `test_ecr_image_retention.py`)
4. New `infra/scripts/reclaim-warehouse-duplicates.sh` — three selectors, VersionId deletes, ADR 0004 operator contract
5. Canonical silver — current `warehouse/silver/sec/silver.duckdb` and `shards/shard-{0-3}.duckdb`; hard deny-list for reclaim

**Key patterns:** (1) relative write + rooted join = lifecycle target; (2) lifecycle for continuous writers, VersionId delete for leftovers and keep-latest (lifecycle cannot keep newest gold `run_id=`); (3) versioned-bucket reclaim — never key-only DELETE; (4) trailing slashes `warehouse/silver/` vs `warehouse/silverstage/` — without the slash, `warehouse/silver` matches silverstage.

### Critical Pitfalls

Top failures already paid for in this bucket, or that copy-paste will recreate. See [PITFALLS.md](PITFALLS.md).

1. **Lifecycle filter omits `warehouse/`** — authors copy the Python relative path; rule matches nothing. Keep `warehouse/silverstage/` (trailing slash). Regression must construct the live key the same way production does.
2. **`terraform apply` from older module code restores `silverstage/`** — one resource replaces every warehouse rule. Apply only from `9d18e5ef+`; abort if plan moves prefix away or drops the 7-day silver rule.
3. **`aws s3 rm --recursive` on a versioned bucket** — inserts delete markers; billed bytes remain. Reclaim only via `list-object-versions` + `delete-objects` with `VersionId`; verify with another version listing, not `s3 ls`.
4. **Deleting current canonical silver** — `cleanup-s3-staging.sh` selects `IsLatest=true` (correct for ephemeral `_staging/`, fatal for shards). Shard reclaim: prefix `warehouse/silver/sec/shards/`, `IsLatest=false` only. Never add `expiration` to the silver rule.
5. **Prefix `warehouse/silver` (no trailing slash) also matches `warehouse/silverstage/`** — always use trailing slashes after different path segments.
6. **Gold / identity in-flight deletes** — streaming gold has no atomic “all tables exist” until the manifest finishes; identity reducer downloads snapshots at start. Exclude RUNNING gold-affecting executions and active identity `run_id` / lease.
7. **Mixing MDM WIP on `claude/credential-isolation`** — do not stage `edgar_warehouse/mdm/**`. Repeat at every reclaim PR.

## Implications for Roadmap

Based on combined research, **six phases**. Do not start reclaim until live lifecycle still shows `warehouse/silverstage/` after apply.

### Phase 0: Branch hygiene
**Rationale:** This checkout already mixed MDM files with lifecycle work. A mixed first commit makes the PR unreviewable and can ship unfinished pool behavior.
**Delivers:** Isolated `claude/silverstage-lifecycle` (or successor) diff: Terraform lifecycle, architecture test, reclaim script, this workstream’s `.planning/` only.
**Addresses:** Git isolation (FEATURES anti-feature / PITFALLS pitfall 8)
**Avoids:** Mixing MDM WIP into the lifecycle PR
**Research-phase:** skip — process, not domain research

### Phase 1: Leak-seal (regression + Terraform apply)
**Rationale:** A reverted prefix during reclaim re-fills the bucket. CI must make a bad apply unmergeable **before** plan/apply. Live S3 is already patched; Terraform state is the remaining hole.
**Delivers:** `tests/architecture/test_warehouse_lifecycle_prefix.py`; `terraform plan`/`apply` of `module.storage.aws_s3_bucket_lifecycle_configuration.warehouse` from `infra/terraform/accounts/prod`; post-apply `get-bucket-lifecycle-configuration` evidence that Prefix is `warehouse/silverstage/` and the 7-day `warehouse/silver/` noncurrent rule is unchanged (no `expiration` block).
**Addresses:** Terraform apply (P1); join() ↔ lifecycle regression (P1); plan gate
**Avoids:** Prefix omits `warehouse/`; apply restores `silverstage/`; `warehouse/silver` vs `silverstage` collision
**Uses:** Terraform 1.14.7+, hashicorp/aws 6.39.0, pytest, `StorageLocation.join()`
**Research-phase:** skip — contract is documented (join + official prefix semantics + in-repo HCL)

### Phase 2: Reclaim script + dry-run inventories
**Rationale:** All three reclaim jobs share one VersionId primitive. Write the script and reviewed manifests **before** any `--apply`. Gold keep-latest and identity skip-sets need a live listing, not guessed GiB.
**Delivers:** New `infra/scripts/reclaim-warehouse-duplicates.sh` (do not reuse `cleanup-s3-staging.sh`); three dry-run TSVs (shards / identity / gold) with key, version_id, last_modified, size_bytes, is_latest; running-task snapshot; evidence under a warehouse release-evidence prefix.
**Addresses:** Versioned delete primitive, dry-run/confirm, fail-closed allowlist, post-delete proof contract (implemented, not yet applied)
**Avoids:** `s3 rm`; 1000-key overflow; missing `is_latest` on the operator TSV
**Research-phase:** **yes (light)** — re-list live prefixes to confirm GiB, gold table layout, and whether identity has an in-flight `run_id`

### Phase 3: Noncurrent shard reclaim (~315 GiB)
**Rationale:** Largest remaining bill; safest selector (`IsLatest=false` on four keys). Independent of gold/identity once current keys are protected. Do this before smaller, logic-heavier prefixes.
**Delivers:** VersionId delete of noncurrent `warehouse/silver/sec/shards/shard-{0-3}.duckdb`; pre/post `head-object` on five canonical keys; remaining-bytes receipt.
**Implements:** Shard selector; standing 7-day rule left at 7 days
**Avoids:** Deleting current silver/shards; prefix `warehouse/silver` without `/sec/shards/`; concurrent `BatchSilver` promote races (idle or second pass)
**Research-phase:** skip after Phase 2 listing — IsLatest filter is a standard pattern

### Phase 4: Identity-refresh snapshot reclaim (~19 GiB)
**Rationale:** Whole prefix is non-canonical, but the reducer still reads `reference_snapshot.duckdb` / `delta.duckdb` for the **active** `run_id`. Needs idle reducer / excluded live lease. Optional same-phase or follow-on Terraform expire on `warehouse/identity_refresh/` so unique keys do not rot back.
**Delivers:** VersionId delete of historical `warehouse/identity_refresh/runs/{run_id}/` prefixes; active run excluded; optional 7-day current+noncurrent lifecycle on that prefix.
**Addresses:** Identity-refresh snapshot reclaim (P1); P2 standing expire if accepted in the same milestone
**Avoids:** Deleting snapshots a running reducer still checksums/downloads
**Research-phase:** **yes** if Phase 2 found a live `run_id` or lease — confirm skip-set against CloudWatch / lease objects

### Phase 5: Historical gold `run_id=` reclaim (~3.4 GiB)
**Rationale:** Smallest GiB, highest “latest run” logic risk. Streaming gold-refresh can leave a partial new `run_id` while the previous complete run is still the only full snapshot. Lifecycle cannot express keep-latest; UUID sort is wrong.
**Delivers:** Keep latest **complete** run per table (max `LastModified` among current objects, plus in-progress `run_id` if any gold-affecting execution is RUNNING — otherwise wait until idle); VersionId-delete older `run_id=` prefixes including their noncurrent versions; Snowflake export bucket untouched.
**Addresses:** Gold keep-latest reclaim (P1)
**Avoids:** Deleting the run a live task still needs; lexicographic UUID “latest”; reclaiming `edgartools-prod-snowflake-export-*`
**Research-phase:** **yes** — which prod `run_id` is currently latest / complete was not re-listed; grouping must be written against a live listing

### Phase Ordering Rationale

- Leak-seal before reclaim: writers must not refill unmatched `silverstage/` while deletes run.
- Regression before apply: a bad apply is unmergeable, not “we’ll notice in the plan.”
- Shared delete primitive + dry-run before any `--apply`: one reviewed contract, three selectors.
- Shards before identity/gold: explicit `IsLatest` keep-bit vs keep-latest / in-flight skip-sets.
- Gold last: easiest place to delete the live warehouse snapshot if grouping is wrong.
- Do not change the 7-day canonical-silver policy; do not touch bronze, tfstate, snowflake-export, or current canonical silver.

### Research Flags

Phases likely needing deeper research during planning (`/gsd:plan-phase --research-phase`):
- **Phase 2:** Live inventory (GiB, gold hive layout, identity in-flight `run_id`) is MEDIUM until re-listed
- **Phase 4:** Active identity lease / RUNNING reducer skip-set
- **Phase 5:** “Complete run_id” heuristic vs per-table `LastModified`; confirm no gold-affecting execution

Phases with standard patterns (skip research-phase):
- **Phase 0:** Git isolation
- **Phase 1:** Official S3 prefix semantics + existing HCL/`join()` contract + architecture-test pattern
- **Phase 3:** Noncurrent VersionId delete; ADR 0004 / staging-cleanup contract with a stricter `IsLatest=false` selector

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Official AWS lifecycle/DeleteObjects/ListObjectVersions docs + exact Terraform pins and in-repo scripts |
| Features | HIGH | Operator contracts match PROJECT.md and existing cleanup scripts; remaining GiB are MEDIUM (inventory dated 2026-08-20, not re-listed here) |
| Architecture | HIGH | Component boundaries, join() contract, and anti-patterns are repo-verified; billed-size split MEDIUM |
| Pitfalls | HIGH | Prefix leak, delete markers, 1000-key cap, Terraform full-document replace: live incidents + official docs. Gold complete-run heuristic MEDIUM until live listing |

**Overall confidence:** HIGH

### Gaps to Address

- **Remaining GiB not re-measured this pass:** treat ~315 / ~19 / ~3.4 as planning estimates; Phase 2 dry-run is the source of truth for apply-delete.
- **Gold “complete run_id” vs max-LastModified per table:** FEATURES says keep max `LastModified` among current objects; PITFALLS says also keep an in-progress run and prefer a complete set (manifest + all tables). Planning must pick: **idle gold-affecting executions, then keep latest complete run per table**; if a table has only one current run, delete nothing for that table.
- **Identity-refresh standing lifecycle:** ARCHITECTURE recommends a 7-day expire on `warehouse/identity_refresh/` so unique keys do not reaccumulate; FEATURES parks it as P2. Recommend: include the additive rule in Phase 1 or 4 if the plan is otherwise clean; do not block shard reclaim on it.
- **CLI pagination merging Versions + DeleteMarkers:** do not trust default pagination; page explicitly (PITFALLS MEDIUM).
- **Optional noncurrent `silver.duckdb` GiB:** out of v1.0 unless Phase 2 inventory shows it is still material after the 7-day rule.

## Sources

### Primary (HIGH confidence)
- [S3 Lifecycle configuration examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-configuration-examples.html) — prefix is a key-name prefix; versioned buckets need `NoncurrentVersionExpiration` to drop old versions without deleting current
- [Deleting object versions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html) — simple DELETE inserts a delete marker; permanent delete requires VersionId
- [DeleteObjects API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteObjects.html) / [CLI delete-objects](https://docs.aws.amazon.com/cli/latest/reference/s3api/delete-objects.html) — max 1000 keys; VersionId for permanent delete
- [ListObjectVersions API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectVersions.html) — `prefix`, `IsLatest`, pagination markers
- hashicorp/aws v6.39.0 `aws_s3_bucket_lifecycle_configuration` — `filter.prefix`; one lifecycle resource per bucket
- In-repo: `infra/terraform/modules/storage_buckets/main.tf`, `infra/terraform/accounts/prod/versions.tf`, `edgar_warehouse/infrastructure/object_storage.py`, `warehouse_paths.properties`, `identity_refresh_publication.py`, `infra/scripts/cleanup-s3-staging.sh`, `destroy-aws-complete.sh`, `tests/architecture/test_ecr_image_retention.py`, ADR 0004
- Workstream: [PROJECT.md](../PROJECT.md); commit `9d18e5ef`

### Secondary (MEDIUM confidence)
- Remaining billed sizes (~315 / ~19 / ~3.4 GiB) and gold latest-run inventory — PROJECT.md / live listing dated 2026-08-20, not re-listed in research
- Gold complete-run selection heuristic until a dry-run listing exists
- Default CLI pagination combining Versions + DeleteMarkers — page explicitly

### Tertiary (LOW confidence)
- None material for v1.0 scope. Recurring gold lifecycle and version-aware runtime `delete_object` are deferred, not researched as launch options.

---
*Research completed: 2026-08-20*
*Ready for roadmap: yes*
