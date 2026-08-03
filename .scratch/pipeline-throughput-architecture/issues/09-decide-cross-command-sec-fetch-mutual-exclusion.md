Type: grilling
Status: resolved

## Question

Should the platform enforce mutual exclusion across *different* SEC-fetching
commands (`daily-incremental`, `bootstrap`, `bootstrap_full`,
`targeted_resync`, `bootstrap-batch` -- all five share
`_capture_submission_bronze_snapshot`, plus the separate artifact-fetch
loop in `bronze_filing_artifacts.py`), so that only one command's worth of
SEC request traffic runs at a time platform-wide?

## Why this is a real, separate decision

[Ticket 06](06-fix-cross-task-sec-rate-limit-compliance.md) fixes each
*command's own* internal concurrency to stay within SEC's 9-10 req/sec
ceiling (via ticket-03-style intra-task threading instead of cross-task
fan-out). But that only guarantees compliance if no *other* SEC-fetching
command is running at the same time. Confirmed via code reading:
`pipeline_run_lease` (`silver_store.py:2707`) is a generic, reusable
mutual-exclusion primitive (atomic acquire, staleness reclaim after a
configurable timeout), but the only lease name actually registered
anywhere in the codebase is `daily_identity_refresh`
(`warehouse_orchestrator.py:141`), used solely to guard `daily-incremental`'s
own identity-refresh-window computation against itself. There is currently
**no** lock preventing, for example, an operator-triggered `bootstrap-batch`
run from overlapping with a scheduled `daily-incremental` execution -- both
would be internally compliant after ticket 06's fix, but could jointly
exceed SEC's stated 10 req/sec per-operator ceiling.

## The real tradeoff

A shared "SEC fetch active" lease would serialize these commands
platform-wide -- correct for compliance, but a real operational cost: today
nothing stops (and nothing measures whether anyone actually relies on)
running e.g. a manual `targeted_resync` while `daily-incremental` is
mid-run. Serializing them could meaningfully lengthen wall-clock time for
whichever command has to wait, especially since `daily-incremental` alone
already takes ~3.5 hours end to end (per ticket 01's measurement).
Alternatives worth weighing: a hard mutual-exclusion lease (simplest,
correct, most conservative); a shared rate budget instead of full exclusion
(e.g. a distributed token bucket dividing the 9-10 req/sec ceiling across
whichever commands are concurrently active -- correct but real new
infrastructure to build and operate, the kind of complexity ticket 03
deliberately avoided by choosing intra-task threading over cross-task
coordination); or accepting the residual risk if concurrent runs are rare
enough in practice to be an acceptable compliance exposure (needs real
operational data on how often multiple SEC-fetching commands actually
overlap today -- not yet measured).

## Done when

A decision -- mutual exclusion, shared budget, accept the risk, or
something else -- with reasoning tied to real operational frequency data
where the decision depends on it (e.g. "accept the risk" requires knowing
how often overlap actually happens, not assuming it's rare).

## Answer (2026-08-03, grilling with user)

**Hard mutual exclusion.** "Accept the risk" was ruled out by real data,
not judgment: pulled execution history for every SEC-fetching state
machine and found `bootstrap` (`bootstrap-ticket03-verify-1785426021`,
2026-07-30T11:40:24 to 15:50:07) and `daily-incremental`
(`daily-incremental-ticket03-1785413694`, 2026-07-30T08:14:56 to
21:35:12) **actually overlapped for 4.16 hours**, 4 days before this
ticket was resolved -- both independently making SEC calls, both
individually compliant with the 9 req/sec in-process limiter, both
jointly over SEC's stated 10 req/sec aggregate ceiling for that entire
window. Not hypothetical, not rare -- it already happened. (Side finding:
`bootstrap_full` and `targeted_resync` have **zero executions ever** in
prod -- their exposure is currently theoretical; the real overlap risk is
between `bootstrap`/`bootstrap-batch`/`load-history` and
`daily-incremental`.)

Between hard exclusion and a shared rate budget: **hard exclusion**,
reusing the *existing* `pipeline_run_lease` primitive
(`silver_store.py:2707` -- atomic acquire, staleness reclaim, already
proven for `daily_identity_refresh`) under a new shared lease name (e.g.
`sec_fetch_active`), rather than building new distributed rate-limiting
infrastructure. Same reasoning ticket 03 used to prefer intra-task
threading over cross-task coordination: don't build a new distributed
primitive when an existing one covers the need. Tradeoff accepted
explicitly: an operator wanting to run one SEC-fetching command while
another is mid-run (`daily-incremental` alone runs ~3.5h, per ticket 01)
will have to wait -- judged acceptable against SEC's compliance risk,
which per ticket 02 includes the platform being blocked "regardless of
req/sec compliance" for automated traffic patterns generally, not just a
10-minute cooldown.

**Scope**: the 5 commands identified in
[ticket 06](06-fix-cross-task-sec-rate-limit-compliance.md) as sharing
SEC-fetching code paths -- `daily_incremental`, `bootstrap`,
`bootstrap_full`, `targeted_resync`, `bootstrap_batch`.

**Left to implementation** (not decided here): the exact acquire/release
boundary (whole-command lifetime vs. just the SEC-fetch-heavy phase,
mirroring how `daily_identity_refresh`'s lease already scopes narrowly to
`ComputeIdentityRefreshWindow`/`ReduceIdentityRefresh`, not all of
`daily-incremental`) and the wait/retry semantics when the lease is held
by another command.

Implementation split to
[release-readiness ticket 80](../../release-readiness/issues/80-implement-cross-command-sec-fetch-lease.md),
matching this map's decision-only mode.
