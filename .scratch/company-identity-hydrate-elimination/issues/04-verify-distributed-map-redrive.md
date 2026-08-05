# Does AWS Step Functions Distributed Map redrive actually resume only failed batches for this delta-then-reduce shape?

Type: research
Status: open

## Question

Ticket 01 found that delta-then-reduce loses per-window failure isolation:
`reduce_identity_refresh`'s manifest-completeness check
(`validate_complete_run_manifest`, `identity_refresh_publication.py:349-393`)
requires *every* declared batch to show `status == "succeeded"` before
*any* batch's delta is merged into canonical. If one batch out of ~53
permanently fails, none of the other 52 successful batches' data reaches
canonical for that run — even though each batch's delta is already a
durable, checksummed, immutable S3 object.

Ticket 01 flagged AWS Step Functions Distributed Map's platform-level
"redrive" capability (re-executing only failed child items of a Map Run,
not already-succeeded ones) as architecturally compatible with rescuing
this — the manifest check is idempotent to *when* a batch succeeds, so a
redrive that only reruns the failed batch and leaves the other 52 deltas
untouched should let the SAME manifest eventually show all-succeeded and
proceed to reduce. But this is **plausible, not verified** — nothing in
this repo exercises or tests an actual redrive.

Per the operator's explicit decision on ticket 03 (2026-08-05): do not
lock in delta-then-reduce as Stage0CompanyIdentity's target architecture
until this is verified, not just plausible.

Investigate:

1. Read AWS's actual documented redrive semantics for Distributed Map
   (`ecs:runTask.sync`-backed Map Runs specifically, not just Standard Map)
   — primary source (AWS docs), not a secondary summary. Confirm: does
   redrive genuinely skip already-succeeded child executions and rerun
   only failed ones, for a Map Run in the shape this repo uses
   (`ItemReader` from S3 JSONL, `ItemProcessor` with `Mode: DISTRIBUTED`)?
2. What triggers a redrive — is it automatic (e.g. on `MaxAttempts`
   exhaustion within the Map's own Retry) or does it require an explicit
   operator/API call (`RedriveExecution`)? If manual, does load_history's
   current failure-handling shape (Catch → `ReleaseSecFetchLeaseAfterFailure`
   → `SecFetchTaskFailed`, a terminal `Fail` state) leave the *execution* in
   a state redrive can actually act on, or does reaching a `Fail` state
   preclude redriving the Map Run within it? (This matters because Stage0's
   own Catch already routes failures to a terminal Fail state today — check
   whether that's compatible with or needs to change for redrive to apply.)
3. Are there any constraints on redrive relevant here — e.g. time limits
   on how long after the original failure a redrive can be issued, limits
   on redrive count, or requirements about unchanged input data (this
   repo's CIK universe / tracking_status could change between the original
   failure and a redrive attempt — does that invalidate anything)?
4. If redrive doesn't cleanly apply as hoped, what's the fallback: does
   ticket 03 need to design an explicit partial-promotion mechanism
   instead (accepting the added scope), or is there a simpler mitigation
   (e.g. a manual "resume from these specific failed batches" CLI
   parameter that reduce_identity_refresh could accept, sidestepping SFN's
   own redrive mechanism entirely)?

Report a clear verdict on whether redrive genuinely provides safe,
batch-level resumability for this exact shape, with primary-source
citations, so ticket 03 can either lock in delta-then-reduce as designed
or adjust its failure-isolation approach.
