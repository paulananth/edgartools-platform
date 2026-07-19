# 01 — Verify canonical S3 bucket is populated and cutover-ready

**What to build:** A read-only verification pass confirming Stage 2 of
`docs/prodb-to-prod-promotion.md` (S3 data preservation into
`edgartools-prod-snowflake-export-690839588395`) actually completed, before
anyone attempts a cutover onto it. Object counts/keys in the canonical bucket
must match the old `edgartools-prodb-snowflake-export` bucket, the most
recent run manifest must be present, and there must be no evidence of a
partial or failed copy. This ticket changes no infrastructure — it only
produces the evidence gate that Ticket 02 depends on.

**Blocked by:** None — can start immediately.

**Status:** BLOCKED (verification FAILED) — verified 2026-07-18

- [x] Object count and latest-manifest key in the canonical bucket are
      compared against the old `prodb` bucket and reported (match / mismatch,
      with the diff if any)
- [x] Any partial/failed copy evidence (incomplete multipart uploads, missing
      manifest suffixes, truncated listings) is explicitly called out
- [x] Verification is read-only — no bucket policy, IAM, or Terraform state
      is modified by this ticket
- [x] Findings are written up (pass/fail) so Ticket 02 has an explicit
      go/no-go signal to start from

**Findings (2026-07-18, read-only AWS checks — `s3 ls`, `cloudwatch
get-metric-statistics`, `s3api get-bucket-lifecycle-configuration`/
`get-bucket-versioning`/`list-object-versions`):**

- `edgartools-prod-snowflake-export-690839588395` (canonical): **0 objects**.
  Stage 2 of `docs/prodb-to-prod-promotion.md` has NOT copied any data into
  this bucket — it is a freshly-created, empty bucket, not a populated
  mirror of prodb's export bucket.
- `edgartools-prodb-snowflake-export` (old): also **0 objects**, and
  `list-object-versions` shows zero versions ever recorded despite
  versioning being enabled on the bucket — this bucket has never held a
  manifest, consistent with `gold-refresh`/`SNOWFLAKE_RUN_MANIFEST_TASK`
  never having run (see TODOS.md's 2026-07-18 addendum to the prodb→prod
  flag entry).
- By contrast, `edgartools-prodb-bronze` (~41GB) and `edgartools-prodb-warehouse`
  (~263GB) are real, actively-growing production data — bronze/silver
  ingestion is live (confirmed via 4 running ECS tasks, Codex's Ticket 20
  strict-release bulk-load, writing to `prodb-bronze` as of this morning).
  The canonical `prod-bronze-690839588395`/`prod-warehouse-690839588395`
  buckets are also both empty — no bronze/silver data has migrated either.
- **Go/no-go signal for Ticket 02: NO-GO as scoped.** There is nothing to
  "match" yet — Stage 2 (S3 preservation) has not actually run for any of
  the three canonical buckets, not just snowflake-export. Ticket 02 (or a
  new ticket ahead of it) needs to actually perform the bronze/warehouse/
  snowflake-export copy from `prodb` to canonical before any IAM/Terraform
  cutover work proceeds — this ticket set assumed Stage 2 was already
  partially done; it is not.

---

**2026-07-19 — superseded by execution.** The NO-GO finding above was correct
and served its purpose: the full cutover session (user directive) performed the
Stage 2 copy itself before any IAM/Terraform work. See Ticket 02.
