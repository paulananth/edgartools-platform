# Pitfalls Research

**Domain:** Warehouse S3 lifecycle prefix correctness and versioned duplicate reclaim (existing EdgarTools AWS platform)
**Researched:** 2026-08-20
**Confidence:** HIGH

This is a subsequent-milestone add-on, not a greenfield stack. The failure modes below are the ones that already happened in this bucket, or that this reclaim will recreate if copied from the wrong sibling script.

Live target: account `690839588395`, bucket `edgartools-prod-warehouse-690839588395`, versioning enabled. Canonical current keys that must survive every reclaim:

- `warehouse/silver/sec/silver.duckdb`
- `warehouse/silver/sec/shards/shard-{0,1,2,3}.duckdb`

`WAREHOUSE_STORAGE_ROOT` already ends in `/warehouse`. `StorageLocation.join()` prefixes that root onto every relative write, so `write_staged_bytes("silverstage/<uuid>/...")` lands at `warehouse/silverstage/<uuid>/...`.

## Critical Pitfalls

### Pitfall 1: Lifecycle filter omits the `warehouse/` prefix

**What goes wrong:**
The Terraform rule `expire-silver-staging-candidates` filters `silverstage/`. Live keys are `warehouse/silverstage/...`. S3 prefix match is a literal key-prefix, not a path suffix, so the rule matches nothing. Staging candidates then live forever. Confirmed 2026-08-20: 1,999 orphaned DuckDB copies, 1.70 TiB, after the filter was wrong. The same class of bug existed earlier as `_staging/` with no lifecycle rule at all.

**Why it happens:**
Authors read `write_staged_bytes` (`staged_relative = f"silverstage/{uuid}/..."`) and copy that relative path into Terraform. They do not join it with `WAREHOUSE_STORAGE_ROOT`. Comments in `identity_refresh_publication.py` still say "lifecycle rule on silverstage/" without the storage-root prefix, which re-teaches the wrong key.

**How to avoid:**
Keep the live filter at `warehouse/silverstage/` (trailing slash required). Regression must construct the live key the same way production does: `StorageLocation(WAREHOUSE_STORAGE_ROOT).join(write_staged_bytes relative path)` and assert the Terraform `prefix` is a prefix of that key, not of the relative path. Never "fix" the Python write path to drop `warehouse/` to match an old filter.

**Warning signs:**
- `get-bucket-lifecycle-configuration` shows `Prefix=silverstage/` while `list-objects-v2 --prefix warehouse/silverstage/` returns objects
- `list-objects-v2 --prefix silverstage/` is empty
- Staging GiB grows after successful promotions (success-path `delete_object` still leaves versions; the lifecycle is the conflict-case backstop)

**Phase to address:**
Leak-seal Terraform apply + regression check (before any further reclaim).

---

### Pitfall 2: `terraform apply` from older module code restores `silverstage/`

**What goes wrong:**
Live bucket lifecycle was already corrected to `warehouse/silverstage/` on 2026-08-20. Terraform source was corrected in `9d18e5ef` on `claude/silverstage-lifecycle`. `aws_s3_bucket_lifecycle_configuration` is a single PutBucketLifecycleConfiguration resource: apply replaces **every** warehouse lifecycle rule, not just the one you meant. Applying `infra/terraform/accounts/prod` from `main` (pre-merge), from another worktree, or from a stash that still has `prefix = "silverstage/"` silently reopens the 1.7 TiB leak. A bad apply can also drop `expire-noncurrent-silver-canonical-versions` if the checkout predates `2e92d7d8`.

**Why it happens:**
The leak is already "fixed live," so an operator treats Terraform as catch-up and does not inspect the plan's prefix diff. Local `backend.hcl` / module source is assumed current. Dev is decommissioned; `storage_buckets_destroyable` still has **no** warehouse lifecycle at all, so copying "the other storage module" is not a safe fallback.

**How to avoid:**
Apply only from a checkout that contains `9d18e5ef` (or its merge). Abort if `terraform plan` shows the staging prefix changing **away from** `warehouse/silverstage/`, or shows destroy of `expire-noncurrent-silver-canonical-versions`. After apply, re-read live config with `get-bucket-lifecycle-configuration` and compare both rule IDs and prefixes to source. Do not apply this root with unrelated tfvars drift in the same pass.

**Warning signs:**
- Plan: `prefix` `warehouse/silverstage/` → `silverstage/`
- Plan wants to replace the whole `module.storage.aws_s3_bucket_lifecycle_configuration.warehouse`
- Post-apply live Prefix != committed Prefix

**Phase to address:**
Leak-seal Terraform apply (gate: plan review before apply).

---

### Pitfall 3: `aws s3 rm --recursive` on a versioned bucket does not free storage

**What goes wrong:**
High-level `aws s3 rm` / `s3 rb --force` / Console "delete object" without a VersionId issues a simple DELETE. On a versioning-enabled bucket that inserts a delete marker and leaves every prior version billed at the same $/GiB. Operators see an empty `aws s3 ls` and think the 315 GiB is gone. It is not. Official S3 behavior: only `DELETE` with `versionId` (or lifecycle `NoncurrentVersionExpiration`) permanently removes bytes.

This platform already paid for that lesson: `cleanup-s3-staging.sh` exists specifically because recursive delete is unsafe here, and `destroy-aws-complete.sh` had to use `list-object-versions` + `delete-objects` with VersionId.

**Why it happens:**
`aws s3 ls` and `list-objects-v2` hide noncurrent versions. The CLI `s3` namespace has no `--version-id` bulk path. Copying a bronze or local-dev cleanup one-liner feels fast.

**How to avoid:**
Reclaim only via `s3api list-object-versions` + `s3api delete-objects` payloads that include `VersionId`, same contract as `infra/scripts/cleanup-s3-staging.sh`: dry-run manifest → reviewed TSV → `--apply` with explicit confirm flag. Never `aws s3 rm --recursive` against this bucket. After delete, verify with another `list-object-versions --prefix ...`, not `s3 ls`.

**Warning signs:**
- `s3 ls` empty under the prefix but Storage Lens / bucket size unchanged
- `list-object-versions` still returns large `Size` on `IsLatest=false` rows
- Delete-marker count jumped; billed bytes did not fall

**Phase to address:**
Every reclaim phase (shards, identity-refresh, gold). Encode it in the runbook before the first apply-delete.

---

### Pitfall 4: Deleting current canonical `silver.duckdb` or `shard-*.duckdb`

**What goes wrong:**
A prefix delete under `warehouse/silver/` that does not filter `IsLatest=false` (or that uses `Expiration` instead of `NoncurrentVersionExpiration`) removes the only live silver copy. Every bootstrap/daily/MDM reader hydrates from those five keys. There is no second warehouse of canonical silver. Immediate reclaim of **noncurrent** shard versions is in scope; deleting current objects is a full-platform outage plus a bronze-to-silver rebuild.

`cleanup-s3-staging.sh` selects versions by age **including** `IsLatest=true`. That is correct for ephemeral `warehouse/_staging/` and would be catastrophic if copied onto `warehouse/silver/sec/shards/`.

**Why it happens:**
Staging cleanup is the nearest script. Shard keys look like "just more DuckDB files." The standing 7-day rule (`expire-noncurrent-silver-canonical-versions`) is easy to "speed up" by adding an `expiration { days = N }` block copied from the silverstage rule. That comment in `storage_buckets/main.tf` exists because this exact mistake would delete the live copy on a quiet day.

**How to avoid:**
- Reclaim shards with prefix `warehouse/silver/sec/shards/` (not `warehouse/silver/` and not `warehouse/silver` without the trailing slash).
- Delete only rows where `IsLatest` is false. Refuse a manifest that contains current `silver.duckdb` or `shard-{0-3}.duckdb`.
- Do not change the 7-day noncurrent policy in this milestone (explicitly out of scope).
- Never add `expiration` to `expire-noncurrent-silver-canonical-versions`.

**Warning signs:**
- Manifest `is_latest=true` for `silver.duckdb` or `shard-N.duckdb`
- Terraform plan adds `expiration` under `warehouse/silver/`
- Post-delete `head-object` 404 on a canonical key
- ECS warehouse tasks fail hydrating silver at start

**Phase to address:**
Shard noncurrent reclaim. Review the manifest before `--apply`.

---

### Pitfall 5: Prefix `warehouse/silver` (no trailing slash) also matches `warehouse/silverstage/`

**What goes wrong:**
S3 prefix `warehouse/silver` matches both `warehouse/silver/sec/...` **and** `warehouse/silverstage/<uuid>/...`. A lifecycle or `list-object-versions --prefix warehouse/silver` then expires or lists staging candidates as if they were canonical silver, or expires canonical silver under a "staging" rule. The two current rules are disjoint only because they use `warehouse/silver/` and `warehouse/silverstage/` with trailing slashes after different path segments.

**Why it happens:**
People treat prefixes like directories. `startswith("warehouse/silver")` is true for `warehouse/silverstage`.

**How to avoid:**
Always use `warehouse/silver/` and `warehouse/silverstage/` with the trailing slash. Regression: assert `warehouse/silver/` is not a prefix of a joined silverstage key, and `warehouse/silverstage/` is not a prefix of a joined canonical silver key.

**Warning signs:**
- One lifecycle rule's listed objects include both `silver/sec/` and `silverstage/`
- A "silver reclaim" manifest contains `silverstage/` keys

**Phase to address:**
Leak-seal regression + shard reclaim prefix choice.

---

### Pitfall 6: Deleting the gold `run_id` a running task still needs

**What goes wrong:**
Warehouse gold parquet lives at `warehouse/gold/{table_name}/run_id={run_id}/{table}.parquet` (`gold.table.path`). Gold-affecting commands stream table-by-table: write warehouse parquet for table N, export that table to the Snowflake export bucket, discard, next table. "Keep the latest run per table" during an in-flight `gold-refresh` / `daily_incremental` / `bootstrap` can delete:

- the previous **complete** run_id, while the new run_id is only partially written, or
- the in-progress run_id's already-written tables, which the same task still has to reference in the run manifest.

A later task crash then leaves no complete warehouse gold snapshot. Snowflake native-pull reads the **export** bucket, not these warehouse copies, but warehouse gold is still the local audit/rebuild copy this milestone is reclaiming.

**Why it happens:**
Latest-by-`LastModified` per table is independent across tables. Lexicographic `run_id` is not "latest." A streaming publish has no atomic "all tables exist for run_id" marker until the manifest is finished.

**How to avoid:**
Do not reclaim `warehouse/gold/` while any `SOURCE_EXPORT_COMMANDS` / gold-refresh ECS task or Step Functions execution is RUNNING. Keep the latest **complete** run (manifest present, all expected tables present) plus the in-progress run_id if any. Delete only older complete `run_id=` prefixes. Do not touch `edgartools-prod-snowflake-export-*` (different bucket, native-pull input).

**Warning signs:**
- Gold-refresh execution RUNNING while the delete manifest includes today's `run_id=`
- Per-table "latest" run_ids disagree
- Manifest object missing for the run_id you kept

**Phase to address:**
Historical gold `run_id=` reclaim (after shard + identity-refresh, when no gold-affecting execution is running).

---

### Pitfall 7: Deleting identity-refresh snapshots a running reducer still reads from S3

**What goes wrong:**
`reduce_identity_refresh` checksums and downloads `identity_refresh/runs/{run_id}/reference/reference_snapshot.duckdb` and each `batches/{batch_id}/delta.duckdb` from S3 into a local cache at the start of the reducer. Map workers are still writing those deltas while the run is open. Deleting "historical" `warehouse/identity_refresh/` without excluding the active `run_id` 404s the reducer or a late batch persist. ~19 GiB is the reclaim target; the current run is not historical.

**Why it happens:**
All identity-refresh DuckDB files look like debug snapshots. The lease lives at a different prefix (`reference/identity_refresh_lease/runs/{run_id}/lease_result.json`), so checking the lease path does not prove the snapshot prefix is idle.

**How to avoid:**
Exclude the active identity-refresh `run_id` (and any run with a live lease or RUNNING `ReduceIdentityRefresh` / identity Map). Reclaim whole old `identity_refresh/runs/{run_id}/` prefixes, not "all `delta.duckdb` under the prefix." Record running ECS tasks / state machines in the evidence bundle the way `cleanup-s3-staging.sh` already does.

**Warning signs:**
- `identity_refresh_attempt_started` in CloudWatch after the delete
- Manifest includes a `run_id` that matches a live lease object
- Reducer `WarehouseRuntimeError` on missing snapshot/delta checksum

**Phase to address:**
Identity-refresh snapshot reclaim.

---

### Pitfall 8: Mixing this commit with unrelated MDM WIP on `claude/credential-isolation`

**What goes wrong:**
This branch already had dirty MDM files (`edgar_warehouse/mdm/database.py`, `pipeline.py`, pool-config tests, `test_run_all_step_concurrency.py`) while the lifecycle workstream was active. Committing leak-seal Terraform or reclaim scripts with credential-isolation / MDM concurrency changes makes the PR unreviewable, can ship unfinished MDM pool behavior into prod, and violates the repo rule that Claude/Codex must not share an uncoordinated edit surface.

**Why it happens:**
Same checkout, same `claude/` prefix, `git add -A` after a Terraform edit. `.planning/active-workstream` was also dirty.

**How to avoid:**
Do not stage `edgar_warehouse/mdm/**` or MDM tests in this workstream. Keep reclaim/terraform commits to `infra/terraform/modules/storage_buckets/`, tests that assert the lifecycle prefix vs `join()`, reclaim scripts, and this workstream's `.planning/` files. If MDM WIP must survive, stash it or move it back to `claude/credential-isolation` before the first lifecycle commit. Never commit to a branch whose latest unexpected commit is the other runtime's.

**Warning signs:**
- `git status` shows `edgar_warehouse/mdm/` next to `storage_buckets/main.tf`
- PR diff includes SQLAlchemy pool settings
- `.planning/active-workstream` flipped away from `s3-silverstage-lifecycle`

**Phase to address:**
Before the first commit of leak-seal. Repeat at every reclaim PR.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Patch live lifecycle via CLI, skip Terraform apply | Leak stops today | Next `terraform apply` from old source restores `silverstage/` | Only as an emergency stop, with Terraform catch-up the same day |
| Copy `cleanup-s3-staging.sh` and change the prefix | Fast reclaim script | That script deletes `IsLatest=true` and targets `warehouse/_staging/`, not shards | Never without rewriting the selection rule |
| Shorten canonical-silver noncurrent days from 7 to 0/1 | Faster ongoing reclaim | No silver rollback window after a bad promote | Never in this milestone (out of scope) |
| Add `expiration` to the `warehouse/silver/` rule | "Symmetric" with silverstage | Deletes current canonical silver | Never |
| Rely on 3-day staging lifecycle instead of immediate version-id delete | No operator delete | On versioned buckets, `Expiration` first writes a delete marker; bytes become noncurrent and need `noncurrent_days` too — up to ~6 days billed | Acceptable as backstop only, not as the 1.7 TiB cleanup |
| `StorageLocation.delete_object` without VersionId | Simple success-path cleanup | Creates a delete marker; prior staging version stays billed until noncurrent expiry | Acceptable for app cleanup; lifecycle must keep **both** `expiration` and `noncurrent_version_expiration` |
| One Terraform apply covering notifications, runtime, and lifecycle | Fewer applies | Unrelated plan diffs hide a prefix revert | Never; read the lifecycle resource in isolation |
| Commit lifecycle + MDM pool changes together | One PR | Undebuggable blast radius; workstream collision | Never |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| S3 lifecycle `Filter.Prefix` | Use the Python relative path `silverstage/` | Use the joined live key prefix `warehouse/silverstage/` |
| `aws_s3_bucket_lifecycle_configuration` | Treat it as additive per-rule | It replaces the entire bucket lifecycle document on apply |
| `aws s3 rm` / Console delete | Assume bytes are gone | Use `delete-objects` with `VersionId`; verify with `list-object-versions` |
| `s3api delete-objects` | Send a whole `list-object-versions` page | Cap at 1000 objects. One page can return 1000 Versions **plus** 1000 DeleteMarkers (this repo's AWS teardown 5-whys, `destroy-aws-complete.sh`) |
| `list-object-versions` | Dump one JSON without pagination | Page on `KeyMarker` / `VersionIdMarker` (or CLI pagination that actually merges both arrays) |
| `cleanup-s3-staging.sh` | Reuse as shard/gold reclaim | New manifest rules: `IsLatest=false` for shards; whole old `run_id` prefixes for identity/gold; never `_staging/` semantics |
| Snowflake export bucket | Delete `run_id=` parquet there too | Out of scope. Native-pull reads `edgartools-prod-snowflake-export-*`, not warehouse gold |
| Bronze / tfstate buckets | "Also duplicates" | Out of scope. Different buckets; bronze is immutable filings; tfstate is required for apply |
| AWS account | Apply with a profile still pointed at `077127448006` | Fail closed on `sts get-caller-identity` == `690839588395` (`check.canonical_prod_account`) |
| App `delete_object` | Expect it to free versioned staging bytes immediately | It does not pass `VersionId`; lifecycle is the versioned backstop |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Unbounded `list-object-versions` into one JSON | CLI timeout, truncated inventory, under-delete | Prefix-narrow listing (`.../shards/`, per gold table); page; write TSV incrementally | Already: 2,011 silverstage versions. Worse for many gold `run_id=` keys |
| `delete-objects` > 1000 keys (Versions+DeleteMarkers combined) | `MalformedXML` / `InvalidArgument`, partial delete | Batches of ≤1000, preferably 100 like `cleanup-s3-staging.sh` | One list page with both arrays (observed 1010 combined on snowflake-export) |
| Deleting current objects to "save a list filter" | Instant 404s on hydrate | Filter `IsLatest=false`; `head-object` the five canonical keys before and after | First mistaken apply |
| Waiting for the 7-day rule to reclaim 315 GiB | Cost continues; versions newer than 7 days never go | Immediate VersionId delete of already-noncurrent shards; leave the 7-day rule as the standing backstop | Versions < 7 days noncurrent stay forever if you only "wait" |
| S3 size metrics as the done check | "Nothing changed" for 24h+ | Use `list-object-versions` byte sums on the prefix as the reclaim receipt | Always — CloudWatch/S3 Storage Lens lag |
| Reclaim while 20-wide `BatchSilver` is promoting shards | Extra noncurrent versions appear during delete; race with hydrate | Run shard reclaim when no silver-publish execution is RUNNING, or accept new noncurrent versions after and do a second pass | Concurrent `stage_and_promote` on shard keys |

## Security Mistakes

Domain-specific issues for this reclaim, not generic web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Broad `s3:DeleteObject` / `s3:DeleteObjectVersion` on `*` for the runner role | Runtime can delete canonical silver | Keep reclaim on the admin profile; do not widen `sec_platform_runner_*` policies |
| Deleting without a reviewed VersionId manifest | Irreversible loss of canonical or in-flight gold | Dry-run TSV, human confirm flag, prefix allowlist in code |
| Putting EDGAR identity / image digests into Terraform to "make apply easier" | Secrets in state | Passive infra only; this apply is lifecycle prefix, nothing else |
| Running reclaim against the decommissioned account's leftover ARNs | Wrong-account delete or auth errors that get "fixed" by retargeting 077 | Hard-code expected bucket `edgartools-prod-warehouse-690839588395` and check caller account |
| Uploading evidence bundles that include secret values from application JSON | Secret leak into the same bucket | Evidence = version listings and TSV keys/VersionIds/sizes only |

## UX Pitfalls

Operator-facing mistakes (this work is operator reclaim, not an end-user app).

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Dry-run that prints row counts but not GiB and `is_latest` | Operator approves a current-key delete | TSV columns: key, version_id, last_modified, size_bytes, is_latest |
| "Empty prefix" from `aws s3 ls` as success | False completion; bill unchanged | Post-delete `list-object-versions` remaining-bytes report |
| One confirm flag reused from staging cleanup (`--confirm-delete-staging`) on shards | Muscle-memory apply against the wrong prefix | Distinct confirm flags per prefix (`--confirm-delete-noncurrent-shards`, etc.) |
| Applying Terraform because plan is "only 1 change" without reading the prefix | Restores the leak | Require the plan snippet for `expire-silver-staging-candidates` in the evidence bundle |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Lifecycle leak-seal:** Live `get-bucket-lifecycle-configuration` Prefix is `warehouse/silverstage/` **and** Terraform source matches **and** `terraform plan` after apply is clean — live CLI patch alone is not done
- [ ] **Regression:** Test joins `StorageLocation("s3://.../warehouse")` with `silverstage/...` and asserts Terraform prefix; a test that only inspects the relative path `silverstage/` will pass while prod is still wrong
- [ ] **Versioned reclaim:** Every deleted object in the receipt has a `VersionId`; zero `s3 rm` / delete-marker-only operations
- [ ] **Canonical silver:** Post-reclaim `head-object` succeeds on `warehouse/silver/sec/silver.duckdb` and `shards/shard-{0-3}.duckdb`; those keys were absent from the delete manifest or marked `is_latest=true` and skipped
- [ ] **Shard scope:** Manifest keys all start with `warehouse/silver/sec/shards/` and `IsLatest=false`; no `warehouse/silverstage/`, no `silver.duckdb`, no bronze, no tfstate
- [ ] **Identity-refresh:** Active `run_id` (lease or RUNNING reducer) excluded; deleted prefixes are whole old `identity_refresh/runs/{run_id}/`
- [ ] **Gold:** No gold-affecting execution RUNNING; kept run is a complete set, not per-table LatestModified; Snowflake export bucket untouched
- [ ] **delete-objects batches:** ≤1000 objects per call; errors array in each batch result is empty; post-list remaining selected VersionIds is 0
- [ ] **Git isolation:** Diff has no `edgar_warehouse/mdm/**`; branch is `claude/silverstage-lifecycle` (or successor), not `claude/credential-isolation`
- [ ] **Account:** `sts get-caller-identity` is `690839588395`; bucket name ends with that account id
- [ ] **Standing 7-day rule:** Still present, still noncurrent-only, still `warehouse/silver/` with trailing slash, days still 7

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Lifecycle prefix reverted to `silverstage/` | LOW (config) / HIGH (if leak ran for days) | Re-apply Terraform from `9d18e5ef+`; immediately `put-bucket-lifecycle-configuration` if apply is blocked; do not wait for the next scheduled apply |
| `s3 rm --recursive` created delete markers only | LOW | Do not "fix" by deleting delete markers (that restores old versions as current). List versions, delete noncurrent VersionIds you actually intended to drop, leave current canonical keys |
| Current canonical silver deleted | HIGH | Stop warehouse/MDM/gold tasks. If a noncurrent version still exists, delete the new delete marker (or copy that VersionId onto the key) to restore. If all versions are gone, rebuild silver from bronze — multi-day `load_history` / `silver-mdm-gold`. This is why current keys are never in the manifest |
| Wrong prefix deleted staging **and** silver | HIGH | Same as canonical silver recovery; treat as incident, not a retry |
| In-progress gold `run_id` deleted | MEDIUM | Re-run `gold-refresh` once silver is intact; Snowflake may still have the previous native-pull load. Do not restore warehouse gold from the export bucket without checking schemas |
| In-progress identity-refresh snapshots deleted | MEDIUM | Re-run the identity-refresh Map + reducer for that window; do not promote a partial merge |
| Terraform apply from old module dropped the 7-day silver rule | LOW | Re-apply current module; noncurrent versions resume accumulating until the rule is back — not data loss |
| MDM files committed into the lifecycle PR | MEDIUM | Reset/restore those paths off the PR before merge; do not deploy a mixed image "while we are here" |
| `delete-objects` MalformedXML / partial batch | LOW | Cap 1000, retry remaining VersionIds from the post-list; do not re-run a recursive rm |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Lifecycle filter missing `warehouse/` | Phase 1 — leak-seal Terraform + regression | Live Prefix == `warehouse/silverstage/`; joined `write_staged_bytes` key startswith that prefix |
| Terraform apply restores old prefix | Phase 1 — plan gate before apply | Plan does not change Prefix away from `warehouse/silverstage/`; post-apply `get-bucket-lifecycle-configuration` matches source for **both** warehouse rules |
| `s3 rm` on versioned bucket | Phase 3–5 — all reclaim runbooks | Script has no `aws s3 rm`; receipts list VersionIds; post `list-object-versions` bytes drop |
| Delete current silver/shards | Phase 3 — shard reclaim | Manifest `is_latest=false` only; pre/post `head-object` on five canonical keys |
| `warehouse/silver` vs `warehouse/silverstage` collision | Phase 1 regression + Phase 3 prefix | Trailing slashes; unit test that the two prefixes are disjoint on real joined keys |
| Delete gold run a live task needs | Phase 5 — gold historical reclaim | No RUNNING gold-affecting executions; keep complete latest run_id set |
| Delete identity-refresh active run | Phase 4 — identity-refresh reclaim | Active run_id / lease excluded; reducer not RUNNING |
| Mix MDM WIP into this commit | Phase 0 — branch hygiene, before Phase 1 commit | `git diff --stat` has no `edgar_warehouse/mdm/` |
| `delete-objects` 1000-key overflow | Phase 3–5 batching | Batches ≤1000; teardown 5-whys pattern; no MalformedXML |
| Shorten 7-day canonical policy | Out of scope this milestone | Terraform still `noncurrent_days = 7` and no `expiration` on that rule |

Suggested phase order (dependencies):

1. **Branch hygiene** — unmix `claude/credential-isolation` files
2. **Leak-seal apply + regression** — stop the leak before measuring remaining duplicates; a reverted prefix during reclaim re-fills the bucket
3. **Noncurrent shard reclaim** — largest remaining GiB; independent of gold/identity once canonical current keys are protected
4. **Identity-refresh snapshot reclaim** — needs idle reducer
5. **Historical gold `run_id=` reclaim** — needs idle gold-refresh; smallest GiB, highest "latest run" logic risk

Do not start 3–5 until Phase 2's live lifecycle still shows `warehouse/silverstage/` after the apply.

## Sources

- Live incident + Terraform comments: `infra/terraform/modules/storage_buckets/main.tf` (`expire-silver-staging-candidates`, `expire-noncurrent-silver-canonical-versions`); commit `9d18e5ef`; workstream `PROJECT.md` / `STATE.md`
- Write path: `edgar_warehouse/infrastructure/object_storage.py` (`join`, `write_staged_bytes`, `promote_staged`, `delete_object` without VersionId)
- Path catalog: `edgar_warehouse/config/warehouse_paths.properties` (`gold.table.path`, silver shard paths); `identity_refresh_publication.py` (`identity_refresh/runs/...`)
- Versioned delete, official: [Deleting object versions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html) — simple DELETE inserts a delete marker; permanent delete requires VersionId; `Expiration` on versioned buckets also creates delete markers; `NoncurrentVersionExpiration` permanently removes bytes
- Prefix filters, official: [S3 Lifecycle configuration examples](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-configuration-examples.html) — prefix is a key-name prefix (`tax/` matches `tax/doc1.txt`)
- High-level CLI: [AWS CLI s3 rm](https://docs.aws.amazon.com/cli/latest/userguide/cli-services-s3-commands.html) — recursive object delete, no VersionId
- In-repo versioned delete pattern: `infra/scripts/cleanup-s3-staging.sh` (dry-run manifest, VersionId delete, batches of 100); `infra/scripts/destroy-aws-complete.sh` (1000-key cap, Versions+DeleteMarkers overflow)
- AWS teardown 5-whys in `Claude.md` — `delete-objects` MalformedXML when combining >1000 versions+markers
- Platform constraints: `Agents.md` / `Claude.md` — AWS-only, account `690839588395`, canonical silver immutability, do not mix workstreams

**Confidence notes:**
- Prefix leak, versioned-delete markers, 1000-key cap, Terraform full-document replace: **HIGH** (official docs + this repo's live incidents)
- Gold "complete run_id" selection heuristic: **MEDIUM** until the reclaim script is written against a live listing (path layout is HIGH; which run_id is currently latest in prod was not re-listed in this pass)
- CLI default pagination merging both `Versions` and `DeleteMarkers` arrays into one file: **MEDIUM** — do not rely on it; page explicitly

---
*Pitfalls research for: warehouse S3 lifecycle prefix correctness and versioned duplicate reclaim*
*Researched: 2026-08-20*
*Workstream: s3-silverstage-lifecycle*
