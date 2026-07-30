# 46 — Decide how to repair Apple's 45 orphaned earnings-8-K bronze objects

Type: task
Status: open
Blocked by: (none)

## Question

Ticket 44 fully root-caused why every one of Apple's (CIK 320193) 45 Item-2.02 earnings-8-K
accessions fails on fetch with `WarehouseRuntimeError("immutable object ... already exists with
different content")`: the pre-existing bronze objects were migrated verbatim from the
now-decommissioned `prodb` environment on 2026-07-19 (an `aws s3 sync` copy, not a fresh fetch),
captured back then via the old raw-HTTP `download_bytes` path that preserved SEC's exact bytes
(including a trailing newline); the current pipeline (since ticket 06's 2026-07-17 gateway
consolidation) fetches via edgartools' `attachment.content`, which `.strip()`s that trailing
newline — a genuine, understood, reproducible one-byte content difference for the *same logical
document*, not a wrong-document collision or corruption. Confirmed (ticket 44 §3) this is
Apple-specific, not a universe-wide blocker — no other sampled CIK has pre-existing bronze to
collide with.

This blocks ticket 42's F5 (`sec_earnings_release`) backfill from landing real rows for the pilot
CIK even with the Item-2.02 selection fix (PR #299) now live and correct.

Decide:
1. **How to reconcile the 45 existing objects with the pipeline's current output.** Options to
   weigh: (a) treat the existing byte-exact migrated content as canonical and adjust the pipeline
   (or add a normalization step) so a matching content-minus-trailing-newline is treated as
   equivalent, not a conflict; (b) run a scoped `--force` repair that overwrites the 45 existing
   objects with the `.strip()`-normalized version the current pipeline produces (accepting the
   1-byte loss, since it's provably immaterial — a trailing newline outside the parsed
   `<TEXT>` content); (c) something else. Ticket 44's evidence supports (b) as low-risk (the byte
   difference is a trailing newline, already outside SGML's meaningful content), but this is an
   operator call on data-integrity policy, not a pure engineering judgment.
2. **Whether this needs a general-purpose "known content-normalization mismatch" exception in the
   immutability guard** (for any future migrated-content collision of this same shape) or should
   be treated as a one-off, CIK-scoped repair specific to Apple's 45 accessions only.
3. Execute the chosen repair and re-verify ticket 42's F5 smoke test actually lands real
   `sec_earnings_release` rows for Apple afterward.

This is a task ticket (decision + execution) rather than pure research — the root cause is fully
understood (ticket 44); what remains is an operator decision on repair mechanism plus carrying it
out.
