Type: task
Status: open

## Question

Ticket 84 wired `sec_fetch_active` (the cross-command SEC-fetch lease) into
all 5 SEC-fetching state machines, but the actual work state --
`RunWarehouseTask` (and its `RunWarehouseTaskDefault`/
`RunWarehouseTaskWithCikList` variants in `targeted_resync`) -- has no
`Catch`. This was known and documented in ticket 84 as a "blast-radius
note," treated as an accepted tradeoff matching the existing
identity-refresh lease's own convention (release is best-effort; the 16h
stale-reclaim window is the real recovery path).

Live verification of ticket 84 (2026-08-04) empirically demonstrated this
is a live, easily-triggered problem, not a theoretical edge case: **two
separate, unrelated, completely mundane failures** (a real immutable-bronze
content conflict on a real CIK, and a deliberately-invalid CLI arg used in
a follow-up probe) both wedged `sec_fetch_active` on the first try, each
time requiring a manual `ecs run-task` + `release-sec-fetch-lease
--run-id <holder>` to recover. Any `RunWarehouseTask` failure -- SEC rate
limiting, a transient S3 error, a bad filing, an ECS capacity blip --
wedges **all 5 SEC-fetching commands platform-wide** for up to 16h, not
just the one command that failed.

This repo already has the exact fix pattern in the same file:
`adv_bulk_fetch_catch = [{"ErrorEquals": ["States.ALL"], "ResultPath": None,
"Next": "ReleaseSecFetchLease"}]`, applied to `fetch-adv-bulk`/
`ingest-relationship-sources` inside `write_warehouse_mdm_gold_definition`.
The same `Catch` needs to route `RunWarehouseTask` (and its two
`targeted_resync` variants) to `ReleaseSecFetchLease` in all 5 machines,
so a downstream task failure releases the lease before the execution fails,
instead of leaving it held.

**Decisions to confirm before implementing** (not yet resolved):
- Should the `Catch` re-raise the original failure after releasing (so the
  execution still shows FAILED, just without wedging the lease), or should
  it route to a distinct terminal "released, but underlying task failed"
  state? The existing `adv_bulk_fetch_catch` pattern continues past the
  failure into a non-fatal path (`ReleaseSecFetchLease` -> success) rather
  than re-failing -- confirm whether that's the right shape for a
  `RunWarehouseTask` failure too, since callers/alerting may currently
  depend on execution status reflecting whether the real work succeeded.
- Does this change interact with `RunWarehouseTask`'s existing `Retry`
  block (2 attempts, `States.TaskFailed`)? The `Catch` should only fire
  after retries are exhausted, which is already how Step Functions orders
  `Retry` before `Catch` -- just confirm no `MaxAttempts` interaction
  changes semantics for the 5 machines' individually-tuned retry configs.
