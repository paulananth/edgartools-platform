# prodb → prod cutover

Labels: wayfinder:map

## Destination

**Reached — executed 2026-07-19, outside this tracker.** All 6 tickets here
described the plan for cutting `690839588395` over from the old `prodb`
buckets/Snowflake database to the canonical `-690839588395` resources. The
actual cutover ran as one operator session the day after Ticket 01's
verification pass, described in full in
`docs/prodb-to-prod-promotion.md` (now marked "EXECUTED 2026-07-19 — this
runbook is now a historical record") and `TODOS.md`'s "RESOLVED
(2026-07-19): prodb→prod promotion executed in full" entry. This tracker
was never updated afterward — closing it out now (2026-08-19) to match
reality, confirmed live: no `prodb`-named S3 bucket exists in the account
any more, and the canonical `edgartools-prod-{bronze,warehouse,
snowflake-export}-690839588395` buckets hold real, actively-written data
(904 objects / 4.6 GB in the export bucket alone, most recent 2026-08-09).

## Notes

- Domain: one-time infrastructure cutover, already executed and decommissioned.
- If this ever needs revisiting (e.g. a second environment cutover), treat
  `docs/prodb-to-prod-promotion.md` as the authoritative runbook, not these
  tickets — they describe the pre-execution plan, not what actually ran.

## Decisions so far

- [Verify canonical S3 bucket is populated and cutover-ready](issues/01-verify-canonical-bucket-cutover-ready.md) — found NOT ready (2026-07-18), which triggered the rest of this ticket set
- [Perform Stage 2 S3 data copy](issues/02-perform-stage2-s3-data-copy.md) — deferred pending release-readiness Ticket 20, then superseded by the full cutover the next day
- [Grant Snowflake IAM read access to canonical bucket](issues/03-grant-snowflake-iam-read-canonical-bucket.md) — done as part of the full cutover, not standalone
- [Prepare coordinated Terraform diff](issues/04-prepare-coordinated-terraform-diff.md) — superseded; the executed cutover reconciled `accounts/prod` state directly rather than via this plan-first sequencing
- [Execute live cutover and verify](issues/05-execute-live-cutover-and-verify.md) — done, 2026-07-19, single operator session (see `docs/prodb-to-prod-promotion.md`)
- [Decommission old prodb bucket and objects](issues/06-decommission-old-prodb-bucket-and-objects.md) — done; confirmed live 2026-08-19, no `prodb`-named bucket remains in the account

## Not yet specified

<!-- empty -- destination reached -->

## Out of scope

<!-- none recorded -->
