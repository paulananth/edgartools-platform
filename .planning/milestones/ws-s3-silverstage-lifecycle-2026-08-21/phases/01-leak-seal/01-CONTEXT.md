# Phase 1: Leak-seal - Context

**Gathered:** 2026-08-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Lock the prod warehouse S3 lifecycle so staging objects expire under the live
`StorageLocation.join()` prefix, add a standing 7-day expire for unique
identity-refresh keys, and add an architecture regression so those prefixes
cannot silently miss live keys. Deliver REGR-01, LIFE-01, and IDEN-02 only.

This phase does not reclaim existing objects (Phase 2–3), inventory bronze
(Phase 4), or change CloudWatch retention (Phase 5). It does not delete
current canonical `warehouse/silver/sec/silver.duckdb` or
`shards/shard-{0-3}.duckdb`. It does not add `expiration` on
`warehouse/silver/`.

</domain>

<decisions>
## Implementation Decisions

### Terraform apply gate
- **D-01:** Prod apply is targeted at
  `module.storage.aws_s3_bucket_lifecycle_configuration.warehouse` after a
  reviewed plan. Do not apply the entire `infra/terraform/accounts/prod` root
  for this phase.
- **D-02:** Plan/apply uses AWS profile `aws-admin-prod`.
- **D-03:** If the plan shows extra warehouse-bucket changes besides that
  lifecycle resource, abort and report. Do not ride leak-seal along other
  storage drift.
- **D-04:** The join() lifecycle-prefix regression must be green before the
  apply runs.

### Identity-refresh expire shape
- **D-05:** Standing rule expires **current and noncurrent** identity-refresh
  objects (unique run keys never become noncurrent by overwrite).
- **D-06:** Filter prefix is `warehouse/identity_refresh/` (trailing slash).
  Lease files under `warehouse/reference/identity_refresh_lease/` are out of
  this rule.
- **D-07:** 7 days is a hard expire. Standing lifecycle does not skip RUNNING
  identity Maps. Phase 3's one-shot delete still skips in-flight `run_id`.
- **D-08:** `expiration.days = 7` and
  `noncurrent_version_expiration.noncurrent_days = 7`.
- **D-09:** Identity-refresh 7-day rule ships in the **same** lifecycle apply
  as the silverstage prefix. One
  `aws_s3_bucket_lifecycle_configuration.warehouse` document.

### Regression test shape
- **D-10:** REGR-01 is an architecture test that (1) parses
  `storage_buckets/main.tf` HCL and (2) calls `StorageLocation.join()` the
  way production does. Analog:
  `tests/architecture/test_ecr_image_retention.py`.
- **D-11:** Required negative case: filter `silverstage/` must **not** be a
  prefix of joined live keys. A revert to that relative path must fail CI.
- **D-12:** The same test locks all three prefixes:
  `warehouse/silverstage/`, `warehouse/identity_refresh/`,
  `warehouse/silver/`.
- **D-13:** Test lives in `tests/architecture/`. Runs with
  `uv run pytest` and needs no AWS credentials.

### Prefix / path exactness
- **D-14:** Exact Terraform `filter.prefix` strings, all with trailing
  slashes: `warehouse/silverstage/`, `warehouse/identity_refresh/`,
  `warehouse/silver/`. Trailing slash on silver is required so
  `warehouse/silver` cannot match `warehouse/silverstage/`.
- **D-15:** Join() assertions use a real storage root that ends in
  `/warehouse` (same contract as `WAREHOUSE_STORAGE_ROOT`), not a
  hand-concatenated `warehouse/` + relative path.
- **D-16:** This phase edits
  `infra/terraform/modules/storage_buckets/main.tf` only. Do not retouch
  destroyable/dev copies unless grep shows a second warehouse lifecycle
  still using `silverstage/`.
- **D-17:** If `join("silverstage", ...)` does not start with the Terraform
  silverstage prefix (including a future root that no longer ends in
  `/warehouse`), the test fails. HCL and join() must change in the same PR.

### Claude's Discretion
- Identity-refresh rule `id` string (suggest
  `expire-identity-refresh-run-snapshots`).
- Exact pytest filename (suggest
  `tests/architecture/test_warehouse_lifecycle_prefix.py`).
- How to parse HCL prefixes (string contains vs regex), as long as D-10–D-17 hold.
- Terraform `-target` invocation details, as long as D-01–D-03 hold.
- Constructing `StorageLocation` in the test (class name / factory), as long
  as join() is the production method on a `/warehouse` root.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Lifecycle and live keys
- `infra/terraform/modules/storage_buckets/main.tf` — warehouse lifecycle
  resource; current `expire-silver-staging-candidates` prefix
  `warehouse/silverstage/`; silver noncurrent-only 7-day rule
- `edgar_warehouse/infrastructure/object_storage.py` —
  `StorageLocation.join()` and `write_staged_bytes` (`silverstage/<uuid>/...`
  relative path)
- `edgar_warehouse/config/warehouse_paths.properties` — identity refresh
  lease path is `reference/identity_refresh_lease/...` (not under
  `identity_refresh/`)

### Test analog
- `tests/architecture/test_ecr_image_retention.py` — architecture test that
  reads Terraform HCL as text

### Workstream
- `.planning/workstreams/s3-silverstage-lifecycle/ROADMAP.md` — Phase 1 goal
  and success criteria
- `.planning/workstreams/s3-silverstage-lifecycle/REQUIREMENTS.md` — LIFE-01,
  REGR-01, IDEN-02
- `.planning/workstreams/s3-silverstage-lifecycle/PROJECT.md` — never expire
  current canonical silver
- `.planning/workstreams/s3-silverstage-lifecycle/research/SUMMARY.md` —
  one lifecycle document; apply replaces the whole resource; prefix is a
  key-name prefix

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `aws_s3_bucket_lifecycle_configuration.warehouse` in
  `infra/terraform/modules/storage_buckets/main.tf` — the only resource this
  phase should apply
- `StorageLocation.join()` / `write_staged_bytes` in
  `edgar_warehouse/infrastructure/object_storage.py` — live-key contract
- `tests/architecture/test_ecr_image_retention.py` — HCL-as-text architecture
  test pattern

### Established Patterns
- Passive AWS Terraform is operator-applied from
  `infra/terraform/accounts/prod` with `aws-admin-prod`
- One lifecycle resource per bucket; apply replaces the entire Rules document
- Architecture tests must not call AWS

### Integration Points
- Prod root `infra/terraform/accounts/prod` wires `module.storage`
- Live bucket `edgartools-prod-warehouse-690839588395` already has
  `warehouse/silverstage/` 3-day expiry from the 2026-08-20 CLI put; Terraform
  must not revert it and must add `warehouse/identity_refresh/` 7/7

</code_context>

<specifics>
## Specific Ideas

- Confirm after apply with `get-bucket-lifecycle-configuration`: staging
  prefix `warehouse/silverstage/`, identity prefix
  `warehouse/identity_refresh/` with 7-day current+noncurrent, silver
  `warehouse/silver/` noncurrent 7 days and **no** current expiration.
- Do not commit unrelated MDM WIP on `claude/credential-isolation` into this
  phase's PR (`edgar_warehouse/mdm/**`).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

Phase 2–5 remain: VersionId reclaim primitive, warehouse duplicate deletes,
bronze inventory, CloudWatch 3-day retention.

</deferred>

---

*Phase: 1-Leak-seal*
*Context gathered: 2026-08-20*
