# 05 — Decommission old prodb S3 bucket + Snowflake objects

**What to build:** After a bake period confirming the canonical path
(Ticket 04) is stable, tear down the now-unused
`edgartools-prodb-snowflake-export` bucket and any orphaned Snowflake
objects that still reference it, closing out Stage 5 (cleanup) of
`docs/prodb-to-prod-promotion.md`.

**Blocked by:** 04 — Execute the live cutover in an approved operator window + verify

**Status:** ready-for-agent

- [ ] Bake period (owner-defined) has elapsed with no incidents tracing back
      to the canonical bucket/cutover
- [ ] Old `edgartools-prodb-snowflake-export` bucket contents are archived
      or confirmed redundant with the canonical bucket before deletion
- [ ] Old bucket, its IAM policy grants, and any dangling Snowflake stage/
      pipe references are removed
- [ ] `edgartools-prod-snowflake-s3` IAM role's policy no longer grants
      access to the decommissioned bucket
