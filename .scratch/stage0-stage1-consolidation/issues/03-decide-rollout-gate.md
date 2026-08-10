# Decide the safe rollout gate and verification plan for redeploying load_history's definition against a live production pipeline

Type: grilling
Status: resolved
Blocked by: 02

## Question

The user's explicit instruction (map Notes) is: design now, but do not
touch `load_history`'s deployed state-machine definition until task #35's
`retry5` execution — currently live, running against the just-shipped
(Aug 5-9) Stage0 delta-then-reduce restructuring — finishes cleanly.
Decide, concretely:

1. **What does "finishes cleanly" mean, checkably?** Candidates: the
   execution reaches `SUCCEEDED` status; Stage0/`ReduceIdentityRefresh`
   specifically completes without retry/failure (isolating confidence in
   the exact machinery this map's ticket 02 architecture builds on);
   `artifact_bronze_recovered` events confirm PR #395's bronze-recovery
   fix is also working correctly alongside it; gold tables populate at
   the end. Pick the bar — some subset, or all of it.

2. **What if retry5 fails for a reason unrelated to Stage0's
   restructuring** (e.g. an SEC rate-limit issue, an unrelated bug)? Does
   the gate require a *clean* run specifically, or just *evidence Stage0's
   restructuring itself didn't cause the failure* — these could mean
   waiting indefinitely for a fully clean end-to-end run vs. a narrower,
   faster bar.

3. **Redeploy mechanics.** `write_load_history_definition`'s redeploy
   re-registers the whole state machine — any in-flight execution keeps
   running on its snapshotted definition (confirmed safe for `retry5`
   itself), but a *retry/restart* of a failed `load_history` execution
   after this redeploy would hit the new, substantially different shape.
   Decide whether the team wants a dry-run/staging verification step
   (e.g. a bounded `--cik-list` smoke execution against the new
   definition before trusting it for the next full-universe run) before
   the next real `load_history` invocation, mirroring this repo's own
   established pattern of bounded smoke tests before trusting a
   structural change at scale (see CLAUDE.md's cutover-stage precedent).

4. **Rollback plan.** If the merged Stage0/Stage1 definition misbehaves in
   its first live run, what's the fastest safe rollback — redeploy the
   prior (pre-merge) `write_load_history_definition` output, or something
   else? Confirm this repo's existing rollback capture pattern (state
   machine definition snapshot before redeploy, per CLAUDE.md's AWS
   teardown precedent) applies here.

## Pre-grill fact-finding

Live status check at grill time (2026-08-10 15:42 ET): retry5's `Stage0
CompanyIdentity` (53/53 succeeded) and `ReduceIdentityRefresh` — the exact
machinery this map's design replaces — **already succeeded**;
`Stage1Parallel` just entered. Checked for existing conventions: no
scripted/documented state-machine-definition rollback-snapshot pattern
exists in this repo (task #21's prior redeploy did it ad hoc via
`aws stepfunctions describe-state-machine --query definition`, not a
reusable script). A reusable bounded-smoke-test precedent does exist —
snowflake-account-cutover's ticket 06 used `bootstrap-next --limit 100`
before trusting a structural cutover at full scale.

## Answer

1. **Bar: whole execution reaches `SUCCEEDED`.** Simplest, matches the
   map's own Notes language, and is the actual production goal (task #35)
   — no reason to accept a narrower bar when the full outcome is directly
   observable.

2. **Unrelated-failure carve-out: the gate does not block on it.**
   Reconciling with point 1 — `SUCCEEDED` is the *preferred*/primary
   target, but if retry5 fails later for a reason demonstrably unrelated
   to Stage0/`ReduceIdentityRefresh` (which, as of this ticket's
   resolution, have already both succeeded on this run), that failure
   does not block this map's implementation. The gate's actual purpose is
   confidence in the specific machinery ticket 02's design replaces, not
   an indefinite hold hostage to unrelated bugs in Stage1B/artifact-fetch/
   MDM. **As of this resolution, that narrower bar is already satisfied**
   — Stage0 and `ReduceIdentityRefresh` succeeded live on retry5. A full
   `SUCCEEDED` execution remains the cleaner signal if it arrives before
   implementation starts, but is not a hard blocker given the above.

3. **Add a bounded smoke test.** Before trusting the post-merge
   `load_history` definition for the next full-universe run, run a small
   `--cik-limit`-bounded execution against it first — same shape as the
   snowflake-account-cutover precedent (`bootstrap-next --limit 100`).

4. **Rollback: manual snapshot step, not new tooling.** Add
   `aws stepfunctions describe-state-machine --state-machine-arn
   arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-prod-load-history
   --query definition --output text > load_history_definition.pre-merge.json`
   (or equivalent) as an explicit step in the implementation checklist,
   run immediately before `deploy-aws-application.sh` redeploys
   `write_load_history_definition`. Mirrors task #21's prior redeploy;
   two uses doesn't clear the bar for building dedicated rollback tooling
   (Rule 0).
