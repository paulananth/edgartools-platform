# Does AWS Step Functions Distributed Map redrive actually resume only failed batches for this delta-then-reduce shape?

Type: research
Status: resolved

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

## Answer

**Verdict: No — not as this repo is currently wired, and this is now
verified, not merely plausible.** AWS Step Functions Distributed Map
redrive genuinely does skip already-succeeded child items and rerun only
failed ones (Q1) — but only for child failures that reach the parent
execution's terminal outcome **unhandled**. AWS's own launch
documentation for this feature states, in as many words, that errors
handled via `Catch`/`Retry`/routing to a `Fail` state do not qualify for
redrive. This repo's `sec_fetch_task_catch()` wiring — present on every
Stage0 Map and on `ReduceIdentityRefresh` in both `load_history` and
`daily_incremental`'s already-live bounded-identity-refresh shape (the
shape ticket 03 wants to generalize to `load_history`) — deliberately
Catches every Map/reducer failure and routes it to a terminal `Fail`
state (`SecFetchTaskFailed`), specifically so the `sec_fetch_active`
lease releases promptly instead of waiting out the 18h stale-lease
reclaim. That is exactly the disqualifying pattern. Redriving one of
these executions today would re-enter and immediately re-fail
`SecFetchTaskFailed` — it would not resume the ~52 other successful
batches' sibling that never got a chance to run, or wasn't declared as
failed.

### Q1 — Does redrive genuinely skip succeeded children and rerun only failed ones, for this repo's ItemReader(S3 JSONL) + ItemProcessor(Mode=DISTRIBUTED) shape?

Yes, as a generic mechanism — confirmed primary source, and confirmed to
match this repo's exact `ExecutionType`.

- The redrive-behavior table for state types
  (docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html#redrive-behavior-states)
  states for **Distributed Map**: "redrives the unsuccessful child
  workflow executions in a
  [Map Run](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-examine-map-run.html)."
  identical wording is repeated in the `RedriveExecution` API reference
  (docs.aws.amazon.com/step-functions/latest/apireference/API_RedriveExecution.html).
- The child-workflow-type table on
  docs.aws.amazon.com/step-functions/latest/dg/redrive-map-run.html#redrive-child-workflow-behavior
  is specific to `ExecutionType` — and this repo's Map shape is
  `ExecutionType: "STANDARD"` (confirmed live in the worktree at
  `infra/scripts/deploy-aws-application.sh:2258` for
  `stage0_company_identity`'s `ItemProcessor.ProcessorConfig`, and
  `:3269` for the bounded daily_incremental prototype
  `stage0_company_identity_bounded`), not `EXPRESS`. For `STANDARD`
  children, the table says: "All child workflow executions that failed,
  timed out, or canceled in the original execution attempt are redriven
  using the `RedriveExecution` API action. These child workflows are
  redriven from the last state in `ItemProcessor` that resulted in their
  unsuccessful execution." — i.e. exactly "rerun only the failed ones,"
  not the whole batch.
- One documented exception, not the normal path here: if a Map fails with
  `States.DataLimitExceeded` (output/input exceeding the payload size
  quota), redrive/Inline-Map/Distributed-Map rerun **everything**,
  including previously-succeeded children
  (docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html;
  redrive-executions.html's state table, Distributed Map row's second
  sentence). This repo's per-batch `ItemSelector`/output is small
  (`cik_list` plus a run id, `deploy-aws-application.sh:3264-3267`), so
  this exception is not expected to be the actual failure mode in
  practice, but ticket 03 should be aware it exists.

So the mechanism itself is real and matches this repo's shape. The
blocker is not "does redrive do what ticket 01 hoped" — it's "does this
repo's failure-handling wiring let redrive act on the right state," which
Q2 answers no.

### Q2 — What triggers redrive, and does this repo's Catch → `ReleaseSecFetchLeaseAfterFailure` → `SecFetchTaskFailed` (terminal `Fail`) wiring preclude it?

**Trigger: always manual, never automatic.** Redrive fires only via an
explicit `RedriveExecution` API call (or the console's "Redrive" button)
— nothing in Step Functions auto-issues it on `MaxAttempts` exhaustion or
any other condition
(docs.aws.amazon.com/step-functions/latest/apireference/API_RedriveExecution.html;
docs.aws.amazon.com/step-functions/latest/dg/redrive-map-run.html#redrive-maprun-api).
This alone means ticket 03 cannot treat redrive as a background safety
net — it requires either an operator action or new automation (e.g. an
EventBridge rule on `ExecutionsFailed` that calls `RedriveExecution`),
neither of which exists in this repo today.

**Decisive finding: yes, reaching a `Fail` state via `Catch` precludes
redrive from rescuing the Map Run underneath it.** AWS's own launch
announcement for the redrive feature states this directly (AWS Compute
Blog, "Introducing AWS Step Functions redrive: a new way to restart
workflows," published 2023-11-15 — the same date that shows up
independently as the redrive-eligibility cutoff date in the docs, i.e.
this is the feature's actual launch post, not a stale mirror):
aws.amazon.com/blogs/compute/introducing-aws-step-functions-redrive-a-new-way-to-restart-workflows/,
corroborated by its syndicated copy at
noise.getoto.net/2023/11/15/introducing-aws-step-functions-redrive-to-recover-from-failures-more-easily/
and independently quoted verbatim by third-party write-ups summarizing
it:

> "Redrive is for unhandled and unexpected errors only. Handling errors
> within a workflow using the built-in mechanisms for catch, retry, and
> routing to a Fail state, does not permit the workflow to redrive."

This is consistent with (not contradicted by) the state-by-state redrive
table on redrive-executions.html: the **Fail workflow state** row says
redrive simply "Reenters the Fail state and fails again." A `Fail` state
has no retry/branch logic of its own to re-evaluate — so when an
execution's terminal marker is a `Fail` state reached via a `Catch` that
already redirected flow past the real failure, redriving that execution
is a no-op that immediately re-fails, not a resumption of whatever failed
upstream of the catch.

This is exactly this repo's wiring today, confirmed by direct inspection
of the worktree's `infra/scripts/deploy-aws-application.sh`, not
inference:

- Both live copies of `sec_fetch_task_catch()` (kept manually in sync per
  this file's own documented duplication convention — one per Python
  heredoc/subprocess) return the identical catcher:
  `[{"ErrorEquals": ["States.ALL"], "ResultPath": "$.sec_fetch_task_error", "Next": "ReleaseSecFetchLeaseAfterFailure"}]`
  (`deploy-aws-application.sh:1493-1497` and `:1983-1987`).
- `load_history`'s `stage0_company_identity` Map sets
  `"Catch": sec_fetch_task_catch()` (`:2266`). `daily_incremental`'s
  bounded prototype `stage0_company_identity_bounded` — the shape ticket
  03 is evaluating generalizing to `load_history` — does the same
  (`:3275`), as does its `reduce_identity_refresh` step (`:3245`).
- `ReleaseSecFetchLeaseAfterFailure` (`:1969-1975`) is an ECS Task that,
  on success, transitions via its own `next_state` param straight to
  `"SecFetchTaskFailed"`, and on its *own* failure Catches straight to
  `"SecFetchTaskFailed"` too (`:1974`) — every path through it ends at
  the same place.
- `SecFetchTaskFailed` (`:1976-1980`) is `"Type": "Fail"` — and the
  surrounding comment (`:1966-1968`) confirms this is deliberate, not
  incidental: "this path always ends in Fail, preserving
  ExecutionsFailed/alarm visibility for a real work failure." This was
  release-readiness ticket 86's fix for a real prior bug (a failure
  inside these stages used to wedge the `sec_fetch_active` lease for the
  full 16h stale-reclaim window, `:1956-1960`) — so the Catch-to-Fail
  wiring is itself the fix for a previously-shipped incident, not
  something ticket 04 can casually recommend reverting.

So today, and in the exact bounded prototype daily_incremental already
runs in production, a batch failure inside Stage0's Map is *caught*, not
left to propagate uncaught to the execution's own terminal state. Per
AWS's own stated design intent, that disqualifies the Map's failure from
being what redrive resumes. `RedriveExecution` against the resulting
`FAILED` execution would re-enter and re-fail `SecFetchTaskFailed`
(possibly without even an API-level error — the general eligibility
checks in Q3 don't inspect Catch topology, only execution status/age/event
count — so an operator could issue the call, have it "succeed," and get a
misleading no-op rather than a rescued run).

### Q3 — Constraints (if the Catch were removed so the Map's own failure propagated uncaught)?

Answered for completeness, since ticket 03 may still want to weigh option
1 in Q4. If the Map's failure were left genuinely uncaught (so it becomes
the execution's own terminal unsuccessful state), redrive would then be
subject to:

- **14-day eligibility window** from when the execution completed, plus:
  started on/after 2023-11-15 (moot for this repo), not exceeding the
  1-year max open time, and under 24,999 total execution history events
  (docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html#redrive-eligibility;
  identical conditions repeated in the `RedriveExecution` API reference).
- **Hard cap of 1000 redrives per Map Run** — beyond that, a
  `States.Runtime` error
  (docs.aws.amazon.com/step-functions/latest/dg/redrive-map-run.html#redrive-eligibility-map-run).
  Irrelevant at 53-batch scale, but not literally unlimited.
- **Per-child redrivability window, `STANDARD` children specifically:**
  each per-batch child execution (this repo's `RunCompanyIdentityBatch`/
  `RunCompanyIdentityWindow`, a single-Task `ItemProcessor`,
  `ExecutionType: STANDARD`) has its own 14-day redrivable window
  measured from when *that child* closed, independent of the parent's own
  window — "A Standard child workflow execution might not be redrivable
  if the parent workflow execution has closed within 14 days, but the
  child workflow execution closed earlier than 14 days"
  (redrive-map-run.html#redrive-child-workflow-behavior). Not a practical
  concern for a same-day/same-week operator response, but real for a
  "redrive weeks later" scenario.
- **Definition/version pinning:** "Redriven executions use the same state
  machine definition and execution ARN that was used for the original
  execution attempt... you must start a new execution if you update your
  state machine definition" (redrive-executions.html). If
  `deploy-aws-application.sh` is re-run between the original failure and
  the redrive attempt (e.g. to ship an unrelated fix), the redrive still
  runs the *old* registered state-machine version, not whatever was just
  deployed.
- **Input/data-drift — not an AWS-level constraint, and already resolved
  cleanly on this repo's side.** Per AWS's own redrive-input table
  (redrive-map-run.html#maprun-redrive-input), a Map Run that already
  started child executions redrives using "the same input provided in the
  original execution attempt," regardless of what the ItemReader's S3
  object might contain by then. This repo's ItemReader key is
  `warehouse/bronze/reference/cik_universe/runs/{run_id}/cik_batches.jsonl`
  (or `cik_windows.jsonl`) — an immutable, `run_id`-scoped path, written
  once via `write_immutable_bytes` and never rewritten
  (`persist_run_manifest`, `edgar_warehouse/application/identity_refresh_publication.py:88-126`).
  So a `tracking_status`/CIK-universe change between the original failure
  and a redrive attempt can't leak into a redrive even in principle —
  combined with `validate_complete_run_manifest`'s own re-check that every
  declared batch's outcome matches its declared CIK identity
  (`identity_refresh_publication.py:380-389`, per ticket 01's Q2), there
  is no drift-invalidation risk on the data side. The only real blocker is
  Q2's Catch-to-Fail wiring, not data staleness.

### Q4 — Fallback, given redrive does not cleanly apply as currently wired

Two real options, framed as ticket 03 needs to choose between them, not
as a menu of equally-good alternatives:

1. **Drop the Map's own `Catch` so its failure propagates uncaught**,
   making it genuinely redrive-eligible. This is a real architecture
   regression to weigh, not a config flip: it means `sec_fetch_active`
   would stop releasing promptly on *this* specific failure mode — the
   exact problem release-readiness ticket 86 fixed
   (`deploy-aws-application.sh:1956-1968`) — and would fall back to the
   pre-existing 18h stale-lease reclaim instead. Choosing this requires
   explicitly re-opening and accepting that trade-off (16-18h of a held
   cross-command lease after a genuine Stage0 failure, blocking any other
   SEC-fetching command in the meantime) in exchange for batch-level
   redrive resumability — not silently reverting ticket 86's fix as a
   side effect of ticket 03's restructuring.
2. **Recommended: sidestep SFN redrive entirely with an explicit CLI
   resume path**, built on the manifest/outcome contract this repo
   already owns (`persist_run_manifest`/`persist_batch_outcome`/
   `validate_complete_run_manifest`, already covered by this repo's own
   tests per ticket 01). A `reduce-identity-refresh` flag (or a narrow,
   manually-triggered replacement Map/Task scoped to just the batch_id(s)
   missing a `succeeded` outcome, run with the **same** `run_id`/
   `identity_refresh_run_id`) reuses the identical immutable-delta
   contract without depending on SFN's redrive eligibility windows, the
   `STANDARD`-vs-`EXPRESS` distinction, the 1000-redrive/14-day/
   version-pinning constraints in Q3, or the Catch-disqualification
   finding in Q2. It keeps failure recovery inside application code this
   repo already tests, rather than depending on infra behavior this repo
   has never exercised even once. This does not require re-opening ticket
   86's lease-release fix.

## Not yet specified

- The concrete shape of option 2's CLI resume path (exact flag name,
  whether it's a `reduce-identity-refresh` addition or a separate
  companion command, how an operator discovers which batch_ids are
  missing) is a design decision for ticket 03, not answered here.
- Whether ticket 03 wants an automated redrive-adjacent safety net (e.g.
  an EventBridge rule on Stage0 `ExecutionsFailed` invoking a Lambda that
  inspects the manifest and either calls the Q4-option-2 CLI resume path
  or pages an operator) is out of scope for this verification ticket.

## Done when

Done — all four questions answered from primary AWS documentation (with
URLs) plus direct file:line inspection of this worktree's actual
`deploy-aws-application.sh`/`identity_refresh_publication.py`, and a clear
verdict given: redrive does NOT cleanly rescue this repo's current
delta-then-reduce shape, because every Map/reducer state that would need
redriving is deliberately Caught into a terminal `Fail` state (ticket 86's
fix for a real prior lease-wedging incident), and AWS's own documentation
states that Catch-handled errors are excluded from redrive by design.
Ticket 03 should not lock in delta-then-reduce on the assumption that
redrive provides free batch-level resumability; it should pick between
Q4's two options and update its failure-isolation section accordingly.
