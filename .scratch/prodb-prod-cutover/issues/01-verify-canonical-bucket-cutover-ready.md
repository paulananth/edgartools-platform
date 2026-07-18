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

**Status:** ready-for-agent

- [ ] Object count and latest-manifest key in the canonical bucket are
      compared against the old `prodb` bucket and reported (match / mismatch,
      with the diff if any)
- [ ] Any partial/failed copy evidence (incomplete multipart uploads, missing
      manifest suffixes, truncated listings) is explicitly called out
- [ ] Verification is read-only — no bucket policy, IAM, or Terraform state
      is modified by this ticket
- [ ] Findings are written up (pass/fail) so Ticket 02 has an explicit
      go/no-go signal to start from
