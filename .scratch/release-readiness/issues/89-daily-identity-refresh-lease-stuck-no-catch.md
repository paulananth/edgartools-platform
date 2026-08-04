# 89 — `daily_identity_refresh` lease has no release-on-failure, currently stuck

Type: task
Status: open

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
