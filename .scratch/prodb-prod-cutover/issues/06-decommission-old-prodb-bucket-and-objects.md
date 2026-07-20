# 06 — Decommission old prodb S3 bucket + Snowflake objects

**What to build:** After a bake period confirming the canonical path
(Ticket 05) is stable, tear down the now-unused
`edgartools-prodb-snowflake-export` bucket and any orphaned Snowflake
objects that still reference it, closing out Stage 5 (cleanup) of
`docs/prodb-to-prod-promotion.md`.

**Blocked by:** 05 — Execute the live cutover in an approved operator window + verify

**Status:** ready-for-agent

- [ ] Bake period (owner-defined) has elapsed with no incidents tracing back
      to the canonical bucket/cutover
- [ ] Old `edgartools-prodb-snowflake-export` bucket contents are archived
      or confirmed redundant with the canonical bucket before deletion
- [ ] Old bucket, its IAM policy grants, and any dangling Snowflake stage/
      pipe references are removed
- [ ] `edgartools-prod-snowflake-s3` IAM role's policy no longer grants
      access to the decommissioned bucket

---

**2026-07-19 — DONE (same-session per explicit user decision, expanded to ALL
prodb resources, not just snowflake-export).** Executed only after the
post-cutover preflight passed 12/12 (including formal 433,681 == 433,681
source/target object parity) and `mdm_check_connectivity` SUCCEEDED on the
canonical stack. Deleted, in order:
- Snowflake safety clone `EDGARTOOLS_LEGACY_BACKUP_20260719` (dropped; the
  underlying DB was verified data-empty pre- and post-rename)
- KMS alias `alias/edgartools-prodb-snowflake-export`; key `45c8c504…`
  scheduled for deletion (PendingDeletion, auto-reaps 2026-07-26 — 7 days is
  the AWS minimum window)
- `edgartools-prodb-snowflake-export` (0 versions — never held a manifest)
- `edgartools-prodb-tfstate` (123 state versions; current states live in
  `edgartools-prod-tfstate-690839588395` + local backups in
  `~/edgartools-tfstate-backups-20260719`)
- `edgartools-prodb-warehouse` (6,047 versions purged)
- `edgartools-prodb-bronze` (1,181,412 versions purged — current 433,681
  objects verified copied; the remainder was version history, knowingly
  forfeited per the user's confirmed DELETE decision)
Final sweep: zero `prodb` buckets, zero `prodb` IAM roles, zero
`EDGARTOOLS_PRODB` Snowflake objects. The four canonical
`edgartools-prod-*-690839588395` buckets are the only production storage.
