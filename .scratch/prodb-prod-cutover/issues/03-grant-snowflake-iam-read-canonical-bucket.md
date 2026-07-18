# 03 — Grant Snowflake IAM role read access to the canonical bucket

**What to build:** The `edgartools-prod-snowflake-s3` IAM role gains
read access (`s3:GetObject`/`s3:ListBucket` on the relevant prefixes) to
`edgartools-prod-snowflake-export-690839588395` *before* any Snowflake
object depends on it. This is purely additive — nothing reads from the
canonical bucket yet, so granting access changes no current production
behavior. Doing this ahead of the cutover window removes IAM propagation
delay from the live cutover in Ticket 05.

**Blocked by:** 02 — Perform Stage 2 S3 data copy: prodb → canonical buckets

**Status:** ready-for-agent

- [ ] `edgartools-prod-snowflake-s3` role's policy includes read access to
      the canonical bucket, additive to (not replacing) its existing access
      to the old `prodb` bucket
- [ ] Verified with a read-only assume-role test that actually reads an
      object from the canonical bucket using the role's credentials
- [ ] No Snowflake-side config (storage integration, stage) is touched in
      this ticket — this is IAM/AWS-side only
- [ ] Old `prodb` bucket access is left fully intact; current production
      ingestion is unaffected
