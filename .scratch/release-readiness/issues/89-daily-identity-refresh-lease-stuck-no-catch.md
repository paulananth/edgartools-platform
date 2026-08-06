# 89 — `daily_identity_refresh` lease has no release-on-failure, currently stuck

Type: task
Status: resolved (2026-08-06)

## Question

Found live 2026-08-04 while starting today's `daily_incremental` run per the
current session's task. The run deferred and did **zero work** — not because of
a genuine concurrent holder, but because a **different, older lease**
(`daily_identity_refresh`, distinct from `sec_fetch_active`) has been stuck in
`status='held'` since **2026-08-03 21:57:22 UTC** (~16.7h before this run),
`released_at: NULL`.

Confirmed via direct canonical-S3 read of `pipeline_run_lease`:

```
{'lease_name': 'daily_identity_refresh', 'status': 'held',
 'run_id': 'daily-incremental-ticket77-livemeasure-1785794199', 'mode': 'daily',
 'acquired_at': 2026-08-03 21:57:22 UTC, 'released_at': None,
 'backstop_overdue': False}
```

The holder, `daily-incremental-ticket77-livemeasure-1785794199`, is
[ticket 83](83-reduce-identity-refresh-oom-on-merge.md)'s own OOM incident —
`reduce-identity-refresh` was OOM-killed twice (exit 137, "OutOfMemoryError:
container killed due to memory usage") on `edgartools-prod-medium` (4096MB),
confirmed via `get-execution-history`'s `TaskFailed`/`ExecutionFailed` events.
Ticket 83 already root-caused and fixed *that* OOM (disk-cached verified
inputs + medium→large resize) but never addressed this consequence: whatever
Step Functions state acquires `daily_identity_refresh` has **no `Catch`**, so
the failure left the lease permanently held with nothing to reclaim it.

This is the same class of gap [ticket 86](86-add-catch-to-runwarehousetask-sec-fetch-lease.md)
fixed for `sec_fetch_active` (`ReleaseSecFetchLeaseAfterFailure` /
`SecFetchTaskFailed`) — but `daily_identity_refresh` is a **separate lease**,
acquired/released by different Step Functions states
(`acquire-identity-refresh-lease` / `release-identity-refresh-lease`, see
`edgar_warehouse/application/warehouse_orchestrator.py:2620-2692`), and ticket
86's fix did not cover it.

**Correction — not stuck forever.** `db.acquire_pipeline_run_lease`
(`silver_store.py:2707`) defaults `stale_after_seconds` to `20 * 3600`, and
`acquire-identity-refresh-lease` (`warehouse_orchestrator.py:2645`) doesn't
override it — confirmed via source read, this is a genuine reclaim-on-next-
acquire mechanism (the UPDATE branch fires when the lease is held but
`acquired_at` is older than the stale window), not a separate sweep job that
might not be scheduled. Acquired at 2026-08-03 21:57:22 UTC + 20h =
**2026-08-04 17:57:22 UTC** — the *next* `daily_incremental` trigger after
that time will reclaim it automatically. Today's manually-triggered run
(`daily-incremental-1785854334`, this session) deferred and completed
(zero work) before that window closed, so it does not self-retry — an
operator still needs to either wait for the 17:57 UTC backstop and trigger a
fresh run after it, or clear the lease now via the real
`release-identity-refresh-lease` ECS command (not a direct DuckDB mutation)
to unblock immediately.

## Open questions

1. Same fix shape as ticket 86 (`Catch` → release-then-refail) applied to
   whichever state(s) acquire `daily_identity_refresh` across
   `daily_incremental` (and any other machine that touches this lease) — is
   there a reason the two leases were wired asymmetrically, or was this
   simply not in ticket 86's original scope (its own text only mentions
   `sec_fetch_active`)?
2. Does the 20h-ish backstop actually reclaim this lease unattended, or does
   it require an explicit sweep command that isn't scheduled anywhere? Worth
   confirming empirically rather than trusting the comment in
   `warehouse_orchestrator.py`.
3. Immediate unblock: run `release-identity-refresh-lease --run-id
   daily-incremental-ticket77-livemeasure-1785794199` via a one-off ECS task
   (the real, tested code path — not a direct DuckDB mutation) so today's/next
   daily run can proceed. Not yet run — pending explicit confirmation per
   this repo's live-prod-action convention.

## Done when

`daily_identity_refresh` is cleared and a fresh `daily_incremental` run
actually reaches `RunWarehouseTask` (not just `NotifyDeferred`); the Catch
fix is implemented, tested, deployed, and live-verified the same way ticket
86 was (a real failure releases the lease with zero manual intervention).

## Answer (2026-08-06)

The original hypothesis ("no `Catch` on whatever acquires the lease") was
**stale by the time this was picked back up** -- re-checking live state
first (per this repo's own "verify before trusting a snapshot" discipline)
found something different: a `Catch` already existed on `ReleaseLease`
(`ReleaseLeaseFailedNonFatal`, "release is best-effort" -- likely landed as
part of some other pass between this ticket being filed and worked). But
the lease was **still held**, `released_at: NULL`, acquired
2026-08-04T11:11:01 EDT -- over 44h earlier, well past the 20h stale-reclaim
window `acquire_pipeline_run_lease` is supposed to provide.

Traced the actual execution that acquired it
(`daily-incremental-ticket89-unblocked-1785856213`, status `SUCCEEDED`,
started 2026-08-04T11:10:16 EDT, stopped 16:00:57 EDT -- an earlier
session's own immediate-unblock-and-retest, from before this session's
compaction). Its `ReleaseLease` step ran for 15 minutes and hit
`States.TaskFailed` **four times in a row** -- every attempt -- each with
`ExitCode 137, "OutOfMemoryError: container killed due to memory usage"`,
on `edgartools-prod-medium` (4096MB). After retries exhausted, the existing
Catch routed to `ReleaseLeaseFailedNonFatal` and the *execution* reported
`SUCCEEDED` -- so the lease being permanently stuck was **completely
invisible** in Step Functions' own status; only a direct read of
`pipeline_run_lease` in canonical S3 exposed it.

Root cause: `release-identity-refresh-lease`'s own handler
(`warehouse_orchestrator.py:2742-2749`) is a single `UPDATE
pipeline_run_lease ...` statement -- trivial by itself. But every command in
this dispatcher, `release-identity-refresh-lease` included, is not on the
one exception path (`bootstrap-batch` with a remote shard manifest,
`_execute_warehouse_bronze_capture` line 414-418) and so unconditionally
hits `_hydrate_silver_database_from_storage` -- downloading and opening the
**entire canonical silver.duckdb** (confirmed live: 1273.8MB and growing,
containing the 6.8M-row `sec_thirteenf_holding` table etc.) before it ever
reaches its own one-line UPDATE. `ReduceIdentityRefresh`, immediately
before `ReleaseLease` in the same state machine, was already moved
`medium -> large` for this *exact* reason under ticket 83
("OOM-killed on medium's 4096MB mid-merge on the largest protected table").
`ReleaseLease` runs right after `ReduceIdentityRefresh`/`GoldRefresh` have
just made canonical heavier within the same run -- so by the time it
hydrates, it's paying that same cost against the freshest, heaviest version
of canonical, on the smaller profile ticket 83 already proved insufficient.
This is the same class of waste as the open
`bootstrap-fundamentals --mode company-identity` wayfinder map (full-hydrate
for an operation that needs almost nothing from canonical) -- not fixed
structurally here, out of scope for this ticket; see that map for the
root-cause elimination effort.

**Fix (mirrors ticket 83's own precedent exactly):** `ReleaseLease` moved
`wh_medium_arn -> wh_large_arn` in `deploy-aws-application.sh`. Regression
test added
(`tests/architecture/test_daily_identity_refresh_state_machine.py::test_release_lease_runs_on_the_large_task_definition`),
confirmed to fail against the pre-fix wiring and pass after. Full
`tests/unit/` + `tests/architecture/` suite: 1049 passed, 4 skipped, only
the pre-existing unrelated `test_go_live_wizard.py` failure (already
failing on `main`, unrelated to this change).

**Immediate unblock:** the stuck lease
(`daily-incremental-ticket89-unblocked-1785856213`) was cleared via a
one-off `release-identity-refresh-lease` ECS task run on the `large`
profile (not `medium`, since `medium` reliably OOMs on this operation) --
confirmed via a fresh read of `pipeline_run_lease` that `status='idle'` and
`released_at` is set. Deployed to prod and live-verified: see the commit
that closes this ticket for the exact digests/task-definition revisions.

**Still open, deliberately out of scope here:** Open question 2 from the
original ticket ("does the 20h stale-reclaim actually fire unattended, or
does nothing ever trigger it?") is now moot for *this* incident (the fix
prevents the OOM that caused it), but the underlying scheduling gap is
real and separate: `--configure-daily-incremental-schedule` is off by
default (CLAUDE.md) and was not enabled as part of this ticket, so no
recurring trigger exists to exercise the stale-reclaim path at all if a
*future*, different failure mode wedges this lease again. Worth a
follow-up if/when the recurring schedule is turned on for real.
