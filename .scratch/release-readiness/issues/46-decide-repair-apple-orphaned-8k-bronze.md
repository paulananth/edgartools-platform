# 46 — Decide how to repair Apple's 45 orphaned earnings-8-K bronze objects

Type: task
Status: resolved
Blocked by: none

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

## Progress (2026-07-31)

The proposed one-byte normalization was fully dry-run, applied with per-key
ETag preconditions, and independently verified for all 45 keys. However, the
subsequent Apple-only `bootstrap-batch` run on the current immutable production
image still had 18 immutable-content conflicts. Direct live comparison of one
of those accessions (`0000320193-19-000073`) showed the current gateway payload
is 109 bytes shorter than the restored migrated object and differs from byte 1,
not solely by a terminal newline.

All 45 keys were immediately restored to their prior byte-exact S3 versions,
again with current-version preconditions; independent readback matched every
prior SHA-256. No `bootstrap-fundamentals --mode per-filing` run was started.
The one-byte repair is rejected and no shared immutability exception was added.
Ticket 55 must establish the actual current-image content contract before a new
operator repair decision can be made.

## Unblocked (2026-08-01)

The byte-exact direct-SEC capture implementation is now available. This ticket
may proceed with its scoped Apple repair decision and verification; it must use
that byte-preserving path and must not revive the rejected normalization
exception or overwrite the preserved bronze objects without the chosen repair
procedure.

## Resolution (2026-08-01)

The chosen repair is to retain the restored, byte-exact bronze objects as canonical and consume
their registered raw/attachment artifacts; no normalization exception and no overwrite were
introduced.  The remaining F5 failure was a separate consumer-selection defect: the
per-filing workflow fed the primary Item 2.02 8-K to the earnings parser instead of its
`EX-99.1` release attachment.

After the targeted selection fix, unit regression, immutable-image deployment
(`sha256:70cdc1c710d1a334a28e7c894f41db61a024baf61a3ddaa76029a937b2ea5e57`,
`edgartools-prod-medium:104`), and direct Apple run
`84eeed611ba64bc7a0cefbe92c5e826b`, the task exited 0 and wrote 44 Apple
`sec_earnings_release` rows.  A read-only query of the newly uploaded canonical production
silver database verifies accession `0000320193-19-000073` with FY2019 Q2,
revenue $53.809B, net income $10.044B, and diluted EPS $2.18.  The preserved SEC bytes were
used without mutating the 45 original bronze objects; this ticket is resolved.
